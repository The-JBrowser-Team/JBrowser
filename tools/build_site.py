"""Build the JBrowser website (GitHub Pages) into ``_site/``.

The site has four parts:

* ``index.html``: the home page, with a direct download of the newest installer.
* ``download/``: a permanent link that always leads to the newest installer.
* ``changelog/``: CHANGELOG.md, one section per release.
* ``docs/<version>/``: the developer documentation of every release since 1.4.0, plus
  ``docs/main/`` (the development branch) and ``docs/latest/`` (the newest release again).

The hand-written documentation lives in ``site/docs`` as Markdown, in the order given by
``site/docs/nav.json``. A page can differ between versions::

    <!-- if >= 1.5.0 -->  ...  <!-- elif == 1.4.1 -->  ...  <!-- else -->  ...  <!-- endif -->

and its front matter can limit it to some versions (``since: 1.5.0``, ``until: 1.4.1``,
``only: main``). The references (settings, commands, shortcuts, command line, data files and
the Python API) are generated from each version's own source code, read from its git tag.

Usage, from the repository folder::

    python tools/build_site.py              # build into _site/
    python tools/build_site.py --serve      # build, then preview at http://localhost:8000/
    python tools/build_site.py --offline    # don't ask the GitHub API for release sizes and dates

It needs ``pip install -r requirements-site.txt`` (Markdown and Pygments). The GitHub Pages
workflow (.github/workflows/pages.yml) runs it on pushes to main, and tools/release.ps1 starts it
after every release.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import html
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tokenize
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indexnow import INDEXNOW_KEY  # noqa: E402  (tools/indexnow.py, no dependencies)

try:
    import markdown
    from pygments.formatters import HtmlFormatter
except ImportError:  # pragma: no cover - explained to the user
    sys.exit("The website builder needs Markdown and Pygments:\n"
             "    python -m pip install -r requirements-site.txt")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
DOCS_SRC = SRC / "docs"
TEMPLATES = SRC / "templates"
STATIC = SRC / "static"
OLDEST_DOCS = (1, 4, 0)          # the first version published on GitHub
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


# ------------------------------------------------------------------------------ small helpers
def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def rel(from_file: str, to_file: str) -> str:
    """Relative URL from the page ``from_file`` to ``to_file`` (both relative to the site root)."""
    base = posixpath.dirname(from_file) or "."
    out = posixpath.relpath(to_file, base)
    return out if not to_file.endswith("/") or out.endswith("/") else out + "/"


def root_of(page: str) -> str:
    """Relative prefix that leads from ``page`` back to the site root ("" or "../../")."""
    depth = page.count("/")
    return "../" * depth


def human_size(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB" if n else ""


def pretty_date(iso: str) -> str:
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d")
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%B %Y')}"


def version_tuple(text: str) -> tuple[int, int, int] | None:
    m = VERSION_RE.match(text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def identity(source: str) -> dict:
    """Constants from jbrowser/__init__.py: __version__, GITHUB_REPO, APP_NAME, COMPANY."""
    out = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


# ------------------------------------------------------------------------------ git access
def find_git() -> str | None:
    exe = shutil.which("git")
    if exe:
        return exe
    desktop = Path(os.environ.get("LOCALAPPDATA", "")) / "GitHubDesktop"
    for app in sorted(desktop.glob("app-*"), reverse=True):
        candidate = app / "resources" / "app" / "git" / "cmd" / "git.exe"
        if candidate.exists():
            return str(candidate)
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / "git.exe"
    return str(candidate) if candidate.exists() else None


class Tree:
    """The repository at one version: a release tag, or the working tree (``ref`` is None)."""

    def __init__(self, git: str | None, ref: str | None):
        self.git = git
        self.ref = ref
        self._cache: dict[str, str | None] = {}
        self._files: list[str] | None = None

    def files(self) -> list[str]:
        if self._files is None:
            if self.ref is None:
                res = subprocess.run([self.git, "ls-files", "--cached", "--others", "--exclude-standard"],
                                     cwd=ROOT, capture_output=True, text=True, encoding="utf-8") if self.git else None
                if res is not None and res.returncode == 0:
                    self._files = sorted(p for p in set(res.stdout.split("\n")) - {""} if (ROOT / p).is_file())
                else:
                    skip = {".git", ".venv", "_site", "dist", "build", "distribution"}
                    self._files = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                                         if p.is_file() and not skip & set(p.relative_to(ROOT).parts))
            else:
                out = subprocess.run([self.git, "ls-tree", "-r", "--name-only", self.ref], cwd=ROOT,
                                     capture_output=True, text=True, encoding="utf-8", check=True).stdout
                self._files = sorted(set(out.split("\n")) - {""})
        return self._files

    def exists(self, path: str) -> bool:
        return path in self.files()

    def prefetch(self, paths: list[str]) -> None:
        need = [p for p in paths if p not in self._cache]
        if not need:
            return
        if self.ref is None:
            for p in need:
                try:
                    self._cache[p] = (ROOT / p).read_text(encoding="utf-8")
                except OSError:
                    self._cache[p] = None
            return
        data = "".join(f"{self.ref}:{p}\n" for p in need).encode("utf-8")
        out = subprocess.run([self.git, "cat-file", "--batch"], cwd=ROOT, input=data, capture_output=True,
                             check=True).stdout
        pos = 0
        for p in need:
            nl = out.index(b"\n", pos)
            header = out[pos:nl].decode("utf-8", "replace")
            pos = nl + 1
            if header.endswith(" missing"):
                self._cache[p] = None
                continue
            size = int(header.split()[2])
            self._cache[p] = out[pos:pos + size].decode("utf-8", "replace")
            pos += size + 1

    def read(self, path: str) -> str | None:
        if path not in self._cache:
            self.prefetch([path])
        return self._cache[path]

    def python_files(self) -> list[str]:
        return [f for f in self.files() if f.startswith("jbrowser/") and f.endswith(".py")]


@dataclass
class Version:
    id: str                          # "1.5.0", or "main"
    number: tuple[int, int, int]     # main: the version its code carries
    tree: Tree
    ref: str                         # git ref used in source links: "v1.5.0" or "main"
    latest: bool = False
    date: str = ""

    @property
    def is_main(self) -> bool:
        return self.id == "main"

    @property
    def number_text(self) -> str:
        return ".".join(map(str, self.number))

    @property
    def label(self) -> str:
        if self.is_main:
            return "main (development)"
        return f"{self.id} (latest)" if self.latest else self.id


def discover_versions(git: str | None) -> list[Version]:
    """Every release tag from OLDEST_DOCS on (newest first), then main."""
    work = Tree(git, None)
    ident = identity(work.read("jbrowser/__init__.py") or "")
    main_number = version_tuple(ident.get("__version__", "0.0.0")) or (0, 0, 0)
    releases: list[Version] = []
    if git:
        tags = subprocess.run([git, "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8").stdout.split()
        for tag in tags:
            number = version_tuple(tag)
            if number and number >= OLDEST_DOCS:
                releases.append(Version(".".join(map(str, number)), number, Tree(git, tag), tag))
    releases.sort(key=lambda v: v.number, reverse=True)
    if releases:
        releases[0].latest = True
    main = Version("main", main_number, work, "main")
    return releases + [main]


# ------------------------------------------------------------------------------ release details
def release_details(repo: str, offline: bool) -> dict[str, dict]:
    """{tag: {date, assets: {name: (url, size)}}} from the GitHub API ({} when offline)."""
    if offline:
        return {}
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases?per_page=60",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "jbrowser-site"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network trouble only costs the sizes and dates
        print(f"  (GitHub API unavailable: {exc}; using fallbacks)")
        return {}
    out = {}
    for rel_ in data:
        if rel_.get("draft") or rel_.get("prerelease"):
            continue
        assets = {a["name"]: (a["browser_download_url"], int(a.get("size") or 0)) for a in rel_.get("assets", [])}
        out[rel_["tag_name"]] = {"date": (rel_.get("published_at") or "")[:10], "assets": assets}
    return out


# ------------------------------------------------------------------------------ templates
_INCLUDE = re.compile(r"\{%\s*include\s+([\w.\-]+)\s*%\}")
_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def render(template: str, values: dict) -> str:
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    for _ in range(3):                         # included templates may include others
        text = _INCLUDE.sub(lambda m: (TEMPLATES / m[1]).read_text(encoding="utf-8"), text)
    return _VAR.sub(lambda m: str(values.get(m[1], "")), text)


# ------------------------------------------------------------------------------ Markdown
_COND = re.compile(r"^\s*<!--\s*(if|elif|else|endif)\b\s*(.*?)\s*-->\s*$")
_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)


def version_test(expr: str, v: Version) -> bool:
    """``>= 1.5.0``, ``< 1.4.1``, ``== 1.4.0``, ``main``, ``not main``, joined with ``and``."""
    for part in (p.strip() for p in expr.split(" and ")):
        if part in ("main", "not main"):
            ok = v.is_main == (part == "main")
        else:
            m = re.match(r"^(>=|<=|==|!=|>|<)\s*(\d+\.\d+\.\d+)$", part)
            if not m:
                raise ValueError(f"Bad version condition: {expr!r}")
            other = version_tuple(m[2])
            ok = {">=": v.number >= other, "<=": v.number <= other, "==": v.number == other,
                  "!=": v.number != other, ">": v.number > other, "<": v.number < other}[m[1]]
        if not ok:
            return False
    return True


_INLINE_COND = re.compile(r"<!--\s*if\s+(.+?)\s*-->(.*?)(?:<!--\s*else\s*-->(.*?))?<!--\s*endif\s*-->")


def apply_conditions(text: str, v: Version, name: str) -> str:
    # Conditions inside a line: <!-- if >= 1.5.0 -->text<!-- else -->other<!-- endif -->
    text = "\n".join(
        _INLINE_COND.sub(lambda m: m[2] if version_test(m[1], v) else (m[3] or ""), line)
        if not _COND.match(line) else line for line in text.split("\n"))
    out: list[str] = []
    stack: list[list[bool]] = []   # [taking this branch, any branch taken]
    for line in text.split("\n"):
        m = _COND.match(line)
        if not m:
            if all(frame[0] for frame in stack):
                out.append(line)
            continue
        kind, expr = m[1], m[2]
        if kind == "if":
            ok = version_test(expr, v)
            stack.append([ok, ok])
        elif not stack:
            raise ValueError(f"{name}: <!-- {kind} --> without <!-- if -->")
        elif kind == "elif":
            ok = not stack[-1][1] and version_test(expr, v)
            stack[-1] = [ok, stack[-1][1] or ok]
        elif kind == "else":
            stack[-1] = [not stack[-1][1], True]
        else:
            stack.pop()
    if stack:
        raise ValueError(f"{name}: unclosed <!-- if -->")
    return "\n".join(out)


def front_matter(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text.replace("\r\n", "\n"))
    if not m:
        return {}, text
    meta = {}
    for line in m[1].split("\n"):
        if ":" in line:
            k, _, val = line.partition(":")
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]          # quoted, as YAML needs for values with a colon
            meta[k.strip()] = val
    return meta, text[m.end():]


def available(meta: dict, v: Version) -> bool:
    if meta.get("only") == "main" and not v.is_main:
        return False
    if meta.get("since") and v.number < version_tuple(meta["since"]):
        return False
    if meta.get("until") and v.number > version_tuple(meta["until"]):
        return False
    return True


def md_to_html(text: str, toc_depth: str = "2-3", permalinks: bool = True) -> tuple[str, list]:
    md = markdown.Markdown(
        extensions=["extra", "admonition", "sane_lists", "toc", "codehilite"],
        extension_configs={"toc": {"permalink": "#" if permalinks else False, "permalink_class": "anchor",
                                   "toc_depth": toc_depth},
                           "codehilite": {"css_class": "highlight", "guess_lang": False}})
    body = md.convert(text)
    return body, getattr(md, "toc_tokens", [])


def plain_text(body: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# ------------------------------------------------------------------------------ the Python API
@dataclass
class ApiFunc:
    name: str
    sig: str
    doc: str
    line: int
    kind: str = ""        # "", "static", "class", "property"


@dataclass
class ApiClass:
    name: str
    bases: list[str]
    doc: str
    line: int
    init_sig: str
    signals: list[tuple[str, str]] = field(default_factory=list)
    attrs: list[tuple[str, str]] = field(default_factory=list)
    methods: list[ApiFunc] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)


@dataclass
class ApiModule:
    name: str
    path: str
    doc: str
    lines: int
    classes: list[ApiClass] = field(default_factory=list)
    functions: list[ApiFunc] = field(default_factory=list)
    constants: list[tuple[str, str, int]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        first = self.doc.strip().split("\n\n")[0].replace("\n", " ")
        return first

    @property
    def package(self) -> str:
        parts = self.name.split(".")
        if self.path.endswith("__init__.py"):
            return self.name
        return ".".join(parts[:-1])


_QT_OVERRIDE = re.compile(r"(Event|^event|^eventFilter|^nativeEvent|^sizeHint|^paint)$")


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef, drop_first: bool) -> str:
    args = copy.deepcopy(fn.args)
    if drop_first:
        if args.posonlyargs:
            args.posonlyargs = args.posonlyargs[1:]
        elif args.args:
            args.args = args.args[1:]
    sig = f"({ast.unparse(args)})"
    if fn.returns is not None:
        sig += f" -> {ast.unparse(fn.returns)}"
    return sig


def _value_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and (len(node.value) > 70 or "\n" in node.value):
        return f"str ({len(node.value):,} characters)"
    text = ast.unparse(node)
    return text if len(text) <= 90 else text[:87] + "…"


def parse_module(path: str, source: str) -> ApiModule | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    name = path[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[: -len(".__init__")]
    mod = ApiModule(name, path, ast.get_docstring(tree) or "", len(source.splitlines()))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            cls = ApiClass(node.name, [ast.unparse(b) for b in node.bases], ast.get_docstring(node) or "",
                           node.lineno, "")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    decos = {ast.unparse(d) for d in sub.decorator_list}
                    if sub.name == "__init__":
                        cls.init_sig = _signature(sub, True).split(" -> ")[0]
                        continue
                    if sub.name.startswith("_"):
                        continue
                    if _QT_OVERRIDE.search(sub.name):
                        cls.overrides.append(sub.name)
                        continue
                    kind = "static" if "staticmethod" in decos else "class" if "classmethod" in decos else \
                        "property" if "property" in decos else ""
                    sig = _signature(sub, kind != "static")
                    cls.methods.append(ApiFunc(sub.name, sig, ast.get_docstring(sub) or "", sub.lineno, kind))
                elif isinstance(sub, ast.Assign) and len(sub.targets) == 1 and isinstance(sub.targets[0], ast.Name):
                    target = sub.targets[0].id
                    value = ast.unparse(sub.value)
                    if value.startswith("pyqtSignal"):
                        cls.signals.append((target, value[len("pyqtSignal"):]))
                    elif target.isupper() and not target.startswith("_"):
                        cls.attrs.append((target, _value_text(sub.value)))
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) \
                        and not sub.target.id.startswith("_"):
                    ann = ast.unparse(sub.annotation)
                    val = f" = {_value_text(sub.value)}" if sub.value is not None else ""
                    cls.attrs.append((sub.target.id, f"{ann}{val}"))
            mod.classes.append(cls)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            mod.functions.append(ApiFunc(node.name, _signature(node, False), ast.get_docstring(node) or "",
                                         node.lineno))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id.isupper() and not target.id.startswith("_") \
                    and node.value is not None:
                mod.constants.append((target.id, _value_text(node.value), node.lineno))
    if not (mod.doc or mod.classes or mod.functions or mod.constants):
        return None
    return mod


def load_api(tree: Tree) -> list[ApiModule]:
    files = tree.python_files()
    tree.prefetch(files)
    mods = []
    for path in files:
        src = tree.read(path)
        if src is None:
            continue
        mod = parse_module(path, src)
        if mod is not None:
            mods.append(mod)
    return sorted(mods, key=lambda m: m.name)


def doc_md(doc: str) -> str:
    """A docstring as Markdown: reST roles become code, literal-block markers and underlines go."""
    doc = re.sub(r":(?:class|func|meth|mod|attr|data|obj|exc):`~?([^`]+)`", r"``\1``", doc)
    doc = re.sub(r"^(\S.*)\n[-=~^]{3,}[ \t]*$", r"**\1**", doc, flags=re.M)
    doc = re.sub(r"::[ \t]*$", ":", doc, flags=re.M)
    parts = re.split(r"(``.+?``|`[^`]+`)", doc, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("`"):
            parts[i] = "`" + part.strip("`") + "`"
        else:
            parts[i] = part.replace("<", "&lt;").replace(">", "&gt;")
    return "".join(parts)


PACKAGE_TITLES = {
    "jbrowser": "Application", "jbrowser.core": "Core", "jbrowser.models": "Models", "jbrowser.engine": "Web engine",
    "jbrowser.services": "Services", "jbrowser.platform": "Platform (Windows)", "jbrowser.ui": "User interface",
    "jbrowser.ui.dialogs": "Dialogs and tool windows",
}


# ------------------------------------------------------------------------------ generated references
def _comments(source: str) -> dict[int, str]:
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            out[tok.start[0]] = tok.string.lstrip("#").strip()
    return out


def _find_assign(tree_ast: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(tree_ast):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def md_code(text: str) -> str:
    """Text for a table cell inside backticks: code spans already protect ``|`` there."""
    return text.replace("\n", " ").replace("`", "'")


class Generators:
    """Markdown for the generated reference pages of one version."""

    def __init__(self, v: Version, link_source):
        self.v = v
        self.tree = v.tree
        self.src = link_source          # (path, line) -> URL

    def _source(self, path: str) -> str | None:
        return self.tree.read(path)

    # -- settings ----------------------------------------------------------------
    def settings(self) -> str:
        path = "jbrowser/core/settings.py"
        source = self._source(path)
        if not source:
            return "*The settings module is missing in this version.*"
        tree_ast = ast.parse(source)
        comments = _comments(source)
        lines = source.split("\n")
        node = _find_assign(tree_ast, "DEFAULTS")
        if not isinstance(node, ast.Dict):
            return "*No DEFAULTS found.*"
        py_files = self.tree.python_files()
        self.tree.prefetch(py_files)
        groups: list[tuple[str, list]] = []
        current = "General"
        for key_node, value_node in zip(node.keys, node.values):
            if not isinstance(key_node, ast.Constant):
                continue
            ln = key_node.lineno
            back = ln - 1
            while back > node.lineno and lines[back - 1].strip().startswith("#"):
                back -= 1
            heading = [comments[i] for i in range(back + 1, ln) if i in comments and
                       lines[i - 1].strip().startswith("#")]
            if heading:
                current = heading[0].split(" (")[0].rstrip(".")
            if not groups or groups[-1][0] != current:
                groups.append((current, []))
            note = comments.get(ln, "") if not lines[ln - 1].strip().startswith("#") else ""
            try:
                value = json.dumps(ast.literal_eval(value_node), ensure_ascii=False)
            except (ValueError, TypeError):
                value = ast.unparse(value_node)
            if len(value) > 60:
                value = f"[{value[:40]}…]({self.src(path, value_node.lineno)})"
            else:
                value = f"`{md_code(value)}`"
            key = key_node.value
            users = []
            for f in py_files:
                if f != path and f'"{key}"' in (self.tree.read(f) or ""):
                    users.append(f"[{posixpath.basename(f)}]({self.src(f)})")
            used = ", ".join(users[:4]) + (" …" if len(users) > 4 else "")
            groups[-1][1].append(f"| `{key}` | {value} | {md_cell(note)} | {used} |")
        out = [f"{sum(len(g[1]) for g in groups)} settings, from `DEFAULTS` in "
               f"[{path}]({self.src(path, node.lineno)}).", ""]
        for title, rows in groups:
            out += [f"## {title}", "", "| Key | Default | Notes | Read in |", "|---|---|---|---|", *rows, ""]
        return "\n".join(out)

    # -- commands ----------------------------------------------------------------
    def _literal_from_import(self, module_ast: ast.Module, name: str):
        """The literal value of ``name``, defined here or imported from another jbrowser module."""
        node = _find_assign(module_ast, name)
        if node is not None:
            return ast.literal_eval(node)
        for imp in module_ast.body:
            if isinstance(imp, ast.ImportFrom) and imp.module and imp.module.startswith("jbrowser") \
                    and any(a.name == name for a in imp.names):
                src = self.tree.read(imp.module.replace(".", "/") + ".py")
                if src:
                    node = _find_assign(ast.parse(src), name)
                    if node is not None:
                        return ast.literal_eval(node)
        raise ValueError(name)

    def _iterate(self, module_ast: ast.Module, it: ast.AST) -> list | None:
        try:
            if isinstance(it, (ast.List, ast.Tuple)):
                return ast.literal_eval(it)
            if isinstance(it, ast.Name):
                value = self._literal_from_import(module_ast, it.id)
                return list(value.items()) if isinstance(value, dict) else list(value)
            if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range":
                return list(range(*[ast.literal_eval(a) for a in it.args]))
            if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and isinstance(it.func.value, ast.Name):
                value = self._literal_from_import(module_ast, it.func.value.id)
                if it.func.attr == "items":
                    return list(value.items())
                if it.func.attr == "keys":
                    return list(value.keys())
        except (ValueError, TypeError, SyntaxError):
            return None
        return None

    @staticmethod
    def _bind(target: ast.AST, value, env: dict) -> None:
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (tuple, list)):
            for t, v in zip(target.elts, value):
                Generators._bind(t, v, env)

    @staticmethod
    def _text(node: ast.AST, env: dict) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            out = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    out.append(str(part.value))
                elif isinstance(part, ast.FormattedValue):
                    expr = ast.unparse(part.value)
                    if isinstance(part.value, ast.Name) and part.value.id in env:
                        out.append(str(env[part.value.id]))
                    else:
                        out.append("{" + expr + "}")
            return "".join(out)
        return None

    def commands(self) -> list[dict]:
        path = "jbrowser/ui/actions.py"
        source = self._source(path)
        if not source:
            return []
        module_ast = ast.parse(source)
        func = next((n for n in module_ast.body if isinstance(n, ast.FunctionDef) and n.name == "register_commands"),
                    None)
        if func is None:
            return []
        categories: dict[str, str] = {}
        result: list[dict] = []

        def visit(stmts: list, env: dict) -> None:
            for st in stmts:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                        and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    categories[st.targets[0].id] = st.value.value
                elif isinstance(st, ast.For):
                    values = self._iterate(module_ast, st.iter)
                    if values is None:
                        visit(st.body, dict(env, __pattern__=ast.unparse(st.iter)))
                    else:
                        for value in values:
                            inner = dict(env)
                            self._bind(st.target, value, inner)
                            visit(st.body, inner)
                elif isinstance(st, ast.If):
                    visit(st.body, env)
                    visit(st.orelse, env)
                elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
                    call = st.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == "add" and len(call.args) >= 3:
                        cid = self._text(call.args[0], env)
                        title = self._text(call.args[1], env)
                        cat = call.args[2]
                        category = categories.get(cat.id, cat.id) if isinstance(cat, ast.Name) else \
                            self._text(cat, env) or ast.unparse(cat)
                        kw = {k.arg: k.value for k in call.keywords if k.arg}
                        shortcuts = []
                        if "shortcuts" in kw:
                            try:
                                shortcuts = list(ast.literal_eval(kw["shortcuts"]))
                            except ValueError:
                                shortcuts = [ast.unparse(kw["shortcuts"])]
                        palette = not (isinstance(kw.get("palette"), ast.Constant) and kw["palette"].value is False)
                        keywords = self._text(kw["keywords"], env) if "keywords" in kw else ""
                        result.append({"id": cid or ast.unparse(call.args[0]), "title": title or "",
                                       "category": category, "shortcuts": shortcuts, "palette": palette,
                                       "keywords": keywords or "", "line": call.lineno,
                                       "pattern": "{" in (cid or "") and env.get("__pattern__", "")})
        visit(func.body, {})
        return result

    def commands_page(self) -> str:
        cmds = self.commands()
        if not cmds:
            return "*No commands found in this version.*"
        path = "jbrowser/ui/actions.py"
        out = [f"{len(cmds)} commands, registered in [{path}]({self.src(path)}) by `register_commands()`. "
               "Each one can be run from the Lazy Toolbar (unless marked *hidden*), by its shortcut, and from code "
               "with `ctx.commands.run(id)`.", ""]
        by_cat: dict[str, list] = {}
        for c in cmds:
            by_cat.setdefault(c["category"], []).append(c)
        for cat, items in by_cat.items():
            out += [f"## {cat}", "", "| ID | Title | Shortcut | |", "|---|---|---|---|"]
            for c in items:
                keys = " ".join(f"<kbd>{esc(s)}</kbd>" for s in c["shortcuts"])
                flags = []
                if not c["palette"]:
                    flags.append("hidden")
                if c["pattern"]:
                    flags.append(f"one per item of `{md_code(c['pattern'])}`")
                src = f"[source]({self.src(path, c['line'])})"
                out.append(f"| `{md_code(c['id'])}` | {md_cell(c['title'])} | {keys} | "
                           f"{md_cell(', '.join(flags))} {src} |")
            out.append("")
        return "\n".join(out)

    # -- shortcuts ---------------------------------------------------------------
    def shortcuts_page(self) -> str:
        cmds = [c for c in self.commands() if c["shortcuts"]]
        out = ["Every keyboard shortcut in this version, generated from the command registry "
               "([jbrowser/ui/actions.py](" + self.src("jbrowser/ui/actions.py") + ")). "
               "In JBrowser, <kbd>Ctrl</kbd>+<kbd>/</kbd> shows the same list.", ""]
        by_cat: dict[str, list] = {}
        for c in cmds:
            by_cat.setdefault(c["category"], []).append(c)
        for cat, items in by_cat.items():
            out += [f"## {cat}", "", "| Action | Keys | Command |", "|---|---|---|"]
            for c in items:
                keys = " or ".join("+".join(f"<kbd>{esc(k)}</kbd>" for k in s.split("+")) for s in c["shortcuts"])
                out.append(f"| {md_cell(c['title'])} | {keys} | `{md_code(c['id'])}` |")
            out.append("")
        extra_src = self._source("jbrowser/ui/hotkeys.py")
        if extra_src:
            node = _find_assign(ast.parse(extra_src), "EXTRA")
            try:
                extra = ast.literal_eval(node) if node is not None else []
            except ValueError:
                extra = []
            if extra:
                out += ["## Mouse and gestures", "",
                        "Handled directly by widgets rather than commands "
                        f"(`EXTRA` in [jbrowser/ui/hotkeys.py]({self.src('jbrowser/ui/hotkeys.py')})).", "",
                        "| Area | Action | Input |", "|---|---|---|"]
                for row in extra:
                    if len(row) >= 3:
                        out.append(f"| {md_cell(row[0])} | {md_cell(row[1])} | {md_cell(row[2])} |")
                out.append("")
        return "\n".join(out)

    # -- command line ------------------------------------------------------------
    ENV_NOTES = {
        "JBROWSER_SKIP_WELCOME": "Don't show the first-run welcome (useful for test profiles).",
        "JBROWSER_SKIP_UPDATES": "Don't check GitHub for updates.",
        "JBROWSER_CONSOLE_LOG": "Also print the log to the console (like `--debug`, without verbose logging).",
        "JBROWSER_ADDED_CHROMIUM_FLAGS": "Internal: the Chromium flags JBrowser added itself, so a restarted copy "
                                         "can drop them again.",
        "QTWEBENGINE_CHROMIUM_FLAGS": "Extra Chromium switches (JBrowser appends its own). "
                                      "`--disable-gpu` helps with blank pages on unusual GPUs.",
        "QT_WIDGETS_RHI": "Set to `1` by JBrowser: widget windows are composited with Direct3D from the start.",
        "QT_WIDGETS_RHI_BACKEND": "Set to `d3d11` by JBrowser.",
        "QT_MEDIA_BACKEND": "Set to `windows` by JBrowser: sound effects use the native backend, not FFmpeg.",
        "QTWEBENGINE_REMOTE_DEBUGGING": "Qt: open a Chrome DevTools Protocol endpoint on this port (testing).",
        "APPDATA": "Where roaming data lives (`%APPDATA%\\JBrowser`).",
        "LOCALAPPDATA": "Where caches live (`%LOCALAPPDATA%\\JBrowser\\Cache`).",
    }

    def cli_page(self) -> str:
        path = "jbrowser/app.py"
        source = self._source(path) or ""
        out = ["How JBrowser is started, generated from `_parse_args()` in "
               f"[{path}]({self.src(path)}).", "", "```powershell",
               "JBrowser.exe [URL ...] [--profile-dir PATH] [--incognito] [--no-restore] [--debug]",
               ".\\.venv\\Scripts\\python.exe main.py [same options]      # from source", "```", "",
               "## Options", "", "| Option | Meaning |", "|---|---|"]
        internal = []
        for node in ast.walk(ast.parse(source)) if source else []:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                names = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if not names:
                    continue
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                help_node = kw.get("help")
                help_text = help_node.value if isinstance(help_node, ast.Constant) else ""
                if isinstance(help_node, ast.Attribute) and help_node.attr == "SUPPRESS":
                    internal.append(names)
                    continue
                action = kw["action"].value if isinstance(kw.get("action"), ast.Constant) else ""
                meta = names[0].strip("-").upper().replace("-", "_")
                if not names[0].startswith("-"):
                    shown = f"`{meta} …`"                                     # positional, nargs="*"
                elif action.startswith("store_"):
                    shown = ", ".join(f"`{n}`" for n in names)
                else:
                    shown = ", ".join(f"`{n} {meta}`" for n in names)
                out.append(f"| {shown} | {md_cell(help_text)} |")
        out.append("")
        if internal:
            out += ["Internal options (used by JBrowser itself): " +
                    ", ".join(f"`{n[0]}`" for n in internal) +
                    ". `--wait-pid PID` makes a restarted copy wait until the old process has exited.", ""]
        out += ["Unknown options are passed on to Qt and Chromium unchanged.", "",
                "## Environment variables", "", "| Variable | Read in | Meaning |", "|---|---|---|"]
        found: dict[str, set[str]] = {}
        pattern = re.compile(r"""os\.environ(?:\.get|\.setdefault)?\s*[\(\[]\s*["']([A-Z][A-Z0-9_]+)["']""")
        py_files = self.tree.python_files()
        self.tree.prefetch(py_files)
        for f in py_files:
            for name in pattern.findall(self.tree.read(f) or ""):
                found.setdefault(name, set()).add(f)
        for name in sorted(found):
            files = ", ".join(f"[{posixpath.basename(f)}]({self.src(f)})" for f in sorted(found[name]))
            out.append(f"| `{name}` | {files} | {md_cell(self.ENV_NOTES.get(name, ''))} |")
        out.append("")
        return "\n".join(out)

    # -- data files --------------------------------------------------------------
    FILE_NOTES = {
        "settings_file": "Every preference (`core/settings.py`), written 0.4 s after the last change.",
        "session_file": "Spaces, cards, layout and each card's back/forward history (`services/session.py`).",
        "history_db": "Browsing history, SQLite in WAL mode (`services/history.py`).",
        "bookmarks_file": "Bookmarks and the bookmarks bar (`services/bookmarks.py`).",
        "vault_file": "The encrypted password vault (`services/vault.py`).",
        "downloads_file": "The downloads list (`services/downloads.py`).",
        "userscripts_file": "User scripts and styles (`services/userscripts.py`).",
        "blocklist_file": "Tracker and ad domains from the downloaded lists (`services/privacy.py`).",
        "threatlist_file": "Phishing and malware hosts (`services/threats.py`).",
        "reset_marker": "Present when a factory reset is pending; the next start erases everything.",
        "archive_file": "The Archive: cards closed in the last 48 hours (`services/archive.py`).",
        "favourites_file": "Sidebar favourites (`services/favourites.py`).",
        "profiles": "One Chromium profile folder per space: cookies, storage, permissions.",
        "profile_cache": "Each space's HTTP cache.",
        "favicons": "The favicon cache (never written for incognito spaces).",
        "logs": "`jbrowser.log`, rotated at 2 MB, three old copies kept.",
        "cache": "Disposable data. Never roams with a Windows profile.",
        "data": "Everything that roams with the Windows profile.",
    }

    def data_files_page(self) -> str:
        path = "jbrowser/paths.py"
        source = self._source(path)
        if not source:
            return ""
        tree_ast = ast.parse(source)
        rows = []
        owned = []
        for node in ast.walk(tree_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                for st in ast.walk(node):
                    if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Attribute) \
                            and isinstance(st.targets[0].value, ast.Name) and st.targets[0].value.id == "self":
                        attr = st.targets[0].attr
                        expr = ast.unparse(st.value)
                        if attr in ("portable",):
                            continue
                        where = expr.replace("self.data", "<data>").replace("self.cache", "<cache>") \
                            .replace(" / ", "\\").replace('"', "").replace("'", "")
                        if attr in ("data", "cache"):
                            continue
                        rows.append(f"| `{attr}` | `{md_code(where)}` | {md_cell(self.FILE_NOTES.get(attr, ''))} |")
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "OWNED" for t in node.targets):
                try:
                    owned = list(ast.literal_eval(node.value))
                except ValueError:
                    owned = []
        out = [f"Where JBrowser keeps its data, generated from `AppPaths` in [{path}]({self.src(path)}).", "",
               "| Folder | Normally | With `--profile-dir PATH` |", "|---|---|---|",
               "| `<data>` | `%APPDATA%\\JBrowser` | `PATH` |",
               "| `<cache>` | `%LOCALAPPDATA%\\JBrowser\\Cache` | `PATH\\Cache` |", "",
               "## Files and folders", "", "| `AppPaths` attribute | Location | Contents |", "|---|---|---|",
               *rows, ""]
        extra = [n for n in owned if n not in ("Profiles", "Logs", "Cache", "JBrowser") and not any(
            n in r for r in rows)]
        if extra:
            out += ["Other files JBrowser owns in `<data>` (`AppPaths.OWNED`, removed by a factory reset): " +
                    ", ".join(f"`{n}`" for n in extra) + ".", ""]
        return "\n".join(out)

    # -- the API index -----------------------------------------------------------
    def api_index(self, modules: list[ApiModule], link_module) -> str:
        out = [f"Every module of the `jbrowser` package in {'this version' if not self.v.is_main else 'main'}: "
               f"{len(modules)} modules, {sum(len(m.classes) for m in modules)} classes. Each page lists the "
               "public classes, signals, methods, functions and constants with their docstrings, and links to "
               "the source.", ""]
        by_pkg: dict[str, list[ApiModule]] = {}
        for m in modules:
            by_pkg.setdefault(m.package, []).append(m)
        for pkg in sorted(by_pkg, key=lambda p: list(PACKAGE_TITLES).index(p) if p in PACKAGE_TITLES else 99):
            out += [f"## {PACKAGE_TITLES.get(pkg, pkg)} {{: #{pkg} }}", "", f"`{pkg}`", "",
                    "| Module | Summary |", "|---|---|"]
            for m in by_pkg[pkg]:
                out.append(f"| [`{m.name}`]({link_module(m.name)}) | {md_cell(doc_md(m.summary))} |")
            out.append("")
        return "\n".join(out)


def api_module_md(mod: ApiModule, src) -> str:
    out = [f'<p class="api-meta"><a href="{esc(src(mod.path))}">{esc(mod.path)}</a> · {mod.lines:,} lines</p>', ""]
    if mod.doc:
        out += [doc_md(mod.doc), ""]
    if mod.constants:
        out += ["## Constants {: #constants }", "", "| Name | Value |", "|---|---|"]
        for name, value, line in mod.constants:
            out.append(f"| [`{name}`]({src(mod.path, line)}) | `{md_code(value)}` |")
        out.append("")
    for cls in mod.classes:
        bases = f"({', '.join(cls.bases)})" if cls.bases else ""
        out += [f"## {cls.name} {{: #{cls.name} }}", "",
                f'<pre class="sig"><code><span class="k">class</span> <b>{esc(cls.name)}</b>{esc(bases)}</code>'
                f'<a class="src" href="{esc(src(mod.path, cls.line))}">source</a></pre>', ""]
        if cls.init_sig and cls.init_sig != "()":
            out += [f'<pre class="sig ctor"><code>{esc(cls.name)}{esc(cls.init_sig)}</code></pre>', ""]
        if cls.doc:
            out += [doc_md(cls.doc), ""]
        if cls.signals:
            out += ['<p class="api-label">Signals</p>', "", "| Signal | Arguments |", "|---|---|"]
            for name, args in cls.signals:
                out.append(f"| `{name}` | `{md_code(args)}` |")
            out.append("")
        if cls.attrs:
            out += ['<p class="api-label">Attributes</p>', "", "| Name | Value |", "|---|---|"]
            for name, value in cls.attrs:
                out.append(f"| `{name}` | `{md_code(value)}` |")
            out.append("")
        for m in cls.methods:
            label = {"static": "static ", "class": "class method ", "property": "property "}.get(m.kind, "")
            sig = "" if m.kind == "property" else m.sig
            out += [f"### {cls.name}.{m.name} {{: #{cls.name}.{m.name} }}", "",
                    f'<pre class="sig"><code><span class="k">{esc(label)}</span><b>{esc(m.name)}</b>{esc(sig)}'
                    f'</code><a class="src" href="{esc(src(mod.path, m.line))}">source</a></pre>', ""]
            if m.doc:
                out += [doc_md(m.doc), ""]
        if cls.overrides:
            out += ['<p class="api-overrides">Qt overrides: ' +
                    ", ".join(f"<code>{esc(o)}</code>" for o in cls.overrides) + "</p>", ""]
    if mod.functions:
        out += ["## Functions {: #functions }", ""]
        for f in mod.functions:
            out += [f"### {f.name} {{: #{f.name} }}", "",
                    f'<pre class="sig"><code><b>{esc(f.name)}</b>{esc(f.sig)}</code>'
                    f'<a class="src" href="{esc(src(mod.path, f.line))}">source</a></pre>', ""]
            if f.doc:
                out += [doc_md(f.doc), ""]
    return "\n".join(out)


# ------------------------------------------------------------------------------ changelog
@dataclass
class Release:
    version: str
    date: str
    body: str


def parse_changelog(text: str) -> tuple[str, list[Release]]:
    parts = re.split(r"(?m)^## \[([^\]]+)\](?:\s*-\s*(\S+))?[^\n]*\n", text)
    intro = parts[0]
    releases = []
    for i in range(1, len(parts), 3):
        releases.append(Release(parts[i], parts[i + 1] or "", parts[i + 2].strip()))
    return intro, releases


def highlights(release: Release, limit: int = 6) -> list[str]:
    """The bold lead-ins of a release's bullet points ("Gallery.", "Colour tints.")."""
    items = []
    for line in release.body.split("\n"):
        m = re.match(r"^- \*\*(.+?)\*\*", line)
        if m:
            items.append(m[1].rstrip(".:"))
        if len(items) >= limit:
            break
    return items


# ------------------------------------------------------------------------------ the builder
class Site:
    def __init__(self, out: Path, offline: bool):
        self.out = out
        self.git = find_git()
        if not self.git:
            print("  (git not found: building the docs for main only)")
        self.versions = discover_versions(self.git)
        work = Tree(self.git, None)
        self.ident = identity(work.read("jbrowser/__init__.py") or "")
        self.repo = self.ident.get("GITHUB_REPO", "The-JBrowser-Team/JBrowser")
        self.repo_url = f"https://github.com/{self.repo}"
        self.youtube_url = self.ident.get("YOUTUBE_URL", "https://www.youtube.com/@TheJBrowserTeam")
        owner, name = self.repo.split("/")
        # The site's public address: the JBROWSER_SITE_URL variable (the SITE_URL repository variable in
        # pages.yml, e.g. https://jbrowser.app/), or the GitHub Pages address of the repository.
        self.site_url = (os.environ.get("JBROWSER_SITE_URL") or f"https://{owner.lower()}.github.io/{name}/").strip()
        if not self.site_url.endswith("/"):
            self.site_url += "/"
        self.base_path = urllib.parse.urlsplit(self.site_url).path or "/"
        self.releases_info = release_details(self.repo, offline)
        self.nav = json.loads((DOCS_SRC / "nav.json").read_text(encoding="utf-8"))
        self.search_entries: dict[str, list] = {}
        self.sitemap: list[str] = []
        self.missing: set[str] = set()     # navigation pages without a Markdown file
        self.broken = 0                    # broken links found by check_links()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.changelog_intro, self.changelog = parse_changelog(changelog)
        for v in self.versions:
            info = self.releases_info.get(v.ref)
            rel_ = next((r for r in self.changelog if r.version == v.id), None)
            v.date = (info or {}).get("date") or (rel_.date if rel_ else "")

    # -- links ------------------------------------------------------------------
    def source_link(self, v: Version):
        def link(path: str, line: int | None = None) -> str:
            kind = "tree" if path.endswith("/") else "blob"
            return f"{self.repo_url}/{kind}/{v.ref}/{path.rstrip('/')}" + (f"#L{line}" if line else "")
        return link

    @property
    def latest(self) -> Version:
        return next((v for v in self.versions if v.latest), self.versions[-1])

    def download(self) -> dict:
        v = self.latest
        tag = v.ref if not v.is_main else ""
        number = v.number_text
        name = f"JBrowser-Setup-{number}.exe"
        info = self.releases_info.get(tag, {})
        url, size = info.get("assets", {}).get(name, (f"{self.repo_url}/releases/download/{tag}/{name}", 0))
        return {"version": number, "tag": tag, "exe_name": name, "exe_url": url, "size": human_size(size),
                "date": pretty_date(v.date) if v.date else "", "release_url": f"{self.repo_url}/releases/tag/{tag}"}

    # -- build ------------------------------------------------------------------
    def build(self) -> None:
        clear_folder(self.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.copy_static()
        self.build_home()
        self.build_download()
        self.build_pages()
        self.build_changelog()
        self.build_docs()
        self.build_404()
        self.build_sitemap()
        write(self.out / ".nojekyll", "")
        self.stamp_assets()
        self.broken = self.check_links()

    def stamp_assets(self) -> None:
        """Adds ?v=<content hash> to every stylesheet and script link, so browsers fetch a changed file
        at once instead of using the copy GitHub Pages lets them cache for 10 minutes."""
        stamps = {p.relative_to(self.out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()[:10]
                  for p in (self.out / "static").rglob("*") if p.suffix in (".css", ".js")}
        pattern = re.compile(r'((?:href|src)="[^"?#]*?(static/(?:css|js)/[\w.-]+\.(?:css|js)))"')
        for page in self.out.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            stamped = pattern.sub(lambda m: f'{m[1]}?v={stamps[m[2]]}"' if m[2] in stamps else m[0], text)
            if stamped != text:
                page.write_text(stamped, encoding="utf-8")

    def check_links(self) -> int:
        """Every relative link and #anchor in the built site must point at something that exists."""
        ids: dict[Path, set[str]] = {}

        def anchors(path: Path) -> set[str]:
            if path not in ids:
                ids[path] = set(re.findall(r'\sid="([^"]+)"', path.read_text(encoding="utf-8")))
            return ids[path]

        broken: list[str] = []
        for page in self.out.rglob("*.html"):
            if page.name == "404.html":
                continue            # absolute links, resolved by GitHub Pages
            text = page.read_text(encoding="utf-8")
            for url in re.findall(r'href="([^"]+)"', text):
                url = html.unescape(url)
                if re.match(r"^[a-z][a-z0-9+.\-]*:", url) or url.startswith("//"):
                    continue        # http:, https:, mailto: ...
                path, _, frag = url.partition("#")
                path = path.partition("?")[0]
                target = (page.parent / path).resolve() if path else page
                if target.is_dir():
                    target = target / "index.html"
                if not target.exists():
                    broken.append(f"{page.relative_to(self.out).as_posix()}: {url}")
                elif frag and target.suffix == ".html" and frag not in anchors(target):
                    broken.append(f"{page.relative_to(self.out).as_posix()}: {url} (no such anchor)")
        for b in sorted(set(broken))[:60]:
            print(f"  ! broken link {b}")
        if len(set(broken)) > 60:
            print(f"  ! … {len(set(broken)) - 60} more")
        print(f"  links checked: {len(set(broken))} broken")
        return len(set(broken))

    def copy_static(self) -> None:
        shutil.copytree(STATIC, self.out / "static", dirs_exist_ok=True)
        img = self.out / "static" / "img"
        img.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "assets" / "jbrowser.png", img / "jbrowser.png")
        shutil.copy2(ROOT / "assets" / "jbrowser.ico", self.out / "favicon.ico")
        # Web app manifest: browsers and search engines read the site's name and icons from it.
        icons = [{"src": f"static/img/icons/{name}", "sizes": f"{size}x{size}", "type": "image/png"}
                 for name, size in (("favicon-48.png", 48), ("favicon-96.png", 96), ("favicon-192.png", 192),
                                    ("icon-512.png", 512))]
        write(self.out / "site.webmanifest", json.dumps({
            "name": "JBrowser", "short_name": "JBrowser",
            "description": "A spatial, privacy-focused web browser for Windows.",
            "start_url": "./", "display": "browser", "theme_color": "#8a5cff", "background_color": "#0e0e14",
            "icons": icons}, indent=1))
        light = HtmlFormatter(style="default").get_style_defs(':root[data-theme="light"] .highlight')
        dark = HtmlFormatter(style="github-dark").get_style_defs(':root[data-theme="dark"] .highlight')
        write(self.out / "static" / "css" / "pygments.css",
              "/* Generated by tools/build_site.py from Pygments styles. */\n" + light + "\n" + dark + "\n")

    def common(self, page: str, title: str, description: str) -> dict:
        root = root_of(page)
        d = self.download()
        return {"root": root, "title": esc(title), "description": esc(description), "repo_url": self.repo_url,
                "youtube_url": self.youtube_url,
                "year": str(datetime.now().year),
                "company": esc(self.ident.get("COMPANY", "The JBrowser Team")),
                "latest_version": d["version"], "exe_url": esc(d["exe_url"]), "exe_name": esc(d["exe_name"]),
                "exe_size": d["size"], "release_date": d["date"], "release_url": esc(d["release_url"]),
                "repo": self.repo, "docs_home": f"{root}docs/latest/index.html",
                "canonical": self.site_url + (page[:-len("index.html")] if page.endswith("index.html") else page),
                "og_image": self.site_url + "static/img/shots/og-image.jpg", "head_extra": ""}

    def software_json_ld(self) -> str:
        """schema.org data for the home page, so search engines know what JBrowser is: the website (its
        name), the team behind it (with the logo) and the app (a Windows desktop browser, not one of the
        mobile apps with a similar name)."""
        d = self.download()
        team = self.ident.get("COMPANY", "The JBrowser Team")
        org_id = self.site_url + "#team"
        data = {"@context": "https://schema.org", "@graph": [
            {"@type": "WebSite", "@id": self.site_url + "#website", "url": self.site_url, "name": "JBrowser",
             "alternateName": ["JBrowser for Windows", "jbrowser.app"], "publisher": {"@id": org_id}},
            {"@type": "Organization", "@id": org_id, "name": team, "url": self.site_url,
             "logo": {"@type": "ImageObject", "url": self.site_url + "static/img/icons/icon-512.png",
                      "width": 512, "height": 512},
             "sameAs": [self.repo_url, self.youtube_url]},
            {"@type": "SoftwareApplication", "name": "JBrowser",
             "applicationCategory": "BrowserApplication", "applicationSubCategory": "Web browser",
             "operatingSystem": "Windows 10, Windows 11",
             "description": "A spatial, privacy-focused web browser for Windows desktops: pages side by side on one "
                            "canvas, separate spaces, built-in ad and tracker blocking. Free and open source.",
             "url": self.site_url, "downloadUrl": self.site_url + "download/", "softwareVersion": d["version"],
             "license": "https://www.gnu.org/licenses/gpl-3.0.html", "isAccessibleForFree": True,
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
             "image": self.site_url + "static/img/shots/og-image.jpg",
             "screenshot": self.site_url + "static/img/shots/hero-dark-1920.webp",
             "author": {"@id": org_id}, "publisher": {"@id": org_id},
             "codeRepository": self.repo_url},
        ]}
        text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        return f'<script type="application/ld+json">{text}</script>'

    def build_home(self) -> None:
        page = "index.html"
        latest = next((r for r in self.changelog if r.version == self.latest.id), None)
        items = highlights(latest) if latest else []
        news = "\n".join(f"<li>{esc(i)}</li>" for i in items)
        values = self.common(page, "JBrowser: a spatial, privacy-focused browser for Windows 11",
                             "JBrowser replaces the tab strip with an infinite canvas of web cards, organised into "
                             "isolated Spaces, with built-in ad and tracker blocking. Free and open source.")
        values.update({"news": news, "size_note": f" · {self.download()['size']}" if self.download()["size"] else "",
                       "head_extra": self.software_json_ld()})
        write(self.out / page, render("home.html", values))
        self.sitemap.append("")

    def build_download(self) -> None:
        page = "download/index.html"
        values = self.common(page, "Download JBrowser", "Download the newest JBrowser installer for Windows.")
        write(self.out / page, render("download.html", values))
        self.sitemap.append("download/")

    def build_changelog(self) -> None:
        page = "changelog/index.html"
        tags = {v.ref for v in self.versions if not v.is_main}
        sections, side = [], []
        for r in self.changelog:
            anchor = "unreleased" if r.version.lower() == "unreleased" else "v" + r.version.replace(".", "-")
            body, _toc = md_to_html(re.sub(r"(?m)^### ", "#### ", r.body), toc_depth="0", permalinks=False)
            body = self.fix_links(body, page, None)
            links = []
            tag = f"v{r.version}"
            if tag in tags or tag in self.releases_info:
                links.append(f'<a href="{self.repo_url}/releases/tag/{tag}">Release on GitHub</a>')
                exe = self.releases_info.get(tag, {}).get("assets", {}).get(f"JBrowser-Setup-{r.version}.exe")
                if exe:
                    links.append(f'<a href="{esc(exe[0])}">Installer ({human_size(exe[1])})</a>')
                links.append(f'<a href="../docs/{r.version}/index.html">Documentation</a>'
                             if version_tuple(r.version) and version_tuple(r.version) >= OLDEST_DOCS else "")
            meta = f'<span class="date">{esc(pretty_date(r.date))}</span>' if r.date else ""
            badge = '<span class="badge badge-new">Latest</span>' if r.version == self.latest.id else ""
            sections.append(
                f'<section class="release" id="{anchor}"><header><h2><a href="#{anchor}">{esc(r.version)}</a>'
                f'{badge}</h2>{meta}<div class="release-links">{"".join(x for x in links if x)}</div></header>'
                f'<div class="prose">{body}</div></section>')
            side.append(f'<li><a href="#{anchor}">{esc(r.version)}</a>'
                        f'<span>{esc(pretty_date(r.date)) if r.date else ""}</span></li>')
        intro_html, _ = md_to_html(self.changelog_intro.split("\n", 1)[1] if "\n" in self.changelog_intro else "",
                                   toc_depth="0", permalinks=False)
        values = self.common(page, "Changelog · JBrowser", "Every change to JBrowser, release by release.")
        values.update({"releases": "\n".join(sections), "release_nav": "\n".join(side),
                       "intro": self.fix_links(intro_html, page, None)})
        write(self.out / page, render("changelog.html", values))
        self.sitemap.append("changelog/")

    def build_pages(self) -> None:
        """site/pages/<name>.md → <name>/index.html: plain text pages such as the code signing policy.
        Front matter: title (the heading), kicker, lead and description."""
        for src in sorted((SRC / "pages").glob("*.md")):
            text = src.read_text(encoding="utf-8")
            meta: dict[str, str] = {}
            m = _FRONT.match(text)
            if m:
                for line in m[1].splitlines():
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
                text = text[m.end():]
            page = f"{src.stem}/index.html"
            body, _ = md_to_html(text, toc_depth="0", permalinks=False)
            title = meta.get("title", src.stem)
            values = self.common(page, f"{title} · JBrowser", meta.get("description", ""))
            values.update({"kicker": esc(meta.get("kicker", "JBrowser")), "heading": esc(title),
                           "lead": esc(meta.get("lead", "")), "body": self.fix_links(body, page, None)})
            write(self.out / page, render("page.html", values))
            self.sitemap.append(f"{src.stem}/")

    def build_404(self) -> None:
        values = self.common("404.html", "Page not found · JBrowser", "")
        values["root"] = self.base_path
        values["docs_home"] = f"{self.base_path}docs/latest/index.html"
        write(self.out / "404.html", render("404.html", values))

    def build_sitemap(self) -> None:
        urls = "\n".join(f"  <url><loc>{esc(self.site_url + u)}</loc></url>" for u in self.sitemap)
        write(self.out / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>\n")
        write(self.out / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.site_url}sitemap.xml\n")
        # IndexNow (Bing, Yandex, Seznam, Naver): the key file proves the site is ours; the Pages workflow
        # sends the sitemap's pages to api.indexnow.org after each deploy (tools/indexnow.py).
        write(self.out / f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY + "\n")
        # security.txt (RFC 9116): where to report vulnerabilities.
        expires = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
        write(self.out / ".well-known" / "security.txt",
              f"Contact: {self.repo_url}/security/advisories/new\n"
              f"Policy: {self.repo_url}/blob/main/SECURITY.md\n"
              f"Canonical: {self.site_url}.well-known/security.txt\n"
              f"Preferred-Languages: en\nExpires: {expires}\n")
        host = urllib.parse.urlsplit(self.site_url).hostname or ""
        if not host.endswith(".github.io"):
            write(self.out / "CNAME", host + "\n")          # the custom domain (also set in the repository)

    # -- link rewriting ---------------------------------------------------------
    def fix_links(self, body: str, page: str, v: Version | None, api_names: set[str] | None = None) -> str:
        src = self.source_link(v) if v else None

        def fix(m: re.Match) -> str:
            url = html.unescape(m[2])
            if url.startswith("source:") and src:
                path, _, frag = url[len("source:"):].partition("#")
                new = src(path) + (f"#{frag}" if frag else "")
            elif url.startswith("api:") and api_names is not None:
                target = url[len("api:"):]
                parts = target.split(".")
                module = next((".".join(parts[:i]) for i in range(len(parts), 0, -1)
                               if ".".join(parts[:i]) in api_names), None)
                if module is None:
                    print(f"  ! unknown API link {target!r} in {page}")
                    new = "#"
                else:
                    anchor = ".".join(parts[len(module.split(".")):])
                    new = rel(page, f"{self.docs_dir(v, page)}api/{module}.html") + (f"#{anchor}" if anchor else "")
            elif v is None and re.match(r"^[\w.\-][\w./\-]*$", url) and not url.startswith(("http", "mailto")):
                # Changelog and other repository documents: their relative links point into the repository.
                new = f"{self.repo_url}/blob/main/{posixpath.normpath(url)}"
            elif re.match(r"^[\w./\-]+\.md(#.*)?$", url) and not url.startswith(("http", "/")):
                path, _, frag = url.partition("#")
                new = path[:-3] + ".html" + (f"#{frag}" if frag else "")
            elif url.startswith("repo:"):
                new = self.repo_url + "/" + url[len("repo:"):]
            else:
                return m[0]
            return f'{m[1]}"{esc(new)}"'
        body = re.sub(r'(href=)"([^"]*)"', fix, body)
        body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        return body

    @staticmethod
    def docs_dir(v: Version, page: str) -> str:
        """``docs/<dir>/`` of the page being built (the latest release is built twice)."""
        parts = page.split("/")
        return f"docs/{parts[1]}/" if len(parts) > 1 and parts[0] == "docs" else f"docs/{v.id}/"

    # -- docs -------------------------------------------------------------------
    def build_docs(self) -> None:
        manifest = {"latest": self.latest.id, "versions": []}
        for v in self.versions:
            print(f"  docs {v.label}")
            pages = self.build_version(v, v.id)
            if v.latest:
                self.build_version(v, "latest")
            manifest["versions"].append({"id": v.id, "label": v.label, "latest": v.latest,
                                         "date": pretty_date(v.date) if v.date else "", "pages": pages})
        write(self.out / "docs" / "versions.json", json.dumps(manifest, indent=1))
        write(self.out / "docs" / "index.html", render("redirect.html", {
            "target": "latest/index.html", "title": "JBrowser documentation"}))

    def build_version(self, v: Version, dir_id: str) -> list[str]:
        """Render every documentation page of ``v`` into docs/<dir_id>/. Returns the page list."""
        prefix = f"docs/{dir_id}/"
        gen = Generators(v, self.source_link(v))
        modules = load_api(v.tree)
        api_names = {m.name for m in modules}
        pages: list[dict] = []          # {slug, title, section, html_path, body, toc, source}
        nav_sections = []
        for section in self.nav["sections"]:
            entries = []
            for slug in section["pages"]:
                page = self.load_page(slug, v, gen, modules, prefix)
                if page is None:
                    continue
                page["section"] = section["title"]
                pages.append(page)
                entries.append(page)
            if entries:
                nav_sections.append((section["title"], entries))
        # API module pages (not in the navigation; reached from the API index)
        api_pages = []
        for mod in modules:
            md_text = api_module_md(mod, self.source_link(v))
            api_pages.append({"slug": f"api/{mod.name}", "title": mod.name, "md": md_text, "section": "Reference",
                              "nav_title": mod.name, "toc_depth": "2", "api": mod,
                              "edit": self.source_link(v)(mod.path), "edit_label": "View source"})
        search = []
        order = [p for p in pages]
        for i, p in enumerate(order + api_pages):
            out_path = prefix + p["slug"] + ".html"
            body, toc = md_to_html(p["md"], p.get("toc_depth", "2-3"))
            body = self.fix_links(body, out_path, v, api_names)
            in_nav = i < len(order)
            prev_p = order[i - 1] if in_nav and i > 0 else None
            next_p = order[i + 1] if in_nav and i + 1 < len(order) else None
            html_text = self.render_doc(v, dir_id, p, out_path, body, toc, nav_sections, prev_p, next_p, modules)
            write(self.out / out_path, html_text)
            if dir_id == v.id or dir_id == "latest":
                entry = {"t": p["title"], "u": p["slug"] + ".html", "s": p["section"],
                         "h": [t["name"] for t in _flatten_toc(toc)][:40], "b": plain_text(body)[:2500]}
                if "api" in p:
                    entry["b"] = p["api"].summary[:300]
                    for cls in p["api"].classes:
                        search.append({"t": cls.name, "u": f"{p['slug']}.html#{cls.name}", "s": p["title"],
                                       "h": [m.name for m in cls.methods][:30],
                                       "b": cls.doc.split("\n\n")[0][:300]})
                    for fn in p["api"].functions:
                        search.append({"t": fn.name + "()", "u": f"{p['slug']}.html#{fn.name}", "s": p["title"],
                                       "h": [], "b": fn.doc.split("\n\n")[0][:300]})
                search.append(entry)
            if dir_id == "latest" and in_nav:
                self.sitemap.append(out_path)
        write(self.out / prefix / "search.json", json.dumps(search, ensure_ascii=False, separators=(",", ":")))
        return [p["slug"] + ".html" for p in order + api_pages]

    def load_page(self, slug: str, v: Version, gen: Generators, modules: list[ApiModule], prefix: str) -> dict | None:
        path = DOCS_SRC / f"{slug}.md"
        if not path.exists() and slug not in self.missing:
            self.missing.add(slug)
            print(f"  ! site/docs/{slug}.md is listed in nav.json but missing")
        meta, text = front_matter(path.read_text(encoding="utf-8")) if path.exists() else ({}, "")
        if not available(meta, v):
            return None
        text = apply_conditions(text, v, slug)
        if re.search(r"<!--\s*(if|elif|else|endif)\b", text):
            print(f"  ! {slug}.md: a version condition was not applied (conditions inside a line must not wrap)")
        generated = {
            "reference/settings": gen.settings, "reference/commands": gen.commands_page,
            "reference/shortcuts": gen.shortcuts_page, "reference/command-line": gen.cli_page,
            "reference/data-files": gen.data_files_page,
            "api/index": lambda: gen.api_index(modules, lambda name: f"{name}.md"),
        }.get(slug)
        if generated is not None:
            produced = generated()
            text = text.replace("[[generated]]", produced) if "[[generated]]" in text else text + "\n\n" + produced
        text = self.macros(text, v)
        # Escapes for pages that show this syntax: <!--! if … -->, {{!version}}, [[!new 1.5.0]] stay literal.
        text = text.replace("<!--!", "<!--").replace("{{!", "{{").replace("[[!", "[[")
        title = meta.get("title") or slug.split("/")[-1].replace("-", " ").capitalize()
        edit = f"{self.repo_url}/edit/main/site/docs/{slug}.md" if path.exists() else ""
        return {"slug": slug, "title": title, "nav_title": meta.get("nav_title", title), "md": text,
                "description": meta.get("description", ""), "edit": edit,
                "edit_label": "Edit this page on GitHub", "generated": generated is not None}

    def macros(self, text: str, v: Version) -> str:
        def badge(m: re.Match) -> str:
            kind, ver = m[1], m[2]
            if v.number < version_tuple(ver):
                return ""
            label = {"new": "New in", "changed": "Changed in", "removed": "Removed in"}[kind]
            return f'<span class="badge badge-{kind}">{label} {ver}</span>'
        text = re.sub(r"\[\[(new|changed|removed) (\d+\.\d+\.\d+)\]\]", badge, text)
        return (text.replace("{{version}}", v.number_text if not v.is_main else "main")
                    .replace("{{ref}}", v.ref).replace("{{repo_url}}", self.repo_url))

    def render_doc(self, v: Version, dir_id: str, p: dict, out_path: str, body: str, toc: list,
                   nav_sections: list, prev_p: dict | None, next_p: dict | None, modules: list[ApiModule]) -> str:
        prefix = f"docs/{dir_id}/"
        here = p["slug"]

        def link(slug: str) -> str:
            return rel(out_path, prefix + slug + ".html")

        # sidebar
        side = []
        for title, entries in nav_sections:
            items = []
            for e in entries:
                active = e["slug"] == here or (e["slug"] == "api/index" and here.startswith("api/"))
                cls = ' class="active" aria-current="page"' if active else ""
                items.append(f'<li><a{cls} href="{esc(link(e["slug"]))}">{esc(e["nav_title"])}</a>')
                if e["slug"] == "api/index" and here.startswith("api/"):
                    pkgs: dict[str, list] = {}
                    for m in modules:
                        pkgs.setdefault(m.package, []).append(m)
                    sub = []
                    for pkg, mods in pkgs.items():
                        sub.append(f'<li class="pkg"><span>{esc(pkg)}</span><ul>' + "".join(
                            f'<li><a{" class=" + chr(34) + "active" + chr(34) if "api/" + m.name == here else ""}'
                            f' href="{esc(link("api/" + m.name))}">'
                            f'{esc("__init__" if m.path.endswith("__init__.py") else m.name.split(".")[-1])}</a></li>'
                            for m in mods) + "</ul></li>")
                    items.append('<ul class="api-tree">' + "".join(sub) + "</ul>")
                items.append("</li>")
            side.append(f'<div class="nav-section"><p class="nav-title">{esc(title)}</p><ul>{"".join(items)}</ul></div>')
        # table of contents
        toc_html = _toc_html(toc)
        # banner
        latest = self.latest
        banner = ""
        if v.is_main:
            # the text is one <span>: the banner is a flex row, and loose text would split into items
            banner = (f'<div class="version-banner dev"><span><strong>Development version.</strong> This '
                      f'describes <code>main</code>, which may include changes that are not released yet.</span> '
                      f'<a href="{esc(rel(out_path, "docs/latest/index.html"))}">Documentation for '
                      f'{esc(latest.id)}</a></div>')
        elif not v.latest and dir_id != "latest":
            banner = (f'<div class="version-banner old"><span>You are reading the documentation for JBrowser '
                      f'<strong>{esc(v.id)}</strong>. The newest release is {esc(latest.id)}.</span> '
                      f'<a class="to-latest" data-page="{esc(p["slug"])}.html" '
                      f'href="{esc(rel(out_path, "docs/latest/index.html"))}">Go to the latest documentation</a></div>')
        # breadcrumbs
        crumbs = [f'<a href="{esc(link("index"))}">Docs</a>']
        if p["slug"] != "index":
            crumbs.append(f'<span>{esc(p["section"])}</span>')
            if here.startswith("api/") and here != "api/index":
                crumbs.append(f'<a href="{esc(link("api/index"))}">Python API</a>')
        # page footer
        pager = []
        if prev_p:
            pager.append(f'<a class="prev" href="{esc(link(prev_p["slug"]))}"><span>Previous</span>'
                         f'{esc(prev_p["nav_title"])}</a>')
        if next_p:
            pager.append(f'<a class="next" href="{esc(link(next_p["slug"]))}"><span>Next</span>'
                         f'{esc(next_p["nav_title"])}</a>')
        badge = ""
        if p.get("generated") or here.startswith("api/"):
            badge = (f'<p class="generated-note">Generated from the source code of '
                     f'{"main" if v.is_main else "JBrowser " + esc(v.id)}.</p>')
        values = self.common(out_path, f"{p['title']} · JBrowser {v.id if not v.is_main else 'main'} docs",
                             p.get("description") or f"JBrowser developer documentation: {p['title']}.")
        values.update({
            "docs_root": rel(out_path, "docs/"), "version_id": v.id, "version_dir": dir_id,
            "version_label": esc(v.label), "page_path": esc(p["slug"] + ".html"),
            "sidebar": "\n".join(side), "toc": toc_html, "banner": banner, "breadcrumbs": " / ".join(crumbs),
            "body": body, "page_title": esc(p["title"]), "generated": badge,
            "edit_link": (f'<a href="{esc(p["edit"])}">{esc(p["edit_label"])}</a>' if p.get("edit") else ""),
            "pager": "".join(pager), "home_link": esc(link("index")),
            "version_short": esc("main" if v.is_main else v.id),
        })
        # Search engines should send people to the current docs: the newest release's own folder is the
        # same as docs/latest/ (canonical), and older versions and main aren't indexed (links still followed).
        if dir_id == self.latest.id:
            values["canonical"] = f"{self.site_url}docs/latest/{p['slug']}.html"
        elif dir_id != "latest":
            values["head_extra"] = '<meta name="robots" content="noindex, follow">'
        return render("docs.html", values)


def _flatten_toc(tokens: list) -> list:
    out = []
    for t in tokens:
        out.append(t)
        out += _flatten_toc(t.get("children", []))
    return out


def _toc_html(tokens: list) -> str:
    if not tokens:
        return ""

    def walk(items: list) -> str:
        return "<ul>" + "".join(
            f'<li><a href="#{esc(t["id"])}">{esc(html.unescape(t["name"]))}</a>'
            + (walk(t["children"]) if t.get("children") else "") + "</li>" for t in items) + "</ul>"
    return walk(tokens)


# ------------------------------------------------------------------------------ main
def serve(out: Path, port: int) -> None:
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {out} at http://localhost:{port}/  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def default_out() -> Path:
    """_site in the repository, like the other build scripts (tools/common.ps1): outside OneDrive,
    which would upload every build and lock files while writing them, and JBROWSER_BUILD_DIR wins."""
    if os.environ.get("JBROWSER_BUILD_DIR"):
        return Path(os.environ["JBROWSER_BUILD_DIR"]) / "site"
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        base = os.environ.get(var)
        if base and ROOT.is_relative_to(Path(base)):
            return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JBrowser-build" / "site"
    return ROOT / "_site"


def clear_folder(path: Path) -> None:
    """Empty ``path`` (a previous build). Folders another program still holds open (a preview server,
    a sync client) are left in place; the build then writes over them."""
    import time
    for _ in range(4):
        failed: list[str] = []
        if path.exists():
            shutil.rmtree(path, onexc=lambda _fn, p, _exc: failed.append(p))
        if not failed:
            return
        time.sleep(0.4)
    leftovers = [p for p in path.rglob("*") if p.is_file()] if path.exists() else []
    if leftovers:
        print(f"  (could not delete {len(leftovers)} old file(s) in {path}; they are overwritten or left unused)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(default_out()),
                   help="output folder (default: _site, or %%LOCALAPPDATA%%\\JBrowser-build\\site inside OneDrive)")
    p.add_argument("--offline", action="store_true", help="don't call the GitHub API")
    p.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT", help="preview the site after building")
    a = p.parse_args()
    out = Path(a.out).resolve()
    if out == ROOT or ROOT.is_relative_to(out):
        sys.exit("Refusing to build into the repository folder itself.")
    print(f"Building the website into {out}")
    site = Site(out, a.offline)
    site.build()
    count = sum(1 for _ in out.rglob("*.html"))
    print(f"Done: {count} pages. Latest release: {site.latest.id}")
    failed = bool(site.missing or site.broken)
    if failed:
        print("The site has problems (see ! above); the Pages workflow will not publish it.")
    if a.serve:
        serve(out, a.serve)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
