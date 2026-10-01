"""The browser JBrowser presents itself as: the current Chrome version, as a Chromium browser.

Qt WebEngine would announce its own Chromium (140 in Qt 6.11) plus a ``QtWebEngine/x.y`` token, and a
browser a year behind Chrome is treated as outdated or suspicious by some sites. JBrowser presents the
newest stable Chrome version instead, consistently everywhere a site can look: the ``User-Agent``
header, ``navigator.userAgent``, the ``Sec-CH-UA`` client-hint headers and ``navigator.userAgentData``.

The user agent string is exactly Chrome's. The client-hint brands say "Chromium" (plus Chrome's
placeholder brand) but not "Google Chrome": Google's sign-in knows a genuine Google Chrome by more than
its brand, and rejects a browser that claims the brand without the rest ("Couldn't sign you in").

The version is recorded at build time: ``tools/chrome_version.py`` asks Google's version history
service for the newest stable Chrome for Windows and rewrites the two constants below, and
``master.ps1`` runs it for every release. A copy of JBrowser that hasn't been updated for a while
keeps up by itself: every 30 days after the recorded date it presents the next major version.
Chrome ships one every 4 weeks, so the estimate never runs ahead of the real Chrome.
"""
from __future__ import annotations

from datetime import date

# Written by tools/chrome_version.py: the newest stable Chrome for Windows, and when it was newest.
CHROME_VERSION = "155.0.8059.26"
CHROME_VERSION_DATE = date(2026, 10, 1)

ESTIMATE_DAYS = 30        # one major version per 30 days after CHROME_VERSION_DATE (Chrome: every 28)

# Chrome's "GREASE" brand, which varies with the major version so sites can't rely on a fixed
# brand list (Chromium's user_agent_utils.cc, GetGreasedUserAgentBrandVersion).
_GREASE_CHARS = (" ", "(", ":", "-", ".", "/", ")", ";", "=", "?", "_")
_GREASE_VERSIONS = ("8", "99", "24")


def chrome_version(today: date | None = None) -> str:
    """The full Chrome version to present, e.g. "155.0.8059.12"."""
    base = CHROME_VERSION
    ahead = max(0, ((today or date.today()) - CHROME_VERSION_DATE).days // ESTIMATE_DAYS)
    if ahead == 0:
        return base
    return f"{int(base.split('.')[0]) + ahead}.0.0.0"


def major(version: str) -> int:
    return int(version.split(".")[0])


def user_agent(version: str) -> str:
    """Chrome's reduced user agent: only the major version is real, the rest is always zero."""
    return (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major(version)}.0.0.0 Safari/537.36")


def grease_brand(seed: int) -> tuple[str, str]:
    """The placeholder brand and version Chrome adds for major version ``seed``, e.g. ("Not(A:Brand", "24")."""
    n = len(_GREASE_CHARS)
    return (f"Not{_GREASE_CHARS[seed % n]}A{_GREASE_CHARS[(seed + 1) % n]}Brand",
            _GREASE_VERSIONS[seed % len(_GREASE_VERSIONS)])


def brand_versions(version: str) -> dict[str, str]:
    """Brand → full version, as a Chromium browser of this version reports them
    (``Sec-CH-UA-Full-Version-List``). No "Google Chrome" brand: see the module notes."""
    grease, grease_version = grease_brand(major(version))
    return {"Chromium": version, grease: f"{grease_version}.0.0.0"}


def engine_version() -> str:
    """The Chromium version Qt WebEngine is actually built on, e.g. "140.0.7339.225"."""
    try:
        from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
        return qWebEngineChromiumVersion()
    except ImportError:          # pragma: no cover - Qt < 6.3
        return CHROME_VERSION


def version_for(choice: str | None) -> str:
    """The version for Settings → Advanced → "How JBrowser introduces itself": the newest Chrome
    ("current", the default) or the engine's own Chromium ("engine")."""
    return engine_version() if choice == "engine" else chrome_version()


def apply(profile, version: str | None = None) -> str:
    """Present ``version`` (default: ``chrome_version()``) on a QWebEngineProfile. Returns the user agent."""
    version = version or chrome_version()
    ua = user_agent(version)
    profile.setHttpUserAgent(ua)
    hints = profile.clientHints()
    hints.setAllClientHintsEnabled(True)
    hints.setFullVersion(version)
    hints.setFullVersionList(brand_versions(version))
    return ua


def firefox_user_agent(today: date | None = None) -> str:
    """A current Firefox user agent for Windows. Firefox 140 came out on 2025-06-24 and a new
    version follows about every four weeks; counting 30 days per version never runs ahead."""
    days = ((today or date.today()) - date(2025, 6, 24)).days
    version = 140 + max(0, days // 30)
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}.0) Gecko/20100101 Firefox/{version}.0"


def apply_firefox(profile) -> str:
    """Present Firefox on a profile, as consistently as Qt WebEngine allows (see engine/signin.py):
    the user agent in headers and JavaScript, no high-entropy client hints, and no browser brands in
    the ``Sec-CH-UA`` header or ``navigator.userAgentData`` (Firefox has neither)."""
    ua = firefox_user_agent()
    profile.setHttpUserAgent(ua)
    hints = profile.clientHints()
    hints.setAllClientHintsEnabled(False)
    hints.setFullVersionList({})
    hints.setFullVersion("")
    return ua
