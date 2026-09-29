"""Adblock Plus / EasyList filter engine: URL-pattern blocking, exceptions and element hiding.

The downloaded lists (see ``privacy.BLOCKLIST_SOURCES``) are split by the updater into:

* ``blocklist.txt``: plain ``||domain^`` rules and hosts-file entries. Fast set lookups in
  :class:`jbrowser.services.privacy.Blocklist`.
* ``filters.txt``: everything else this engine understands. That is URL patterns such as
  ``/ads/banner*.js$third-party``, exceptions (``@@``), and element-hiding rules (``##.ad-slot``,
  ``example.com##.promo``), which hide the empty boxes and "Advertisement" frames that
  domain blocking alone leaves behind.

Matching uses the same trick as Adblock Plus: every filter is filed under one "token" (a word
it must contain), so a request only checks the handful of filters whose token appears in its
URL. Unsupported syntax (procedural cosmetics, scriptlets, regex filters) is skipped.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9%]{3,}")
# Safety valves for lists downloaded from the internet: patterns with many wildcards can backtrack
# badly, and matching never looks further than MAX_URL characters into an address.
MAX_WILDCARDS = 4
MAX_URL = 2048
_COSMETIC = re.compile(r"^([\w.,~*\-]*)(#@?#)(.+)$")
# Syntax this engine does not implement: extended CSS (#?#), snippets/scriptlets (#$#, #%#, +js),
# HTML filters ($$).
_SKIP_LINE = re.compile(r"#@?[?$%]#|\$\$|#@?#\+js|#@?#\^")
# Characters that end a token; "*" doesn't (a wildcard next to a token makes it unreliable).
_SEP_CLASS = r"[^a-z0-9_\-.%]"

TYPE_OPTIONS = {
    "script": "script", "image": "image", "stylesheet": "stylesheet", "css": "stylesheet",
    "font": "font", "subdocument": "subdocument", "frame": "subdocument", "xmlhttprequest": "xmlhttprequest",
    "xhr": "xmlhttprequest", "media": "media", "ping": "ping", "beacon": "ping", "object": "object",
    "websocket": "websocket", "other": "other", "object-subrequest": "object",
}
ALL_TYPES = frozenset(TYPE_OPTIONS.values())
# Options that don't change whether a request is blocked, or that only matter for cosmetics.
_IGNORED = {"match-case", "important", "third-party", "3p", "first-party", "1p", "~third-party",
            "~first-party", "~3p", "~1p", "all", "redirect", "redirect-rule", "empty", "mp4", "collapse", "~collapse"}
# Options that make a filter mean something JBrowser can't do: the filter is skipped.
_UNSUPPORTED = {"popup", "csp", "rewrite", "removeparam", "queryprune", "replace", "header", "permissions", "to",
                "denyallow", "method", "strict1p", "strict3p", "document", "doc", "genericblock", "badfilter",
                "inline-script", "inline-font", "webrtc", "sitekey", "cname", "urltransform", "uritransform",
                "urlskip", "elemhide", "ehide", "generichide", "ghide", "specifichide", "shide", "popunder"}
_PROCEDURAL = re.compile(r":-abp-|:(?:has-text|contains|matches-\w+|xpath|upward|remove|style|watch-attr|"
                         r"min-text-length|others|if|if-not|nth-ancestor|shadow|remove-attr|remove-class|matches-path)"
                         r"\(|\+js\(|^\+")


class NetworkFilter:
    __slots__ = ("pattern", "regex", "types", "third", "include", "exclude", "important")

    def __init__(self, pattern: str, types: frozenset, third: bool | None, include: tuple, exclude: tuple,
                 important: bool):
        self.pattern = pattern
        self.regex = None            # compiled on first use
        self.types = types
        self.third = third           # True: third-party only, False: first-party only, None: both
        self.include = include       # first-party domains the filter is limited to
        self.exclude = exclude       # first-party domains the filter never applies to
        self.important = important

    def matches(self, url: str, first: str, rtype: str, third: bool) -> bool:
        if rtype not in self.types:
            return False
        if self.third is not None and self.third != third:
            return False
        if self.include and not _domain_in(first, self.include):
            return False
        if self.exclude and _domain_in(first, self.exclude):
            return False
        if self.regex is None:
            self.regex = re.compile(_to_regex(self.pattern))
        return self.regex.search(url) is not None


def _domain_in(host: str, domains: tuple) -> bool:
    for d in domains:
        if host == d or host.endswith("." + d):
            return True
    return False


def _to_regex(pattern: str) -> str:
    """Adblock Plus pattern → regular expression (on a lower-cased URL)."""
    start = ""
    if pattern.startswith("||"):
        start = r"^[a-z][a-z0-9+.\-]*://(?:[^/?#]*\.)?"
        pattern = pattern[2:]
    elif pattern.startswith("|"):
        start = "^"
        pattern = pattern[1:]
    end = ""
    if pattern.endswith("|"):
        end = "$"
        pattern = pattern[:-1]
    out = []
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "^":
            out.append(f"(?:{_SEP_CLASS}|$)")
        else:
            out.append(re.escape(ch))
    return start + "".join(out) + end


def _best_token(pattern: str) -> str:
    """The longest word the URL must contain as a whole token, or "" if there is none."""
    body = pattern.lstrip("|")
    best = ""
    for m in _TOKEN.finditer(body):
        s, e = m.start(), m.end()
        before = body[s - 1] if s else ("|" if pattern.startswith("|") else "*")
        after = body[e] if e < len(body) else ("|" if pattern.endswith("|") else "*")
        if before == "*" or after == "*":
            continue
        if len(m.group()) > len(best):
            best = m.group()
    return best


def _split_options(line: str) -> tuple[str, str]:
    idx = line.rfind("$")
    if idx <= 0 or line.startswith("/") and line.endswith("/"):
        return line, ""
    return line[:idx], line[idx + 1:]


class FilterEngine:
    """Parsed ``filters.txt``: network filters indexed by token, plus element-hiding rules."""

    def __init__(self) -> None:
        self.block: dict[str, list[NetworkFilter]] = {}
        self.allow: dict[str, list[NetworkFilter]] = {}
        self.site_allow: set[str] = set()         # @@||site^$document: no blocking on these sites
        self.no_cosmetic: set[str] = set()        # @@||site^$elemhide
        self.no_generic: set[str] = set()         # @@||site^$generichide
        self.generic: list[str] = []
        self.generic_skip: dict[str, set[str]] = {}   # selector -> sites excluded with ~site##
        self.specific: dict[str, list[str]] = {}
        self.unhide: dict[str, set[str]] = {}      # site -> selectors excepted with site#@#
        self.global_unhide: set[str] = set()
        self.network_count = 0
        self.cosmetic_count = 0
        self._payload: dict | None = None

    # ------------------------------------------------------------------ parsing
    @classmethod
    def from_text(cls, text: str) -> "FilterEngine":
        eng = cls()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in "![":
                continue
            try:
                eng._add(line)
            except Exception:              # one bad line never breaks the list
                continue
        eng.generic = list(dict.fromkeys(eng.generic))
        return eng

    @classmethod
    def load(cls, path: Path) -> "FilterEngine | None":
        try:
            text = path.read_text("utf-8")
        except OSError:
            return None
        eng = cls.from_text(text)
        log.info("Filter engine: %d network filters, %d element-hiding rules", eng.network_count, eng.cosmetic_count)
        return eng

    def _add(self, line: str) -> None:
        if _SKIP_LINE.search(line):
            return
        m = _COSMETIC.match(line)
        if m:
            self._add_cosmetic(m.group(1), m.group(2), m.group(3).strip())
            return
        self._add_network(line)

    def _add_cosmetic(self, domains: str, marker: str, selector: str) -> None:
        if not selector or _PROCEDURAL.search(selector) or "{" in selector or "}" in selector:
            return
        include = [d.strip().lower() for d in domains.split(",") if d.strip() and not d.strip().startswith("~")]
        exclude = [d.strip()[1:].lower() for d in domains.split(",") if d.strip().startswith("~")]
        if marker == "#@#":
            if include:
                for d in include:
                    self.unhide.setdefault(d, set()).add(selector)
            else:
                self.global_unhide.add(selector)
            return
        self.cosmetic_count += 1
        if include:
            for d in include:
                self.specific.setdefault(d, []).append(selector)
        else:
            self.generic.append(selector)
            if exclude:
                self.generic_skip.setdefault(selector, set()).update(exclude)

    def _add_network(self, line: str) -> None:
        exception = line.startswith("@@")
        if exception:
            line = line[2:]
        pattern, opts = _split_options(line)
        pattern = pattern.lower()
        if not pattern or pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            return                                         # regular-expression filters: skipped
        if pattern.count("*") > MAX_WILDCARDS or len(pattern) > 512:
            return                                         # could backtrack badly on long addresses
        types: set[str] = set()
        neg_types: set[str] = set()
        third = None
        include: list[str] = []
        exclude: list[str] = []
        important = False
        doc_like: set[str] = set()
        for opt in (o.strip().lower() for o in opts.split(",") if o.strip()):
            name, _, value = opt.partition("=")
            if name in ("domain", "from"):
                for d in value.split("|"):
                    d = d.strip()
                    if d.startswith("~"):
                        exclude.append(d[1:])
                    elif d:
                        include.append(d)
            elif name in ("third-party", "3p", "~first-party", "~1p"):
                third = True
            elif name in ("~third-party", "~3p", "first-party", "1p"):
                third = False
            elif name == "important":
                important = True
            elif name in TYPE_OPTIONS:
                types.add(TYPE_OPTIONS[name])
            elif name.startswith("~") and name[1:] in TYPE_OPTIONS:
                neg_types.add(TYPE_OPTIONS[name[1:]])
            elif exception and name in ("document", "doc", "elemhide", "ehide", "generichide", "ghide"):
                doc_like.add(name)
            elif name in _IGNORED:
                continue
            elif name in _UNSUPPORTED or name:
                return
        if doc_like:
            m = re.match(r"^\|\|([a-z0-9.\-]+)\^?$", pattern)
            if m:
                site = m.group(1)
                if doc_like & {"document", "doc"}:
                    self.site_allow.add(site)
                if doc_like & {"document", "doc", "elemhide", "ehide"}:
                    self.no_cosmetic.add(site)
                if doc_like & {"generichide", "ghide"}:
                    self.no_generic.add(site)
            return
        final_types = frozenset(types or ALL_TYPES) - neg_types
        if not final_types:
            return
        f = NetworkFilter(pattern, final_types, third, tuple(include), tuple(exclude), important)
        index = self.allow if exception else self.block
        index.setdefault(_best_token(pattern), []).append(f)
        self.network_count += 1

    # ----------------------------------------------------------------- matching
    @staticmethod
    def _candidates(index: dict, url: str):
        seen = set()
        for tok in _TOKEN.findall(url):
            if tok in seen:
                continue
            seen.add(tok)
            yield from index.get(tok, ())
        yield from index.get("", ())

    @staticmethod
    def _chain(host: str) -> list[str]:
        """``a.b.example.com`` → [a.b.example.com, b.example.com, example.com]."""
        parts = host.lower().split(".")
        return [".".join(parts[i:]) for i in range(max(1, len(parts) - 1))]

    def site_allowed(self, first: str) -> bool:
        """The list itself exempts this site from blocking (``@@||site^$document``)."""
        return bool(first and self.site_allow) and any(h in self.site_allow for h in self._chain(first))

    def blocking_filter(self, url: str, first: str, rtype: str, third: bool) -> NetworkFilter | None:
        url = url[:MAX_URL]
        for f in self._candidates(self.block, url):
            if f.matches(url, first, rtype, third):
                return f
        return None

    def excepted(self, url: str, first: str, rtype: str, third: bool) -> bool:
        url = url[:MAX_URL]
        for f in self._candidates(self.allow, url):
            if f.matches(url, first, rtype, third):
                return True
        return False

    # ----------------------------------------------------------------- cosmetics
    def cosmetic_data(self) -> dict:
        """Element-hiding rules in the compact form the page script uses (see engine/js.py
        ``cosmetic_js``): the script picks the rules for its own site as the page starts. That is
        the only way they apply to the very first page of a site, because a script added while
        a navigation is already under way only takes effect from the next one."""
        if self._payload is None:
            gu = self.global_unhide
            self._payload = {
                "g": [s for s in self.generic if s not in gu],
                "s": {d: [s for s in dict.fromkeys(sels) if s not in gu] for d, sels in self.specific.items()},
                "u": {d: sorted(sels) for d, sels in self.unhide.items()},
                "k": {s: sorted(ds) for s, ds in self.generic_skip.items() if s not in gu},
                "nc": {d: 1 for d in self.no_cosmetic},
                "ng": {d: 1 for d in self.no_generic},
            }
        return self._payload

    def css_for(self, host: str) -> str:
        """The style sheet the page script builds for ``host`` (for tests and diagnostics)."""
        data = self.cosmetic_data()
        chain = self._chain(host) if host else []
        if any(h in data["nc"] for h in chain):
            return ""
        unhide = set().union(*(data["u"].get(h, ()) for h in chain)) if chain else set()
        selectors: list[str] = []
        if not any(h in data["ng"] for h in chain):
            for sel in data["g"]:
                skip = data["k"].get(sel)
                if sel not in unhide and not (skip and any(h in skip for h in chain)):
                    selectors.append(sel)
        for h in chain:
            selectors.extend(s for s in data["s"].get(h, ()) if s not in unhide)
        # One rule per selector: an unsupported selector then drops only its own rule.
        return "\n".join(f"{s}{{display:none!important}}" for s in dict.fromkeys(selectors))


def split_list(text: str) -> tuple[set[str], list[str]]:
    """Split a downloaded list into plain domains (for ``blocklist.txt``) and the lines the
    :class:`FilterEngine` handles (for ``filters.txt``). Hosts files only produce domains."""
    domains: set[str] = set()
    rest: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "![#" and not line.startswith(("##", "#@#")):
            continue
        low = line.lower()
        m = re.match(r"^\|\|([a-z0-9][a-z0-9.\-]*[a-z0-9])\^(?:\$(.*))?$", low)
        if m:
            opts = m.group(2) or ""
            plain = {o.strip() for o in opts.split(",") if o.strip()} <= {"third-party", "3p"}
            if plain:
                domains.add(m.group(1))
                continue
            rest.append(line)
            continue
        m = re.match(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)\s+([a-z0-9][a-z0-9.\-]*[a-z0-9])", low)
        if m:
            if m.group(1) not in ("localhost", "localhost.localdomain", "local", "broadcasthost", "0.0.0.0"):
                domains.add(m.group(1))
            continue
        if re.match(r"^[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+$", low):
            domains.add(low)
            continue
        rest.append(line)
    return domains, rest
