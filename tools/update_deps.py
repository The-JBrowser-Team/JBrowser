"""Install or update everything JBrowser needs, then prove it all imports.

What it does, in order:

1. Creates ``.venv`` (with the Python running this script) if it does not exist yet.
2. Upgrades pip, then installs/upgrades the packages in ``requirements.txt`` and, unless
   ``--runtime-only`` is given, the build tools in ``requirements-build.txt``.
3. Imports every module of the ``jbrowser`` package and every Qt / third-party module the
   app uses (inside the virtual environment), so a broken or missing package is caught now
   rather than when a user opens a dialog.
4. Runs pyflakes over the code (when the build tools are installed).
5. Optionally writes ``requirements.lock.txt`` with the exact versions (``--lock``), which
   makes a release build reproducible.

Usage (from the project folder, with any Python 3.14+)::

    python tools/update_deps.py              # create/update .venv and verify
    python tools/update_deps.py --check      # verify only, change nothing
    python tools/update_deps.py --lock       # also pin exact versions
    python tools/update_deps.py --runtime-only

Exit code 0 means everything is installed and importable.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
MIN_PYTHON = (3, 14)

# Modules JBrowser imports at runtime that live outside its own package.
REQUIRED_IMPORTS = [
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtNetwork", "PyQt6.QtPrintSupport",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebChannel", "PyQt6.QtMultimedia",
    "requests", "cryptography.hazmat.primitives.ciphers.aead", "cryptography.hazmat.primitives.kdf.scrypt",
    "pywinstyles",
]

VERIFY_SNIPPET = r"""
import importlib, json, pkgutil, sys, traceback
sys.path.insert(0, ROOT)
failed = {}
names = list(REQUIRED)
import jbrowser
names += [m.name for m in pkgutil.walk_packages(jbrowser.__path__, "jbrowser.")]
names += ["jbrowser"]
for name in names:
    try:
        importlib.import_module(name)
    except Exception:
        failed[name] = traceback.format_exc(limit=2).strip().splitlines()[-1]
print(json.dumps({"checked": len(names), "failed": failed}))
"""


def say(msg: str, colour: str = "36") -> None:
    print(f"\033[{colour}m{msg}\033[0m" if sys.stdout.isatty() else msg, flush=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    say("  $ " + " ".join(str(c) for c in cmd), "90")
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True,
                          capture_output=capture, encoding="utf-8", errors="replace")


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        return py
    if sys.version_info[:2] < MIN_PYTHON:
        raise SystemExit(f"JBrowser needs Python {'.'.join(map(str, MIN_PYTHON))}+ "
                         f"(this is {sys.version.split()[0]}). Run this script with a newer Python.")
    say(f"Creating the virtual environment in {VENV} ...")
    venv.EnvBuilder(with_pip=True, upgrade_deps=False).create(VENV)
    return py


def install(py: Path, runtime_only: bool) -> None:
    say("Updating pip ...")
    run([str(py), "-m", "pip", "install", "--upgrade", "--disable-pip-version-check", "pip"])
    req = "requirements.txt" if runtime_only else "requirements-build.txt"
    say(f"Installing / upgrading packages from {req} ...")
    run([str(py), "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager",
         "--disable-pip-version-check", "-r", req])


def verify(py: Path) -> bool:
    say("Checking that every module imports ...")
    code = f"ROOT = {str(ROOT)!r}\nREQUIRED = {REQUIRED_IMPORTS!r}\n" + VERIFY_SNIPPET
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([str(py), "-c", code], cwd=ROOT, capture_output=True, text=True, env=env,
                         encoding="utf-8", errors="replace")
    import json
    try:
        result = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        say("The import check could not run:\n" + out.stderr, "31")
        return False
    if result["failed"]:
        for name, err in result["failed"].items():
            say(f"  x {name}: {err}", "31")
        return False
    say(f"  {result['checked']} modules import cleanly", "32")
    return True


def lint(py: Path) -> bool:
    has = run([str(py), "-c", "import pyflakes"], check=False, capture=True).returncode == 0
    if not has:
        say("  (pyflakes not installed: skipped, it comes with the build tools)", "90")
        return True
    say("Running pyflakes ...")
    res = run([str(py), "-m", "pyflakes", "jbrowser", "tools", "main.py"], check=False, capture=True)
    if res.returncode != 0:
        say(res.stdout + res.stderr, "31")
        return False
    say("  no problems found", "32")
    return True


def report(py: Path) -> None:
    say("Installed versions:")
    names = ["PyQt6", "PyQt6-WebEngine", "PyQt6-Qt6", "PyQt6-WebEngine-Qt6", "requests", "cryptography",
             "pywinstyles", "pyinstaller", "pyflakes"]
    code = ("import importlib.metadata as m\n"
            f"for n in {names!r}:\n"
            "    try: print(f'  {n:<22} {m.version(n)}')\n"
            "    except m.PackageNotFoundError: pass\n")
    print(subprocess.run([str(py), "-c", code], capture_output=True, text=True).stdout, end="")
    ver = subprocess.run([str(py), "-c", "import sys; print(sys.version.split()[0])"], capture_output=True,
                         text=True).stdout.strip()
    say(f"  {'Python':<22} {ver}")


def lock(py: Path) -> None:
    frozen = run([str(py), "-m", "pip", "freeze", "--exclude-editable"], capture=True).stdout
    target = ROOT / "requirements.lock.txt"
    target.write_text("# Exact versions from the last successful `python tools/update_deps.py --lock`.\n"
                      "# Install them with: pip install -r requirements.lock.txt\n" + frozen, encoding="utf-8")
    say(f"Pinned {len(frozen.splitlines())} packages in {target.name}", "32")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="verify only; do not install anything")
    p.add_argument("--runtime-only", action="store_true", help="skip the build tools (PyInstaller, pyflakes)")
    p.add_argument("--lock", action="store_true", help="write requirements.lock.txt with exact versions")
    a = p.parse_args()

    if a.check:
        py = venv_python()
        if not py.exists():
            say("No .venv yet. Run without --check to create it.", "31")
            return 1
    else:
        py = ensure_venv()
        try:
            install(py, a.runtime_only)
        except subprocess.CalledProcessError:
            say("pip could not install the packages (see above).", "31")
            return 1
    ok = verify(py) and lint(py)
    report(py)
    if ok and a.lock:
        lock(py)
    say("Everything is up to date and importable." if ok else "Some checks failed (see above).",
        "32" if ok else "31")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
