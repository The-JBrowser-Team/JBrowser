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
        self._last_sample = (time.monotonic(), record.received)

    @property
    def active(self) -> bool:
        return self.record.state in ("in_progress", "requested", "paused")

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

    def __init__(self, settings: Settings, store: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._store = store
        self._items: list[DownloadItem] = []
        self.window_provider: Callable[[], QWidget | None] = lambda: None
        self.tab_resolver: Callable[[QWebEnginePage | None], str] = lambda _p: ""
        self.referrer_resolver: Callable[[QWebEnginePage | None], str] = lambda _p: ""
        # UI hook deciding whether a dangerous file may be kept: (filename, host, insecure) -> bool
        self.confirm_dangerous: Callable[[str, str, bool], bool] = lambda _n, _h, _i: True
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

    def handle(self, req: DR, space_id: str, incognito: bool) -> None:
        tab_id = self.tab_resolver(req.page())
        referrer = self.referrer_resolver(req.page())
        if not req.isSavePageDownload():
            name = req.downloadFileName() or req.suggestedFileName() or "download"
            if self.settings.get("downloads.protect") and is_dangerous_file(name):
                insecure = req.url().scheme() == "http"
                if not self.confirm_dangerous(name, req.url().host(), insecure):
                    req.cancel()
                    return
            directory = self.default_directory()
            if self.settings.get("downloads.ask"):
                path, _ = QFileDialog.getSaveFileName(self.window_provider(), "Save file",
                                                      os.path.join(directory, name))
                if not path:
                    req.cancel()
                    return
                req.setDownloadDirectory(os.path.dirname(path))
                req.setDownloadFileName(os.path.basename(path))
            else:
                req.setDownloadDirectory(directory)
                req.setDownloadFileName(self._unique(directory, name))
        path = os.path.join(req.downloadDirectory(), req.downloadFileName())
        rec = DownloadRecord(url=req.url().toString(), path=path, filename=req.downloadFileName(),
                             total=req.totalBytes(), space_id=space_id, referrer=referrer)
        item = DownloadItem(rec, req, tab_id, incognito, self)
        self._items.append(item)
        req.receivedBytesChanged.connect(lambda *_, i=item: self._progress(i))
        req.totalBytesChanged.connect(lambda *_, i=item: self._progress(i))
        req.stateChanged.connect(lambda *_, i=item: self._state(i))
        req.isPausedChanged.connect(lambda *_, i=item: self._state(i))
        req.accept()
        self.added.emit(item)
        self._state(item)

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
        for item in [i for i in self._items if not i.active]:
            self._items.remove(item)
            self.removed.emit(item.record.id)
        self._schedule_save()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def save_now(self) -> None:
        self._save_timer.stop()
        atomic_write_json(self._store, [asdict(i.record) for i in self._items if not i.incognito][-300:])
