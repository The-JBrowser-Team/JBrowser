"""Download manager: accepts engine downloads, tracks progress, persists completed items."""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QStandardPaths, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage
from PyQt6.QtWidgets import QFileDialog, QWidget

from jbrowser.core.jsonstore import atomic_write_json, read_json
from jbrowser.core.settings import Settings
from jbrowser.platform.win import reveal_in_explorer

DR = QWebEngineDownloadRequest

# File types that can run code on Windows when opened.
DANGEROUS_EXTENSIONS = {
    ".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".ps1", ".psm1", ".psd1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".lnk",
    ".reg", ".dll", ".sys", ".iso", ".img", ".vhd", ".vhdx", ".application", ".appref-ms", ".msp", ".gadget",
    ".inf", ".scf", ".url", ".chm", ".xll", ".msc", ".settingcontent-ms", ".library-ms", ".sh", ".py", ".pyw",
}


def is_dangerous_file(name: str) -> bool:
    return os.path.splitext(name.lower().rstrip(". "))[1] in DANGEROUS_EXTENSIONS


# A flagged download is saved under this extra extension until the user keeps it, so it can't be
# opened by accident while it waits (the same idea as Chrome's "Unconfirmed" files).
HOLD_SUFFIX = ".unconfirmed"

# Why a download was flagged (see DownloadManager.assess). Shown in the warning and the downloads list.
REASONS = {
    "threat": "{host} is on a list of dangerous sites.",
    "type": "This type of file can run programs on your PC.",
    "insecure": "It's coming from a site without a secure connection (no HTTPS), so it could be changed on "
                "the way.",
}


def describe(reasons: list[str], host: str) -> str:
    """One readable sentence per reason, most serious first."""
    order = [r for r in ("threat", "type", "insecure") if r in reasons]
    return " ".join(REASONS[r].format(host=host or "This site") for r in order)


def write_mark_of_the_web(path: str, url: str, referrer: str, private: bool) -> bool:
    """Tag a downloaded file as coming from the internet (Zone.Identifier alternate data stream),
    so Windows SmartScreen and Office Protected View treat it accordingly."""
    lines = ["[ZoneTransfer]", "ZoneId=3"]
    if not private:
        if referrer.startswith(("http://", "https://")):
            lines.append(f"ReferrerUrl={referrer}")
        if url.startswith(("http://", "https://")):
            lines.append(f"HostUrl={url}")
    try:
        with open(path + ":Zone.Identifier", "w", encoding="utf-8", newline="") as fh:
            fh.write("\r\n".join(lines) + "\r\n")
        return True
    except OSError:
        return False


_STATE_NAMES = {
    DR.DownloadState.DownloadRequested: "requested",
    DR.DownloadState.DownloadInProgress: "in_progress",
    DR.DownloadState.DownloadCompleted: "completed",
    DR.DownloadState.DownloadCancelled: "cancelled",
    DR.DownloadState.DownloadInterrupted: "interrupted",
}


@dataclass
class DownloadRecord:
    url: str
    path: str
    filename: str
    total: int = -1
    received: int = 0
    state: str = "in_progress"
    space_id: str = ""
    error: str = ""
    referrer: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    warning: list = field(default_factory=list)   # reasons it was flagged ("threat", "type", "insecure")
    held: bool = False                              # saved as <name>.unconfirmed until the user keeps it
    final_path: str = ""                            # where a held file goes when kept


class DownloadItem(QObject):
    changed = pyqtSignal(object)

    def __init__(self, record: DownloadRecord, request: DR | None = None, tab_id: str = "",
                 incognito: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self.record = record
        self.request = request
        self.tab_id = tab_id
        self.incognito = incognito
        self.speed = 0.0
        self.verdict = ""                 # "keep" chosen while a held file is still downloading
        self._last_sample = (time.monotonic(), record.received)

    @property
    def active(self) -> bool:
        return self.record.state in ("in_progress", "requested", "paused")

    @property
    def waiting(self) -> bool:
        """A flagged download that needs the user's decision (keep or delete)."""
        return self.record.held and self.record.state not in ("cancelled", "interrupted", "deleted", "blocked")

    @property
    def paused(self) -> bool:
        return self.record.state == "paused"

    @property
    def fraction(self) -> float:
        r = self.record
        if r.total and r.total > 0:
            return max(0.0, min(1.0, r.received / r.total))
        return 1.0 if r.state == "completed" else 0.0

    def sample(self) -> None:
        now = time.monotonic()
        t0, b0 = self._last_sample
        dt = now - t0
        if dt >= 0.4:
            inst = (self.record.received - b0) / dt
            self.speed = inst if self.speed == 0 else self.speed * 0.6 + inst * 0.4
            self._last_sample = (now, self.record.received)


class DownloadManager(QObject):
    added = pyqtSignal(object)        # DownloadItem
    updated = pyqtSignal(object)      # DownloadItem
    removed = pyqtSignal(str)         # item id
    activeCountChanged = pyqtSignal(int)
    finished = pyqtSignal(object)     # DownloadItem (completed)
    flagged = pyqtSignal(object)      # DownloadItem that needs a decision: keep or delete (standard mode)
    blocked = pyqtSignal(object)      # DownloadItem stopped by strict protection

    def __init__(self, settings: Settings, store: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._store = store
        self._items: list[DownloadItem] = []
        self.session_started = time.time()
        self.unseen = 0                   # finished since the Downloads window was last opened
        self.finished.connect(self._on_finished)
        self.window_provider: Callable[[], QWidget | None] = lambda: None
        self.tab_resolver: Callable[[QWebEnginePage | None], str] = lambda _p: ""
        self.referrer_resolver: Callable[[QWebEnginePage | None], str] = lambda _p: ""
        # Hooks set by AppContext: is a host on the dangerous-site list? Is a URL a local / developer address?
        self.threat_check: Callable[[str], bool] = lambda _h: False
        self.local_check: Callable[[QUrl], bool] = lambda _u: False
        for d in read_json(store, []) or []:
            try:
                rec = DownloadRecord(**{k: v for k, v in d.items() if k in DownloadRecord.__dataclass_fields__})
            except TypeError:
                continue
            if rec.state in ("in_progress", "requested", "paused"):
                rec.state = "interrupted"
                rec.error = rec.error or "Interrupted when JBrowser closed"
            self._items.append(DownloadItem(rec, parent=self))
        self._dirty: set[str] = set()
        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._flush)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.save_now)

    # ------------------------------------------------------------ queries
    def items(self) -> list[DownloadItem]:
        return sorted(self._items, key=lambda i: i.record.started, reverse=True)

    def active_items(self) -> list[DownloadItem]:
        return [i for i in self._items if i.active]

    def overall_progress(self) -> float:
        act = [i for i in self.active_items() if i.record.total > 0]
        if not act:
            return 0.0
        return sum(i.record.received for i in act) / max(1, sum(i.record.total for i in act))

    def session_items(self) -> list[DownloadItem]:
        """Downloads started since JBrowser opened (they keep the ribbon's Downloads button visible)."""
        return [i for i in self._items if i.record.started >= self.session_started]

    def waiting_items(self) -> list[DownloadItem]:
        return [i for i in self._items if i.waiting]

    def _on_finished(self, _item: DownloadItem) -> None:
        self.unseen += 1

    def mark_seen(self) -> None:
        if self.unseen:
            self.unseen = 0
            self.activeCountChanged.emit(len(self.active_items()))

    def active_for_tab(self, tab_id: str) -> bool:
        return any(i.active and i.tab_id == tab_id for i in self._items)

    def active_in_space(self, space_id: str) -> bool:
        return any(i.active and i.record.space_id == space_id for i in self._items)

    # ------------------------------------------------------------ intake
    def default_directory(self) -> str:
        d = self.settings.get("downloads.directory") or ""
        if d and os.path.isdir(d):
            return d
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())

    @staticmethod
    def _unique(directory: str, name: str) -> str:
        base, ext = os.path.splitext(name or "download")
        candidate = f"{base}{ext}"
        n = 1
        while os.path.exists(os.path.join(directory, candidate)) or \
                os.path.exists(os.path.join(directory, candidate + ".crdownload")):
            candidate = f"{base} ({n}){ext}"
            n += 1
        return candidate

    @property
    def protection(self) -> str:
        """off | standard (warn and let the user keep or delete) | strict (block)."""
        mode = self.settings.get("downloads.protection")
        return mode if mode in ("off", "standard", "strict") else "standard"

    def assess(self, name: str, url: QUrl, referrer: str) -> list[str]:
        """Reasons to warn about a download: dangerous site, file that can run programs, no HTTPS."""
        if self.protection == "off":
            return []
        reasons = []
        hosts = {url.host()} | ({QUrl(referrer).host()} if referrer else set())
        if any(h and self.threat_check(h) for h in hosts):
            reasons.append("threat")
        if is_dangerous_file(name):
            reasons.append("type")
        pages = [url] + ([QUrl(referrer)] if referrer.startswith("http") else [])
        if any(u.scheme() == "http" and not self.local_check(u) for u in pages):
            reasons.append("insecure")
        return reasons

    def handle(self, req: DR, space_id: str, incognito: bool) -> None:
        tab_id = self.tab_resolver(req.page())
        referrer = self.referrer_resolver(req.page())
        reasons: list[str] = []
        final_path = ""
        if not req.isSavePageDownload():
            name = req.downloadFileName() or req.suggestedFileName() or "download"
            reasons = self.assess(name, req.url(), referrer)
            if reasons and self.protection == "strict":
                req.cancel()
                self._record_blocked(req, name, reasons, space_id, referrer, tab_id, incognito)
                return
            directory = self.default_directory()
            if self.settings.get("downloads.ask"):
                path, _ = QFileDialog.getSaveFileName(self.window_provider(), "Save file",
                                                      os.path.join(directory, name))
                if not path:
                    req.cancel()
                    return
                directory, name = os.path.dirname(path), os.path.basename(path)
            else:
                name = self._unique(directory, name)
            req.setDownloadDirectory(directory)
            if reasons:
                final_path = os.path.join(directory, name)
                name = self._unique(directory, name + HOLD_SUFFIX)
            req.setDownloadFileName(name)
        path = os.path.join(req.downloadDirectory(), req.downloadFileName())
        rec = DownloadRecord(url=req.url().toString(), path=path,
                             filename=os.path.basename(final_path) if final_path else req.downloadFileName(),
                             total=req.totalBytes(), space_id=space_id, referrer=referrer,
                             warning=reasons, held=bool(reasons), final_path=final_path)
        item = DownloadItem(rec, req, tab_id, incognito, self)
        self._items.append(item)
        req.receivedBytesChanged.connect(lambda *_, i=item: self._progress(i))
        req.totalBytesChanged.connect(lambda *_, i=item: self._progress(i))
        req.stateChanged.connect(lambda *_, i=item: self._state(i))
        req.isPausedChanged.connect(lambda *_, i=item: self._state(i))
        req.accept()
        self.added.emit(item)
        self._state(item)
        if item.record.held:
            self.flagged.emit(item)

    def _record_blocked(self, req: DR, name: str, reasons: list[str], space_id: str, referrer: str,
                        tab_id: str, incognito: bool) -> None:
        rec = DownloadRecord(url=req.url().toString(), path="", filename=name, state="blocked",
                             space_id=space_id, referrer=referrer, warning=reasons, finished=time.time(),
                             error=describe(reasons, req.url().host()))
        item = DownloadItem(rec, None, tab_id, incognito, self)
        self._items.append(item)
        self.added.emit(item)
        self.blocked.emit(item)
        self._schedule_save()

    def _progress(self, item: DownloadItem) -> None:
        req = item.request
        if req is None:
            return
        item.record.received = req.receivedBytes()
        item.record.total = req.totalBytes()
        item.sample()
        self._dirty.add(item.record.id)
        if not self._tick.isActive():
            self._tick.start()

    def _state(self, item: DownloadItem) -> None:
        req = item.request
        if req is None:
            return
        state = _STATE_NAMES.get(req.state(), "in_progress")
        if state == "in_progress" and req.isPaused():
            state = "paused"
        prev = item.record.state
        if item.verdict == "delete":
            # Deleted by the user: whatever the engine reports now, the file must not stay behind.
            if state in ("completed", "cancelled", "interrupted"):
                self._delete_file(item)
                item.record.state, item.speed = "deleted", 0.0
                self.updated.emit(item)
                self.activeCountChanged.emit(len(self.active_items()))
                self._schedule_save()
            return
        item.record.state = state
        item.record.received = req.receivedBytes()
        item.record.total = req.totalBytes()
        if state == "interrupted":
            item.record.error = req.interruptReasonString()
        if state in ("completed", "cancelled", "interrupted"):
            item.record.finished = time.time()
            item.speed = 0.0
            if state == "completed" and prev != "completed":
                if not req.isSavePageDownload():
                    write_mark_of_the_web(item.record.path, item.record.url, item.record.referrer, item.incognito)
                if item.record.held and item.verdict == "keep":
                    self._release(item)
                if not item.record.held:
                    self.finished.emit(item)
        self.updated.emit(item)
        self.activeCountChanged.emit(len(self.active_items()))
        self._schedule_save()

    def _flush(self) -> None:
        ids, self._dirty = self._dirty, set()
        for item in self._items:
            if item.record.id in ids:
                self.updated.emit(item)
        if not self._dirty:
            self._tick.stop()

    # ------------------------------------------------------------ actions
    def pause(self, item: DownloadItem) -> None:
        if item.request is not None and item.active:
            item.request.pause()

    def resume(self, item: DownloadItem) -> None:
        if item.request is not None and item.paused:
            item.request.resume()

    def cancel(self, item: DownloadItem) -> None:
        if item.request is not None and item.active:
            item.request.cancel()

    def keep(self, item: DownloadItem) -> None:
        """The user trusts a flagged download: give it its real name (now, or as soon as it finishes)."""
        if not item.record.held:
            return
        if item.record.state == "completed":
            self._release(item)
            self.finished.emit(item)
        else:
            item.verdict = "keep"
        self.updated.emit(item)
        self._schedule_save()

    def discard(self, item: DownloadItem) -> None:
        """Delete safely: stop a flagged (or any) download and remove the file it left behind."""
        item.verdict = "delete"
        if item.active:
            self.cancel(item)               # Chromium removes the partial file
        if item.record.state == "completed":
            self._delete_file(item)
        item.record.held = False
        item.record.state = "deleted"
        item.record.finished = item.record.finished or time.time()
        self.updated.emit(item)
        self.activeCountChanged.emit(len(self.active_items()))
        self._schedule_save()

    def _release(self, item: DownloadItem) -> None:
        r = item.record
        target = r.final_path or r.path.removesuffix(HOLD_SUFFIX)
        directory = os.path.dirname(target)
        if os.path.exists(target):
            target = os.path.join(directory, self._unique(directory, os.path.basename(target)))
        try:
            os.replace(r.path, target)        # the Zone.Identifier stream moves with the file
        except OSError:
            return
        r.path, r.filename, r.held, item.verdict = target, os.path.basename(target), False, ""

    @staticmethod
    def _delete_file(item: DownloadItem) -> None:
        for p in (item.record.path, item.record.path + ".crdownload"):
            try:
                if p and os.path.isfile(p):
                    os.remove(p)              # removes its Zone.Identifier stream too
            except OSError:
                pass

    @staticmethod
    def open(item: DownloadItem) -> None:
        if os.path.exists(item.record.path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(item.record.path))

    @staticmethod
    def show_in_folder(item: DownloadItem) -> None:
        reveal_in_explorer(item.record.path)

    def remove(self, item: DownloadItem) -> None:
        if item.active:
            self.cancel(item)
        if item in self._items:
            self._items.remove(item)
            self.removed.emit(item.record.id)
            self._schedule_save()

    def clear_finished(self) -> None:
        for item in [i for i in self._items if not i.active and not i.waiting]:
            self._items.remove(item)
            self.removed.emit(item.record.id)
        self._schedule_save()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def save_now(self) -> None:
        self._save_timer.stop()
        atomic_write_json(self._store, [asdict(i.record) for i in self._items if not i.incognito][-300:])
