"""Automatic updates from GitHub Releases.

How it works
------------
1. Once a day (and when you press *Check for updates*) JBrowser asks the GitHub Releases
   API for the latest published release of ``GITHUB_REPO``::

       GET https://api.github.com/repos/<owner>/<repo>/releases/latest

2. If the release's version (its tag, e.g. ``v1.4.1``) is newer than ``__version__``, the
   ribbon shows an *Update* button.
3. Installing downloads ``JBrowser-Setup-<version>.exe`` from the release and verifies it
   against ``JBrowser-Setup-<version>.exe.sha256`` (also a release asset). A download that
   does not match is deleted and never run.
4. JBrowser starts a small hidden PowerShell helper and closes. The helper waits until
   JBrowser (and its web processes) have exited, then runs the installer with ``/SILENT
   /RELAUNCH``. The installer replaces the program files and starts the new version. Your data in
   ``%APPDATA%\\JBrowser`` is never touched by an update.

Only installed copies (with ``unins000.exe`` beside ``JBrowser.exe``) update themselves.
Portable builds and source checkouts are told about new versions and can open the
release page instead. Releases are made with ``tools/release.ps1`` (see docs/RELEASING.md).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from jbrowser import APP_NAME, GITHUB_REPO, RELEASES_PAGE, __version__
from jbrowser.core.settings import Settings
from jbrowser.platform import win

log = logging.getLogger(__name__)

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CHECK_INTERVAL_S = 24 * 3600
INSTALLER_RE = re.compile(r"^JBrowser-Setup-(\d+\.\d+\.\d+)\.exe$", re.IGNORECASE)
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024


def parse_version(text: str) -> tuple[int, int, int] | None:
    """``"v1.4.0"`` / ``"1.4"`` -> ``(1, 4, 0)``; anything else -> ``None``."""
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


@dataclass
class UpdateInfo:
    version: str
    tag: str
    title: str
    notes: str
    page_url: str
    installer_name: str = ""
    installer_url: str = ""
    installer_size: int = 0
    checksum_url: str = ""
    published: str = ""


class UpdateService(QObject):
    """Checks for, downloads, verifies and launches updates. All network I/O is asynchronous."""

    stateChanged = pyqtSignal(str)            # idle | checking | available | uptodate | error | downloading | ready
    available = pyqtSignal(object)            # UpdateInfo (only for versions the user has not skipped)
    downloadProgress = pyqtSignal(int, int)   # bytes received, bytes total (-1 when unknown)
    readyToInstall = pyqtSignal(str)          # path of the verified installer

    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.nam = QNetworkAccessManager(self)
        self.state = "idle"
        self.message = ""
        self.latest: UpdateInfo | None = None
        self.installer_path = ""
        self._reply: QNetworkReply | None = None
        self._file = None
        self._hash = None
        self._expected_sha = ""
        self._manual = False
        self._timer = QTimer(self)
        self._timer.setInterval(3600 * 1000)          # hourly look at "is a daily check due?"
        self._timer.timeout.connect(self.maybe_check)

    # ------------------------------------------------------------------ facts
    @property
    def current_version(self) -> str:
        return __version__

    @staticmethod
    def installed_copy() -> bool:
        """True for an installer-managed copy, which can update itself."""
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            return False
        return os.path.exists(os.path.join(os.path.dirname(sys.executable), "unins000.exe"))

    def _set_state(self, state: str, message: str = "") -> None:
        self.state = state
        self.message = message
        self.stateChanged.emit(state)

    # ------------------------------------------------------------------ checking
    def start(self, delay_ms: int = 15000) -> None:
        QTimer.singleShot(delay_ms, self.maybe_check)
        self._timer.start()

    def maybe_check(self) -> None:
        if not self.settings.get("updates.auto_check"):
            return
        last = float(self.settings.get("updates.last_check") or 0)
        if time.time() - last >= CHECK_INTERVAL_S:
            self.check(manual=False)

    def check(self, manual: bool = True) -> None:
        if self.state in ("checking", "downloading"):
            return
        self._manual = manual
        req = QNetworkRequest(QUrl(API_LATEST))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"X-GitHub-Api-Version", b"2022-11-28")
        req.setRawHeader(b"User-Agent", f"{APP_NAME}/{__version__} (update check)".encode())
        req.setTransferTimeout(20000)
        self._set_state("checking", "Checking for updates…")
        reply = self.nam.get(req)
        reply.finished.connect(lambda r=reply: self._on_checked(r))

    def _on_checked(self, reply: QNetworkReply) -> None:
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        body = bytes(reply.readAll())
        if reply.error() != QNetworkReply.NetworkError.NoError and status not in (404,):
            self._set_state("error", f"Could not reach GitHub ({reply.errorString()})")
            log.info("Update check failed: %s", reply.errorString())
            return
        self.settings.set("updates.last_check", time.time())
        if status == 404:
            self._set_state("uptodate", "No releases have been published yet")
            return
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:
            self._set_state("error", "GitHub sent an unexpected answer")
            return
        info = self._parse_release(data)
        if info is None:
            self._set_state("error", "The latest release has no version number")
            return
        self.latest = info
        if is_newer(info.version):
            self._set_state("available", f"JBrowser {info.version} is available")
            if self._manual or self.settings.get("updates.skipped") != info.version:
                self.available.emit(info)
        else:
            self._set_state("uptodate", f"You have the latest version ({__version__})")

    @staticmethod
    def _parse_release(data: dict) -> UpdateInfo | None:
        tag = str(data.get("tag_name") or "")
        version = parse_version(tag)
        if version is None:
            return None
        info = UpdateInfo(version=".".join(map(str, version)), tag=tag,
                          title=str(data.get("name") or tag), notes=str(data.get("body") or ""),
                          page_url=str(data.get("html_url") or RELEASES_PAGE),
                          published=str(data.get("published_at") or ""))
        assets = {a.get("name", ""): a for a in data.get("assets") or [] if isinstance(a, dict)}
        for name, asset in assets.items():
            if INSTALLER_RE.match(name):
                info.installer_name = name
                info.installer_url = str(asset.get("browser_download_url") or "")
                info.installer_size = int(asset.get("size") or 0)
                checksum = assets.get(name + ".sha256")
                if checksum:
                    info.checksum_url = str(checksum.get("browser_download_url") or "")
                break
        return info

    def skip(self, version: str) -> None:
        self.settings.set("updates.skipped", version)

    # ------------------------------------------------------------------ downloading
    def can_install(self) -> bool:
        info = self.latest
        return bool(self.installed_copy() and info and info.installer_url and info.checksum_url)

    def download(self) -> None:
        """Fetch the checksum, then the installer; verify before announcing it."""
        info = self.latest
        if info is None or not info.installer_url:
            self._set_state("error", "This release has no installer to download")
            return
        if not info.checksum_url:
            self._set_state("error", "This release has no checksum, so it cannot be verified")
            return
        if self.state == "downloading":
            return
        self._set_state("downloading", "Preparing the download…")
        req = self._asset_request(info.checksum_url)
        reply = self.nam.get(req)
        reply.finished.connect(lambda r=reply: self._on_checksum(r))

    @staticmethod
    def _asset_request(url: str) -> QNetworkRequest:
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", f"{APP_NAME}/{__version__} (updater)".encode())
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        return req

    def _on_checksum(self, reply: QNetworkReply) -> None:
        reply.deleteLater()
        text = bytes(reply.readAll()).decode("utf-8", "replace")
        m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
        if reply.error() != QNetworkReply.NetworkError.NoError or not m:
            self._set_state("error", "Could not download the update's checksum")
            return
        self._expected_sha = m.group(1).lower()
        folder = os.path.join(tempfile.gettempdir(), "JBrowser-Update")
        os.makedirs(folder, exist_ok=True)
        self.installer_path = os.path.join(folder, self.latest.installer_name)
        try:
            self._file = open(self.installer_path + ".part", "wb")
        except OSError as exc:
            self._set_state("error", f"Could not save the update: {exc}")
            return
        self._hash = hashlib.sha256()
        reply = self.nam.get(self._asset_request(self.latest.installer_url))
        self._reply = reply
        reply.readyRead.connect(self._on_data)
        reply.downloadProgress.connect(lambda got, total: self.downloadProgress.emit(int(got), int(total)))
        reply.finished.connect(self._on_installer)
        self._set_state("downloading", f"Downloading JBrowser {self.latest.version}…")

    def _on_data(self) -> None:
        reply = self._reply
        if reply is None or self._file is None:
            return
        chunk = bytes(reply.readAll())
        self._file.write(chunk)
        self._hash.update(chunk)
        if self._file.tell() > MAX_INSTALLER_BYTES:
            reply.abort()

    def _on_installer(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        reply.deleteLater()
        self._on_data()
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        err = reply.errorString()
        if self._file is not None:
            self._file.close()
            self._file = None
        part = self.installer_path + ".part"
        if not ok:
            self._discard(part)
            self._set_state("error", "The download was cancelled" if "cancel" in err.lower()
                            else f"The download failed ({err})")
            return
        digest = self._hash.hexdigest()
        if digest != self._expected_sha:
            self._discard(part)
            log.warning("Update rejected: SHA-256 %s does not match %s", digest, self._expected_sha)
            self._set_state("error", "The downloaded update did not pass its safety check and was deleted")
            return
        try:
            if os.path.exists(self.installer_path):
                os.remove(self.installer_path)
            os.replace(part, self.installer_path)
        except OSError as exc:
            self._set_state("error", f"Could not prepare the update: {exc}")
            return
        problem = self.signature_problem(self.installer_path)
        if problem:
            self._discard(self.installer_path)
            log.warning("Update rejected: %s", problem)
            self._set_state("error", "The downloaded update is not signed by JBrowser's publisher and was deleted")
            return
        self._set_state("ready", f"JBrowser {self.latest.version} is ready to install")
        self.readyToInstall.emit(self.installer_path)

    @staticmethod
    def signature_problem(installer: str) -> str:
        """Once JBrowser itself is code-signed, an update must be signed by the same publisher.
        Returns why ``installer`` fails that, or "" (also while JBrowser is unsigned)."""
        if not getattr(sys, "frozen", False):
            return ""
        status, publisher = win.authenticode(sys.executable)
        if status != "Valid":
            return ""                                  # an unsigned JBrowser accepts unsigned updates
        new_status, new_publisher = win.authenticode(installer)
        if new_status != "Valid":
            return f"signature {new_status} (JBrowser is signed by {publisher})"
        if new_publisher != publisher:
            return f"signed by {new_publisher}, not {publisher}"
        return ""

    def cancel_download(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    @staticmethod
    def _discard(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    # ------------------------------------------------------------------ installing
    def launch_installer(self, pid: int) -> bool:
        """Start the hidden helper that waits for this process to exit and then runs the installer.
        The caller must close JBrowser straight afterwards."""
        path = self.installer_path
        if not path or not os.path.exists(path):
            return False
        app_dir = os.path.dirname(sys.executable)

        def q(s: str) -> str:                       # PowerShell single-quoted literal
            return "'" + s.replace("'", "''") + "'"
        script = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            f"Wait-Process -Id {int(pid)} -Timeout 90; "
            "Get-Process QtWebEngineProcess | Where-Object { $_.Path -like " + q(app_dir + "*") + " } "
            "| Wait-Process -Timeout 30; "
            "Start-Sleep -Milliseconds 600; "
            # /RELAUNCH is JBrowser's own switch: the installer starts the new version when it finishes.
            f"Start-Process -FilePath {q(path)} -ArgumentList '/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',"
            "'/RELAUNCH'"
        )
        started = QProcess.startDetached("powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                                            "Bypass", "-WindowStyle", "Hidden", "-Command", script])
        ok = started[0] if isinstance(started, tuple) else bool(started)
        log.info("Update helper %s for %s", "started" if ok else "failed to start", path)
        return bool(ok)
