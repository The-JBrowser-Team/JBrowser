"""DNS resolver selection (DNS-over-HTTPS), proxy routing and localhost developer tooling."""
from __future__ import annotations

import base64
import ctypes
import logging
import os
from typing import Callable

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkProxy, QNetworkProxyFactory, QTcpSocket
from PyQt6.QtWebEngineCore import QWebEngineGlobalSettings, QWebEnginePage, QWebEngineProfile

from jbrowser.core.settings import Settings
from jbrowser.platform import win

log = logging.getLogger(__name__)

DNS_MODES = {
    "system": {"label": "OS Default", "detail": "Use the resolver configured in Windows.",
               "templates": []},
    "quad9": {"label": "Quad9 Malware Blocking (Recommended)",
              "detail": "Encrypted DNS-over-HTTPS via Quad9 (9.9.9.9). Blocks known malicious domains.",
              "templates": ["https://dns.quad9.net/dns-query"]},
    "cloudflare": {"label": "Cloudflare DNS (1.1.1.1)",
                   "detail": "Encrypted DNS-over-HTTPS via Cloudflare's 1.1.1.1 resolver.",
                   "templates": ["https://cloudflare-dns.com/dns-query"]},
}

DEV_PORTS = [(3000, "React / Next.js / Express"), (5173, "Vite"), (8000, "Django / FastAPI / http.server"),
             (8080, "Generic dev server"), (4200, "Angular"), (5000, "Flask"), (8888, "Jupyter")]


# ------------------------------------------------------------------ secrets
def protect_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return "dpapi:" + base64.b64encode(win.dpapi_protect(value.encode("utf-8"))).decode("ascii")
    except OSError:
        return "plain:" + value


def reveal_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:"):
        try:
            return win.dpapi_unprotect(base64.b64decode(value[6:])).decode("utf-8")
        except (OSError, ValueError):
            return ""
    if value.startswith("plain:"):
        return value[6:]
    return value


# ---------------------------------------------------------------------- DNS
class DnsManager(QObject):
    """Switches Chromium's stub resolver between system DNS and DNS-over-HTTPS at runtime.

    PyQt6 exposes ``QWebEngineGlobalSettings.DnsMode`` but not the static ``setDnsMode()``
    call, so the exported C++ function is invoked through ctypes. ``DnsMode`` is passed by
    value (MSVC x64: pointer to a temporary that the callee destroys), so the shared
    ``QStringList`` payload is ref-counted up once to balance the callee-side destructor.
    """

    applied = pyqtSignal(str, bool)

    _SYMBOL = "?setDnsMode@QWebEngineGlobalSettings@@YA_NUDnsMode@1@@Z"

    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._fn = self._resolve()
        self.current = ""

    @classmethod
    def _resolve(cls):
        if not win.IS_WINDOWS:
            return None
        candidates = [
            os.path.join(QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.BinariesPath),
                         "Qt6WebEngineCore.dll"),
            os.path.join(os.path.dirname(QtCore.__file__), "Qt6", "bin", "Qt6WebEngineCore.dll"),
            "Qt6WebEngineCore.dll",
        ]
        for path in candidates:
            try:
                if os.path.isabs(path) and not os.path.exists(path):
                    continue
                dll = ctypes.CDLL(path)
                fn = dll[cls._SYMBOL]
                fn.restype = ctypes.c_bool
                fn.argtypes = [ctypes.c_void_p]
                return fn
            except (OSError, AttributeError):
                continue
        log.warning("QWebEngineGlobalSettings::setDnsMode not found; DNS selection unavailable")
        return None

    @property
    def available(self) -> bool:
        return self._fn is not None

    def apply(self, mode: str | None = None) -> bool:
        from PyQt6 import sip

        mode = mode or self.settings.get("network.dns_mode")
        if mode not in DNS_MODES:
            mode = "system"
        if self._fn is None:
            self.applied.emit(mode, False)
            return False
        G = QWebEngineGlobalSettings
        dm = G.DnsMode()
        templates = DNS_MODES[mode]["templates"]
        if templates:
            fallback = bool(self.settings.get("network.dns_fallback"))
            dm.secureMode = G.SecureDnsMode.SecureWithFallback if fallback else G.SecureDnsMode.SecureOnly
        else:
            dm.secureMode = G.SecureDnsMode.SystemOnly
        dm.serverTemplates = templates
        addr = sip.unwrapinstance(dm)
        list_d = ctypes.c_void_p.from_address(addr + 8).value  # QStringList's QArrayData*
        if list_d:
            ctypes.c_int.from_address(list_d).value += 1
        try:
            ok = bool(self._fn(addr))
        except OSError as exc:
            log.error("setDnsMode failed: %s", exc)
            ok = False
        if ok:
            self.current = mode
        self.applied.emit(mode, ok)
        return ok


# -------------------------------------------------------------------- proxy
def normalize_proxy(cfg: dict | None) -> dict:
    base = {"mode": "direct", "type": "http", "host": "", "port": 8080, "username": "", "password": ""}
    if cfg:
        base.update({k: v for k, v in cfg.items() if k in base})
    try:
        base["port"] = int(base["port"])
    except (TypeError, ValueError):
        base["port"] = 8080
    return base


def describe_proxy(cfg: dict | None) -> str:
    c = normalize_proxy(cfg)
    if c["mode"] == "system":
        return "System proxy"
    if c["mode"] != "manual" or not c["host"]:
        return "Direct connection"
    return f"{c['type'].upper()} {c['host']}:{c['port']}"


class ProxyManager(QObject):
    """Routes engine traffic through HTTP / SOCKS5 proxies (applied live) or an HTTPS
    (TLS-to-proxy) server (applied through Chromium flags at startup).

    Chromium owns one network stack per process, so per-space overrides follow the
    foreground space: switching spaces re-routes traffic and "kicks" each profile's
    network context so the new configuration is used by the very next request.
    """

    changed = pyqtSignal(str)  # human readable description

    KICK_URL = "http://proxy-refresh.jbrowser.invalid/"

    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._profiles: Callable[[], list[QWebEngineProfile]] = lambda: []
        self._kickers: list[QWebEnginePage] = []
        self._current_key: tuple | None = None
        self.flag_mode = False
        self.description = "Direct connection"

    def set_profile_provider(self, provider: Callable[[], list[QWebEngineProfile]]) -> None:
        self._profiles = provider

    @staticmethod
    def startup_flags(settings: Settings) -> list[str]:
        cfg = normalize_proxy(settings.get("network.proxy"))
        if cfg["mode"] == "manual" and cfg["type"] == "https" and cfg["host"]:
            return [f"--proxy-server=https://{cfg['host']}:{cfg['port']}"]
        return []

    def global_config(self) -> dict:
        return normalize_proxy(self.settings.get("network.proxy"))

    def requests_proxies(self) -> dict:
        """The global proxy in ``requests`` form, so JBrowser's own downloads (block lists,
        threat lists) take the same route as the pages."""
        cfg = self.global_config()
        if cfg["mode"] != "manual" or not cfg["host"]:
            return {}
        scheme = {"socks5": "socks5h", "https": "https"}.get(cfg["type"], "http")
        auth = ""
        if cfg["username"]:
            from urllib.parse import quote
            auth = f"{quote(cfg['username'], safe='')}:{quote(reveal_secret(cfg['password']), safe='')}@"
        url = f"{scheme}://{auth}{cfg['host']}:{cfg['port']}"
        return {"http": url, "https": url}

    def effective(self, space_proxy: dict | None) -> dict:
        if space_proxy and normalize_proxy(space_proxy)["mode"] != "inherit":
            cfg = normalize_proxy(space_proxy)
            if cfg["mode"] in ("direct", "system", "manual"):
                return cfg
        return self.global_config()

    @staticmethod
    def _qproxy(cfg: dict) -> QNetworkProxy:
        if cfg["mode"] == "system":
            QNetworkProxyFactory.setUseSystemConfiguration(True)
            return QNetworkProxy(QNetworkProxy.ProxyType.DefaultProxy)
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        if cfg["mode"] != "manual" or not cfg["host"] or cfg["type"] == "https":
            return QNetworkProxy(QNetworkProxy.ProxyType.NoProxy)
        ptype = QNetworkProxy.ProxyType.Socks5Proxy if cfg["type"] == "socks5" else QNetworkProxy.ProxyType.HttpProxy
        proxy = QNetworkProxy(ptype, cfg["host"], int(cfg["port"]))
        if cfg["username"]:
            proxy.setUser(cfg["username"])
            proxy.setPassword(reveal_secret(cfg["password"]))
        return proxy

    def apply(self, space_proxy: dict | None = None, force: bool = False) -> None:
        if self.flag_mode:
            return
        cfg = self.effective(space_proxy)
        key = (cfg["mode"], cfg["type"], cfg["host"], cfg["port"], cfg["username"], cfg["password"])
        if key == self._current_key and not force:
            return
        self._current_key = key
        QNetworkProxy.setApplicationProxy(self._qproxy(cfg))
        self.description = describe_proxy(cfg)
        self._kick()
        self.changed.emit(self.description)

    def _kick(self) -> None:
        """Make every profile's network context re-read the proxy configuration now."""
        for profile in self._profiles():
            try:
                page = QWebEnginePage(profile, self)
            except RuntimeError:
                continue
            self._kickers.append(page)
            page.loadFinished.connect(lambda _ok, p=page: self._drop_kicker(p))
            page.load(QUrl(self.KICK_URL))
            QTimer.singleShot(8000, lambda p=page: self._drop_kicker(p))

    def _drop_kicker(self, page: QWebEnginePage) -> None:
        if page in self._kickers:
            self._kickers.remove(page)
            page.deleteLater()

    def release_all(self) -> None:
        for page in list(self._kickers):
            self._drop_kicker(page)

    def credentials_for(self, host: str, space_proxy: dict | None) -> tuple[str, str] | None:
        for cfg in (self.effective(space_proxy), self.global_config()):
            if cfg["mode"] == "manual" and cfg["host"].lower() == host.lower() and cfg["username"]:
                return cfg["username"], reveal_secret(cfg["password"])
        return None

    def toggle_global(self) -> str:
        cfg = self.global_config()
        if cfg["mode"] == "manual":
            cfg["mode"] = "direct"
        elif cfg["host"]:
            cfg["mode"] = "manual"
        else:
            cfg["mode"] = "system" if cfg["mode"] == "direct" else "direct"
        self.settings.set("network.proxy", cfg)
        return describe_proxy(cfg)


# --------------------------------------------------------------- dev tools
class PortProbe(QObject):
    """Asynchronously checks whether something is listening on local ports."""

    result = pyqtSignal(int, bool)

    def probe(self, port: int, host: str = "127.0.0.1", timeout_ms: int = 600) -> None:
        sock = QTcpSocket(self)
        done = {"v": False}

        def finish(ok: bool):
            if done["v"]:
                return
            done["v"] = True
            self.result.emit(port, ok)
            sock.abort()
            sock.deleteLater()

        sock.connected.connect(lambda: finish(True))
        sock.errorOccurred.connect(lambda _e: finish(False))
        QTimer.singleShot(timeout_ms, lambda: finish(False))
        sock.connectToHost(host, port)
