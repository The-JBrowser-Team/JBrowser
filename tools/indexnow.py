"""Tells search engines that support IndexNow (Bing, Yandex, Seznam, Naver) about the website's pages.

The Pages workflow runs it after each deploy of the site on its own domain. It reads the sitemap
and sends every address to api.indexnow.org, which shares it with the other engines. The key file
(<key>.txt at the site's root, written by build_site.py) proves the site is ours. Google doesn't
use IndexNow: it reads the sitemap (submit it once in Google Search Console).

    python tools/indexnow.py https://jbrowser.app/sitemap.xml
    python tools/indexnow.py _site                            # a built site folder
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

INDEXNOW_KEY = "5e0c3f9a1d7b4e62a8c9f0b13d2e7a46"   # public by design: served as /<key>.txt
ENDPOINT = "https://api.indexnow.org/indexnow"


def sitemap_text(source: str) -> str:
    if source.startswith("https://"):
        req = urllib.request.Request(source, headers={"User-Agent": "JBrowser-site"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    return (Path(source) / "sitemap.xml").read_text(encoding="utf-8")


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "_site"
    try:
        urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_text(source))
    except OSError as exc:
        print(f"Could not read the sitemap ({exc}). Skipped.")
        return 0
    if not urls:
        print("No addresses in the sitemap. Skipped.")
        return 0
    host = urllib.parse.urlsplit(urls[0]).hostname or ""
    if host.endswith(".github.io"):
        print(f"{host} is GitHub's own domain; IndexNow needs the site on its own domain. Skipped.")
        return 0
    body = json.dumps({"host": host, "key": INDEXNOW_KEY, "keyLocation": f"https://{host}/{INDEXNOW_KEY}.txt",
                       "urlList": urls[:10000]}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow: sent {len(urls)} addresses for {host} (HTTP {r.status}).")
    except urllib.error.HTTPError as exc:                # 403/422: the key file isn't reachable yet, and similar
        print(f"IndexNow refused the list (HTTP {exc.code}): {exc.read()[:200]!r}. Not fatal.")
    except OSError as exc:
        print(f"IndexNow could not be reached ({exc}). Not fatal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
