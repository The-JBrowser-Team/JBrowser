"""Phishing & malware protection.

Top-level navigations are checked against a local list of known malicious hosts (URLhaus
malware hosts + Phishing Army). The list is refreshed in the background about once a week;
lookups never leave the machine. Blocked pages get an interstitial with "Go back" and an
explicit "Continue anyway" escape hatch that is remembered only for the current session.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_bytes
from jbrowser.core.settings import Settings
from jbrowser.core.urls import is_local_host, strip_www
from jbrowser.core.workers import fetch_text
from jbrowser.services.privacy import parse_filter_list

log = logging.getLogger(__name__)

THREAT_SOURCES = [
    ("URLhaus malware hosts (abuse.ch)", "https://urlhaus.abuse.ch/downloads/hostfile/"),
    ("Phishing Army", "https://phishing.army/download/phishing_army_blocklist.txt"),
]
REFRESH_SECONDS = 7 * 24 * 3600

# Never treat these as threats even if a feed lists them by mistake (huge shared hosts).
_NEVER_BLOCK = {"google.com", "youtube.com", "microsoft.com", "github.com", "githubusercontent.com",
                "raw.githubusercontent.com", "drive.google.com", "docs.google.com", "dropbox.com",
                "onedrive.live.com", "1drv.ms", "sharepoint.com", "amazonaws.com", "cloudfront.net",
                "blogspot.com", "sites.google.com", "forms.gle", "bit.ly", "t.me", "discord.com",
                "discordapp.com", "cdn.discordapp.com", "archive.org", "wikipedia.org"}


class ThreatService(QObject):
    updated = pyqtSignal(int, str)  # number of hosts, error text

    def __init__(self, settings: Settings, list_file: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._file = list_file
        self._hosts: set[str] = set()
        self._session_allow: set[str] = set()
        self._worker: _ThreatUpdater | None = None
        self.proxy_provider = lambda: {}   # requests-style proxies (set by AppContext)
        self.load()

    def load(self) -> None:
        try:
            self._hosts = {h.strip() for h in self._file.read_text("utf-8").splitlines() if h.strip()}
        except OSError:
            self._hosts = set()
        self._hosts -= _NEVER_BLOCK

    def __len__(self) -> int:
        return len(self._hosts)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("privacy.threat_protection"))

    def match(self, host: str) -> bool:
        """True when ``host`` (or a parent domain) is a known phishing / malware host."""
        if not self.enabled or not host:
            return False
        host = strip_www(host.lower())
        if is_local_host(host) or host in self._session_allow:
            return False
        labels = host.split(".")
        for i in range(len(labels) - 1):
            if ".".join(labels[i:]) in self._hosts:
                return True
        return False

    def allow_for_session(self, host: str) -> None:
        self._session_allow.add(strip_www(host.lower()))

    def add_hosts(self, hosts: set[str]) -> None:
        """Merge extra hosts (used by tests and by the updater)."""
        self._hosts |= {h.lower() for h in hosts} - _NEVER_BLOCK

    def maybe_refresh(self) -> None:
        if not self.enabled:
            return
        last = float(self.settings.get("privacy.threatlist_updated") or 0)
        if time.time() - last > REFRESH_SECONDS or not self._hosts:
            self.refresh()

    def refresh(self, proxies: dict | None = None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            return False
        self._worker = _ThreatUpdater([u for _, u in THREAT_SOURCES], self._file,
                                      proxies if proxies is not None else self.proxy_provider(), self)
        self._worker.done.connect(self._on_done)
        self._worker.start()
        return True

    def _on_done(self, count: int, error: str) -> None:
        self.load()
        if count:
            self.settings.set("privacy.threatlist_updated", time.time())
        if error:
            log.info("Threat list update issues: %s", error)
        self.updated.emit(len(self._hosts), error)


class _ThreatUpdater(QThread):
    done = pyqtSignal(int, str)

    def __init__(self, urls: list[str], out: Path, proxies: dict, parent: QObject | None = None):
        super().__init__(parent)
        self._urls = urls
        self._out = out
        self._proxies = proxies

    def run(self) -> None:  # worker thread
        hosts: set[str] = set()
        errors = []
        headers = {"User-Agent": "JBrowser threat list updater"}
        for url in self._urls:
            if self.isInterruptionRequested():
                return
            try:
                hosts |= parse_filter_list(fetch_text(url, headers, self._proxies, self.isInterruptionRequested))
            except InterruptedError:
                return
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        if self.isInterruptionRequested():
            return
        if hosts:
            atomic_write_bytes(self._out, "\n".join(sorted(hosts)).encode("utf-8"))
        self.done.emit(len(hosts), "\n".join(errors))
