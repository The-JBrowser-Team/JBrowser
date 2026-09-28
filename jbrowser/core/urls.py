"""URL heuristics: omnibox input classification, host/domain helpers."""
from __future__ import annotations

import ipaddress
import re

from PyQt6.QtCore import QUrl

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
_HOSTPORT_RE = re.compile(r"^(?P<host>\[[0-9a-fA-F:.]+\]|[^/:?#\s]+)(?::(?P<port>\d{1,5}))?(?P<rest>[/?#].*)?$")

INTERNAL_SCHEMES = {"http", "https", "file", "about", "data", "view-source", "chrome", "qrc",
                    "ftp", "blob", "javascript", "devtools", "ws", "wss", "chrome-error"}
EXTERNAL_SCHEMES = {"mailto", "tel", "sms", "callto", "magnet", "steam", "spotify", "zoommtg",
                    "msteams", "slack", "vscode", "ms-settings", "ms-windows-store", "discord"}

# Frequently used TLDs. Any two-letter alphabetic TLD (country codes) is also accepted.
_TLDS = set("""
com org net edu gov mil int info biz name pro aero coop museum mobi asia tel travel jobs cat
app dev io ai co me tv cc gg sh so to ly fm am xyz online site tech store blog cloud page
news live world today life space website fun top club shop art design studio agency
digital media network systems software solutions services support email link click
wiki one zone guru ninja rocks social chat game games video music photo photos pics
tools codes run build bot inc llc ltd company business finance money bank capital
health care law legal news press report review reviews science academy school college
university education community city london nyc berlin paris tokyo moe lol wtf fyi
test localhost local internal lan home arpa onion example invalid
""".split())

_MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "me.uk", "net.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "co.nz", "org.nz", "net.nz",
    "co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp", "co.kr", "or.kr", "com.cn", "net.cn",
    "org.cn", "gov.cn", "com.br", "net.br", "org.br", "com.mx", "com.ar", "co.in",
    "net.in", "org.in", "gov.in", "com.tr", "com.sg", "com.hk", "com.tw", "co.za",
    "com.my", "com.ph", "com.vn", "co.id", "co.il", "com.sa", "com.eg", "com.ng",
    "github.io", "gitlab.io", "blogspot.com", "herokuapp.com", "vercel.app",
    "netlify.app", "pages.dev", "workers.dev", "web.app", "firebaseapp.com",
    "azurewebsites.net", "cloudfront.net", "appspot.com", "fly.dev", "onrender.com",
}


def is_ip(host: str) -> bool:
    h = host.strip("[]")
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def is_local_host(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    if host in ("localhost", "0.0.0.0") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


def registrable_domain(host: str) -> str:
    """Approximate eTLD+1 (e.g. ``a.b.example.co.uk`` -> ``example.co.uk``)."""
    host = (host or "").lower().strip(".")
    if not host or is_ip(host):
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def same_site(host_a: str, host_b: str) -> bool:
    return registrable_domain(host_a) == registrable_domain(host_b)


def strip_www(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def origin_of(url: QUrl) -> str:
    if not url.isValid() or not url.host():
        return ""
    port = url.port()
    default = {"http": 80, "https": 443}.get(url.scheme(), -1)
    suffix = f":{port}" if port not in (-1, default) else ""
    return f"{url.scheme()}://{url.host().lower()}{suffix}"


def pretty_url(url: str | QUrl, keep_path: bool = True) -> str:
    q = url if isinstance(url, QUrl) else QUrl(url)
    if not q.isValid():
        return str(url)
    if q.scheme() in ("http", "https"):
        host = strip_www(q.host())
        port = f":{q.port()}" if q.port() != -1 else ""
        if not keep_path:
            return host + port
        rest = q.toString(QUrl.UrlFormattingOption.RemoveScheme
                          | QUrl.UrlFormattingOption.RemoveAuthority
                          | QUrl.UrlFormattingOption.RemoveFragment)
        rest = "" if rest == "/" else rest
        return f"{host}{port}{rest}"
    return q.toDisplayString()


def looks_like_url(text: str, dev_hosts: set[str] | None = None) -> bool:
    text = text.strip()
    if not text or " " in text:
        return False
    if _SCHEME_RE.match(text):
        scheme = text.split(":", 1)[0].lower()
        if scheme in INTERNAL_SCHEMES or scheme in EXTERNAL_SCHEMES:
            return True
        # "localhost:3000" or "example.com:8080" parse as scheme:path — verify below.
        if not re.match(r"^[^:]+:\d{1,5}([/?#].*)?$", text):
            return False
    m = _HOSTPORT_RE.match(text)
    if not m:
        return False
    host = m.group("host").lower()
    if dev_hosts and host in dev_hosts:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if is_ip(host):
        return True
    if "." not in host or host.startswith(".") or host.endswith("."):
        return False
    tld = host.rsplit(".", 1)[1]
    if not re.fullmatch(r"[a-z0-9\-]+", host.replace(".", "")):
        # Allow internationalised domains
        return bool(re.fullmatch(r"[^\s/]+\.[^\s/.]{2,}", host))
    return tld in _TLDS or (len(tld) == 2 and tld.isalpha()) or tld.startswith("xn--")


def to_url(text: str) -> QUrl:
    """Turn user input that ``looks_like_url`` into a navigable QUrl."""
    text = text.strip()
    if _SCHEME_RE.match(text):
        scheme = text.split(":", 1)[0].lower()
        if scheme in INTERNAL_SCHEMES or scheme in EXTERNAL_SCHEMES:
            return QUrl(text)
    m = _HOSTPORT_RE.match(text)
    host = (m.group("host") if m else text).lower()
    scheme = "http" if (is_local_host(host) or host.endswith((".test", ".local", ".internal", ".lan"))) \
        else "https"
    return QUrl.fromUserInput(f"{scheme}://{text}")


def display_title(title: str, url: str) -> str:
    if title and title.strip():
        return title.strip()
    return pretty_url(url) if url else "New card"
