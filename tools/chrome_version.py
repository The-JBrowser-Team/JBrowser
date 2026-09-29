"""Records the newest stable Chrome for Windows in jbrowser/engine/identity.py.

JBrowser presents itself to websites as the current Chrome version (see identity.py). This asks
Google's version history service which version that is and rewrites CHROME_VERSION and
CHROME_VERSION_DATE. master.ps1 runs it for every release, so each update carries the numbers of
the Chrome that was current when it was built.

    python tools/chrome_version.py            # print the recorded and the newest version
    python tools/chrome_version.py --update   # record the newest version (exit code 1 if it can't)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDENTITY = ROOT / "jbrowser" / "engine" / "identity.py"
API = "https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/stable/versions?pageSize=1"


def newest() -> str:
    req = urllib.request.Request(API, headers={"User-Agent": "JBrowser-build"})
    with urllib.request.urlopen(req, timeout=20) as r:
        version = json.load(r)["versions"][0]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
        raise ValueError(f"unexpected version {version!r}")
    return version


def recorded() -> tuple[str, str]:
    text = IDENTITY.read_text(encoding="utf-8")
    v = re.search(r'^CHROME_VERSION = "([\d.]+)"', text, re.M)
    d = re.search(r"^CHROME_VERSION_DATE = date\((\d+), (\d+), (\d+)\)", text, re.M)
    return (v[1] if v else "?"), (f"{int(d[1]):04d}-{int(d[2]):02d}-{int(d[3]):02d}" if d else "?")


def record(version: str, today: date) -> None:
    text = IDENTITY.read_text(encoding="utf-8")
    text = re.sub(r'^CHROME_VERSION = "[\d.]+"', f'CHROME_VERSION = "{version}"', text, count=1, flags=re.M)
    text = re.sub(r"^CHROME_VERSION_DATE = date\(\d+, \d+, \d+\)",
                  f"CHROME_VERSION_DATE = date({today.year}, {today.month}, {today.day})", text, count=1, flags=re.M)
    IDENTITY.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    old, old_date = recorded()
    try:
        new = newest()
    except Exception as exc:
        print(f"Could not ask Google for the newest Chrome ({exc}). Keeping Chrome {old} ({old_date}).")
        return 1
    if "--update" not in sys.argv:
        print(f"Recorded: Chrome {old} ({old_date}). Newest stable for Windows: {new}.")
        return 0
    record(new, date.today())
    print(f"JBrowser presents Chrome {new} (was {old}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
