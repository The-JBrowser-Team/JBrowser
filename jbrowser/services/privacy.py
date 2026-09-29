"""Privacy sandbox: third-party tracker blocking, GPC / DNT, HTTPS upgrades, dev host routing."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QThread, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from jbrowser.core.jsonstore import atomic_write_bytes
from jbrowser.core.settings import Settings
from jbrowser.core.urls import is_local_host, registrable_domain, strip_www
from jbrowser.core.workers import fetch_text
from jbrowser.services.adfilter import FilterEngine, split_list
from jbrowser.services.blocklist_data import builtin_rules

log = logging.getLogger(__name__)

RT = QWebEngineUrlRequestInfo.ResourceType
# Qt resource types → the request types Adblock Plus filters talk about.
_RTYPE = {
    RT.ResourceTypeScript: "script", RT.ResourceTypeImage: "image", RT.ResourceTypeFavicon: "image",
    RT.ResourceTypeStylesheet: "stylesheet", RT.ResourceTypeFontResource: "font",
    RT.ResourceTypeSubFrame: "subdocument", RT.ResourceTypeXhr: "xmlhttprequest", RT.ResourceTypeJson: "xmlhttprequest",
    RT.ResourceTypeMedia: "media", RT.ResourceTypePing: "ping", RT.ResourceTypeCspReport: "ping",
    RT.ResourceTypeObject: "object", RT.ResourceTypePluginResource: "object", RT.ResourceTypeWebSocket: "websocket",
}

# Sites that must never have JBrowser's page-level privacy changes (canvas noise) or third-party cookie
# blocking get in the way: CAPTCHA / bot-check providers and the big sign-in pages. Bot checks look
# for exactly the kind of changes privacy protection makes, and answer with "unusual traffic" pages.
CHALLENGE_SITES = ("google.com", "gstatic.com", "recaptcha.net", "youtube.com", "hcaptcha.com", "cloudflare.com",
                   "arkoselabs.com", "funcaptcha.com", "microsoftonline.com", "live.com", "microsoft.com",
                   "apple.com", "icloud.com", "paypal.com")
CAPTCHA_COOKIE_SITES = ("recaptcha.net", "hcaptcha.com", "challenges.cloudflare.com", "arkoselabs.com")

BLOCKLIST_SOURCES = [
    ("EasyPrivacy (trackers & telemetry)", "https://easylist.to/easylist/easyprivacy.txt"),
    ("EasyList (ads)", "https://easylist.to/easylist/easylist.txt"),
    ("Peter Lowe's ad & tracking servers",
     "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=0&mimetype=plaintext"),
    ("NoCoin (cryptominers)", "https://raw.githubusercontent.com/hoshsadiq/adblock-nocoin-list/master/hosts.txt"),
]

TRACKING_PARAMS = {
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "twclid", "ttclid",
    "li_fat_id", "igshid", "igsh", "mc_cid", "mc_eid", "_hsenc", "_hsmi", "__hssc", "__hstc", "__hsfp",
    "hsctatracking", "mkt_tok", "oly_anon_id", "oly_enc_id", "vero_id", "vero_conv", "wickedid", "rb_clickid",
    "s_cid", "ncid", "sr_share", "_openstat", "zanpid", "epik", "cmpid", "srsltid", "ref_src", "ref_url",
}
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "piwik_", "hmb_", "ga_")
# Parameters that are only tracking on specific sites.
SITE_TRACKING_PARAMS = {
    "youtube.com": {"si", "pp", "feature"}, "youtu.be": {"si", "feature"}, "spotify.com": {"si", "context"},
    "amazon.com": {"ref", "ref_", "pd_rd_r", "pd_rd_w", "pd_rd_wg", "pf_rd_p", "pf_rd_r", "psc", "tag"},
    "instagram.com": {"igsh", "img_index"}, "twitter.com": {"s", "t"}, "x.com": {"s", "t"},
    "tiktok.com": {"is_from_webapp", "sender_device", "sender_web_id"},
}


def strip_tracking(url: QUrl) -> tuple[QUrl, int]:
    """Return ``url`` without known tracking query parameters, and how many were removed."""
    if url.scheme() not in ("http", "https") or not url.hasQuery():
        return url, 0
    from urllib.parse import unquote_plus

    host = strip_www(url.host().lower())
    site_params: set[str] = set()
    for dom, params in SITE_TRACKING_PARAMS.items():
        if host == dom or host.endswith("." + dom):
            site_params |= params
    raw = url.query(QUrl.ComponentFormattingOption.FullyEncoded)
    pieces = [p for p in raw.split("&") if p]
    kept = []
    for piece in pieces:
        name = unquote_plus(piece.split("=", 1)[0])
        low = name.lower()
        if low in TRACKING_PARAMS or low.startswith(TRACKING_PREFIXES) or name in site_params:
            continue
        kept.append(piece)
    removed = len(pieces) - len(kept)
    if not removed:
        return url, 0
    clean = QUrl(url.toString(QUrl.UrlFormattingOption.RemoveQuery | QUrl.ComponentFormattingOption.FullyEncoded))
    if kept:
        clean.setQuery("&".join(kept), QUrl.ParsingMode.StrictMode)
    return clean, removed


_ABP_DOMAIN = re.compile(r"^\|\|([a-z0-9][a-z0-9.\-]*[a-z0-9])\^(\$(?P<opts>.*))?$")
_HOSTS_LINE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)\s+([a-z0-9][a-z0-9.\-]*[a-z0-9])")
_PLAIN = re.compile(r"^([a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+)$")


def parse_filter_list(text: str) -> set[str]:
    """Extract whole-domain block rules from hosts files and Adblock Plus lists."""
    out: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip().lower()
        if not line or line[0] in "#![" or line.startswith("@@"):
            continue
        m = _ABP_DOMAIN.match(line)
        if m:
            opts = m.group("opts") or ""
            if "domain=" in opts or "~third-party" in opts or "first-party" in opts:
                continue
            out.add(m.group(1))
            continue
        m = _HOSTS_LINE.match(line)
        if m:
            host = m.group(1)
            if host not in ("localhost", "localhost.localdomain", "local", "broadcasthost", "0.0.0.0"):
                out.add(host)
            continue
        m = _PLAIN.match(line)
        if m:
            out.add(m.group(1))
    return out


class Blocklist:
    def __init__(self, extra_file: Path):
        self.domains, self.paths = builtin_rules()
        self.extra_file = extra_file
        self.extra: set[str] = set()
        self.load_extra()

    def load_extra(self) -> None:
        try:
            self.extra = {line.strip() for line in self.extra_file.read_text("utf-8").splitlines() if line.strip()}
        except OSError:
            self.extra = set()

    def __len__(self) -> int:
        return len(self.domains | self.extra) + sum(len(v) for v in self.paths.values())

    def match(self, host: str, path: str = "/") -> bool:
        labels = host.split(".")
        for i in range(len(labels) - 1):
            cand = ".".join(labels[i:])
            if cand in self.domains or cand in self.extra:
                return True
        rules = self.paths.get(host) or self.paths.get(strip_www(host))
        return bool(rules and any(path.startswith(p) for p in rules))


class PrivacyService(QObject):
    """Holds privacy policy and answers per-request decisions for the interceptors."""

    blocklistUpdated = pyqtSignal(int, str)  # new size, error text ("" on success)

    def __init__(self, settings: Settings, blocklist_file: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.blocklist = Blocklist(blocklist_file)
        self.filters_file = blocklist_file.with_name("filters.txt")
        self.filters: FilterEngine | None = FilterEngine.load(self.filters_file)
        self._dev_map: dict[str, tuple[str, int]] = {}
        self._upgraded: dict[str, float] = {}
        self._no_upgrade: set[str] = set()
        self._updater: BlocklistUpdater | None = None
        self.stripped = 0  # tracking parameters removed this session
        self.threats = None  # ThreatService, attached by AppContext
        self.proxy_provider = lambda: {}   # requests-style proxies (set by AppContext)
        self.last_update_manual = False
        self._reload()
        settings.changed.connect(self._on_setting)

    def _on_setting(self, key: str, _value) -> None:
        if key.startswith(("privacy.", "network.dev_hosts")):
            self._reload()

    def _reload(self) -> None:
        self._cosmetic_cache: tuple = (None, "")
        s = self.settings
        self.block_trackers = bool(s.get("privacy.block_trackers"))
        self.gpc = bool(s.get("privacy.gpc"))
        self.dnt = bool(s.get("privacy.dnt"))
        self.https_upgrade = bool(s.get("privacy.https_upgrade"))
        self.strip_tracking = bool(s.get("privacy.strip_tracking"))
        self.block_3p_cookies = bool(s.get("privacy.block_third_party_cookies"))
        self.allowlist = {strip_www(h) for h in s.get("privacy.allowlist") or []}
        self._dev_map = {}
        for m in s.get("network.dev_hosts") or []:
            if not m.get("enabled", True) or not m.get("host") or not m.get("target"):
                continue
            target = str(m["target"]).strip()
            host, _, port = target.rpartition(":")
            if not host:
                host, port = target, "80"
            try:
                self._dev_map[str(m["host"]).lower().strip()] = (host.strip("[]") or "127.0.0.1", int(port))
            except ValueError:
                continue

    # -------------------------------------------------------------- decisions
    def dev_hosts(self) -> set[str]:
        return set(self._dev_map)

    def dev_target(self, host: str) -> tuple[str, int] | None:
        return self._dev_map.get(host.lower())

    def is_allowlisted(self, host: str) -> bool:
        host = strip_www(host)
        return host in self.allowlist or registrable_domain(host) in self.allowlist

    def set_site_protection(self, host: str, enabled: bool) -> None:
        host = strip_www(host)
        items = [h for h in self.settings.get("privacy.allowlist") or [] if h != host]
        if not enabled:
            items.append(host)
        self.settings.set("privacy.allowlist", items)

    def should_block(self, info: QWebEngineUrlRequestInfo) -> bool:
        rt = info.resourceType()
        if rt == RT.ResourceTypeMainFrame:
            return False
        url = info.requestUrl()
        host = url.host().lower()
        if not host or is_local_host(host):
            return False
        # Sub-resources and frames from known phishing / malware hosts are always blocked.
        if self.threats is not None and self.threats.match(host):
            return True
        if not self.block_trackers:
            return False
        first = info.firstPartyUrl().host().lower()
        if first and self.is_allowlisted(first):
            return False
        third = not first or registrable_domain(first) != registrable_domain(host)
        eng = self.filters
        if eng is not None and eng.site_allowed(first):
            return False
        rtype = _RTYPE.get(rt, "other")
        text = ""
        important = False
        # Tracker and ad domains (hosts lists and ||domain^ rules) are blocked on other sites only.
        blocked = third and self.blocklist.match(host, url.path() or "/")
        if not blocked and eng is not None:
            text = url.toString(QUrl.ComponentFormattingOption.FullyEncoded).lower()
            f = eng.blocking_filter(text, first or host, rtype, third)
            blocked = f is not None
            important = bool(f and f.important)
        if not blocked:
            return False
        if eng is not None and not important:
            text = text or url.toString(QUrl.ComponentFormattingOption.FullyEncoded).lower()
            if eng.excepted(text, first or host, rtype, third):
                return False
        return True

    def cosmetic_script(self) -> str:
        """Profile script that hides ad boxes and "Advertisement" frames, or "" when tracker blocking
        is off or no lists have been downloaded yet (see engine/js.py cosmetic_js)."""
        from jbrowser.engine.js import cosmetic_js
        if not self.block_trackers or self.filters is None:
            return ""
        key = (id(self.filters), tuple(sorted(self.allowlist)))
        if self._cosmetic_cache[0] != key:
            self._cosmetic_cache = (key, cosmetic_js(self.filters.cosmetic_data(), sorted(self.allowlist)))
        return self._cosmetic_cache[1]

    @staticmethod
    def is_challenge_site(host: str) -> bool:
        host = strip_www(host.lower())
        return any(host == d or host.endswith("." + d) for d in CHALLENGE_SITES) or \
            bool(re.match(r"^(?:[\w-]+\.)*google\.[a-z]{2,3}(?:\.[a-z]{2})?$", host))

    def rewrite(self, info: QWebEngineUrlRequestInfo) -> QUrl | None:
        """Dev-host routing and HTTPS upgrades. Returns a redirect target or None."""
        url = info.requestUrl()
        host = url.host().lower()
        target = self._dev_map.get(host)
        if target:
            new = QUrl(url)
            new.setScheme("http" if url.scheme() in ("http", "https") else url.scheme())
            new.setHost(target[0])
            new.setPort(target[1])
            return new
        if self.strip_tracking and info.resourceType() in (RT.ResourceTypeMainFrame, RT.ResourceTypeSubFrame) \
                and info.requestMethod() == b"GET" and not self.is_allowlisted(host):
            clean, removed = strip_tracking(url)
            if removed:
                self.stripped += removed
                return clean
        if (self.https_upgrade and url.scheme() == "http"
                and info.resourceType() == RT.ResourceTypeMainFrame
                and not is_local_host(host) and host not in self._no_upgrade and "." in host):
            now = time.monotonic()
            last = self._upgraded.get(host)
            if last and now - last < 4.0:
                # The https site bounced us back to http: respect it for this session.
                self._no_upgrade.add(host)
                return None
            self._upgraded[host] = now
            new = QUrl(url)
            new.setScheme("https")
            if new.port() == 80:
                new.setPort(-1)
            return new
        return None

    def was_upgraded(self, url: QUrl, window: float = 30.0) -> bool:
        """True when ``url`` is an https address JBrowser upgraded from http a moment ago."""
        if url.scheme() != "https":
            return False
        last = self._upgraded.get(url.host().lower())
        return bool(last) and time.monotonic() - last < window

    def upgrade_fallback(self, url: QUrl) -> QUrl | None:
        """HTTPS-First fallback: the upgraded address failed, so return the original http one."""
        if not self.was_upgraded(url):
            return None
        host = url.host().lower()
        self._no_upgrade.add(host)
        self._upgraded.pop(host, None)
        plain = QUrl(url)
        plain.setScheme("http")
        if plain.port() == 443:
            plain.setPort(-1)
        return plain

    def allow_cookie(self, request) -> bool:
        if not self.block_3p_cookies or not request.thirdParty:
            return True
        # CAPTCHA widgets keep their "this person already passed" state in their own cookies; without
        # them every site shows a harder challenge.
        origin = request.origin.host().lower()
        if origin and any(origin == d or origin.endswith("." + d) for d in CAPTCHA_COOKIE_SITES):
            return True
        first = request.firstPartyUrl.host()
        return bool(first) and self.is_allowlisted(first)

    # -------------------------------------------------------- list updating
    def maybe_update_blocklist(self) -> None:
        """Weekly background refresh (skipped when the user chose the built-in list only)."""
        if not self.block_trackers or not self.settings.get("privacy.blocklist_auto"):
            return
        last = float(self.settings.get("privacy.blocklist_updated") or 0)
        # filters.txt is new in 1.5: fetch it now rather than at the next weekly refresh.
        if time.time() - last > 7 * 24 * 3600 or not self.filters_file.exists():
            self.update_blocklist(manual=False)

    def update_blocklist(self, proxies: dict | None = None, manual: bool = True) -> bool:
        if self._updater and self._updater.isRunning():
            return False
        self.last_update_manual = manual
        if manual:
            self.settings.set("privacy.blocklist_auto", True)
        self._updater = BlocklistUpdater([u for _, u in BLOCKLIST_SOURCES], self.blocklist.extra_file,
                                         self.filters_file, proxies if proxies is not None else self.proxy_provider(),
                                         self)
        self._updater.done.connect(self._on_updated)
        self._updater.start()
        return True

    def _on_updated(self, count: int, error: str) -> None:
        self.blocklist.load_extra()
        self.filters = FilterEngine.load(self.filters_file)
        self._reload()
        if count:
            self.settings.set("privacy.blocklist_updated", time.time())
        self.blocklistUpdated.emit(len(self.blocklist) + (self.filters.network_count if self.filters else 0), error)

    def reset_blocklist(self) -> None:
        for f in (self.blocklist.extra_file, self.filters_file):
            try:
                f.unlink()
            except OSError:
                pass
        self.blocklist.load_extra()
        self.filters = None
        self._reload()
        self.settings.set("privacy.blocklist_updated", 0)
        self.settings.set("privacy.blocklist_auto", False)
        self.last_update_manual = True
        self.blocklistUpdated.emit(len(self.blocklist), "")


class BlocklistUpdater(QThread):
    done = pyqtSignal(int, str)

    def __init__(self, urls: list[str], out_file: Path, filters_file: Path, proxies: dict,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._urls = urls
        self._out = out_file
        self._filters_out = filters_file
        self._proxies = proxies

    def run(self) -> None:  # worker thread
        domains: set[str] = set()
        rest: list[str] = []
        errors = []
        headers = {"User-Agent": "JBrowser blocklist updater", "DNT": "1"}
        for url in self._urls:
            if self.isInterruptionRequested():
                return
            try:
                d, r = split_list(fetch_text(url, headers, self._proxies, self.isInterruptionRequested))
                domains |= d
                rest += r
            except InterruptedError:
                return
            except Exception as exc:  # network errors are reported, not fatal
                errors.append(f"{url}: {exc}")
        if self.isInterruptionRequested():
            return
        if domains:
            atomic_write_bytes(self._out, "\n".join(sorted(domains)).encode("utf-8"))
        if rest:
            header = "! JBrowser: URL-pattern, exception and element-hiding rules from the lists in Settings\n"
            atomic_write_bytes(self._filters_out, (header + "\n".join(dict.fromkeys(rest))).encode("utf-8"))
        self.done.emit(len(domains), "\n".join(errors))


class ProfileInterceptor(QWebEngineUrlRequestInterceptor):
    """Runs for every request of a profile: privacy headers, HTTPS upgrade, dev host routing."""

    def __init__(self, privacy: PrivacyService, parent: QObject | None = None):
        super().__init__(parent)
        self._p = privacy

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        try:
            target = self._p.rewrite(info)
            if target is not None:
                info.redirect(target)
                return
            if self._p.dnt:
                info.setHttpHeader(b"DNT", b"1")
            if self._p.gpc:
                info.setHttpHeader(b"Sec-GPC", b"1")
        except Exception:  # never let an exception escape into the engine
            log.exception("ProfileInterceptor failed")


class PageInterceptor(QWebEngineUrlRequestInterceptor):
    """Per-card interceptor so blocked requests can be attributed and counted per card."""

    def __init__(self, privacy: PrivacyService, on_blocked: Callable[[str], None], parent: QObject | None = None,
                 on_websocket: Callable[[], None] | None = None):
        super().__init__(parent)
        self._p = privacy
        self._on_blocked = on_blocked
        self._on_websocket = on_websocket

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        try:
            if self._p.should_block(info):
                info.block(True)
                self._on_blocked(info.requestUrl().host())
            elif self._on_websocket is not None and info.resourceType() == RT.ResourceTypeWebSocket:
                self._on_websocket()
        except Exception:
            log.exception("PageInterceptor failed")
