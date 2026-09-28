"""Download manager window: live progress, speed/ETA, pause/resume/cancel and file launcher."""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import QFileInfo, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPainter, QPainterPath
from PyQt6.QtWidgets import (QFileIconProvider, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from jbrowser.services.downloads import DownloadItem
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import heading
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton


def human_size(n: float) -> str:
    if n < 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s left"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s left"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m left"


class DownloadRow(QFrame):
    def __init__(self, dlg: "DownloadsDialog", item: DownloadItem):
        super().__init__(dlg)
        self.dlg = dlg
        self.item = item
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedSize(32, 32)
        lay.addWidget(self.icon)
        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.name = QLabel()
        f = self.name.font()
        f.setPointSizeF(10)
        self.name.setFont(f)
        self.status = QLabel()
        self.status.setProperty("muted", True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        self.bar.setRange(0, 1000)
        mid.addWidget(self.name)
        mid.addWidget(self.bar)
        mid.addWidget(self.status)
        lay.addLayout(mid, 1)
        self.pause = IconButton("pause", "Pause", self, size=32, glyph_px=12)
        self.cancel = IconButton("close", "Cancel", self, size=32, glyph_px=10)
        self.open = IconButton("open_file", "Open file", self, size=32, glyph_px=13)
        self.folder = IconButton("folder_open", "Show in folder", self, size=32, glyph_px=13)
        self.remove = IconButton("delete", "Remove from list", self, size=32, glyph_px=12)
        for b in (self.pause, self.cancel, self.open, self.folder, self.remove):
            lay.addWidget(b)
        m = dlg.ctx.downloads
        self.pause.clicked.connect(lambda: m.resume(item) if item.paused else m.pause(item))
        self.cancel.clicked.connect(lambda: m.cancel(item))
        self.open.clicked.connect(lambda: m.open(item))
        self.folder.clicked.connect(lambda: m.show_in_folder(item))
        self.remove.clicked.connect(lambda: m.remove(item))
        self.refresh()

    def refresh(self) -> None:
        r = self.item.record
        self.name.setText(r.filename)
        self.name.setToolTip(f"{r.path}\n{r.url}")
        info = QFileInfo(r.path)
        if not self.icon.pixmap() or self.icon.pixmap().isNull():
            ic = QFileIconProvider().icon(info) if info.exists() else QFileIconProvider().icon(
                QFileIconProvider.IconType.File)
            self.icon.setPixmap(ic.pixmap(QSize(32, 32)))
        active = self.item.active
        self.bar.setVisible(active)
        self.bar.setValue(int(self.item.fraction * 1000))
        if r.total <= 0 and active:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
        if r.state == "in_progress":
            parts = [f"{human_size(r.received)} of {human_size(r.total)}" if r.total > 0 else human_size(r.received)]
            if self.item.speed > 1:
                parts.append(f"{human_size(self.item.speed)}/s")
                if r.total > 0:
                    parts.append(human_eta((r.total - r.received) / max(1.0, self.item.speed)))
            text = " · ".join(parts)
        elif r.state == "paused":
            text = f"Paused · {human_size(r.received)} of {human_size(r.total)}"
        elif r.state == "completed":
            exists = os.path.exists(r.path)
            when = time.strftime("%d %b %Y %H:%M", time.localtime(r.finished or r.started))
            text = f"{human_size(r.total if r.total > 0 else r.received)} · {when}" + ("" if exists else " · file moved or deleted")
        elif r.state == "cancelled":
            text = "Cancelled"
        else:
            text = f"Failed: {r.error or 'interrupted'}"
        self.status.setText(text)
        self.pause.setVisible(active and self.item.request is not None)
        self.pause.set_glyph("play" if self.item.paused else "pause")
        self.pause.setToolTip("Resume" if self.item.paused else "Pause")
        self.cancel.setVisible(active)
        done = r.state == "completed"
        self.open.setVisible(done and os.path.exists(r.path))
        self.folder.setVisible(done)
        self.remove.setVisible(not active)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.fillPath(path, theme().c("input"))
        p.end()


class DownloadsDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Downloads", parent, (760, 560))
        self.ctx = ctx
        self.ui = ui
        top = QHBoxLayout()
        top.addWidget(heading("Downloads"))
        top.addStretch(1)
        folder = QPushButton("Open downloads folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(ctx.downloads.default_directory())))
        clear = QPushButton("Clear finished")
        clear.clicked.connect(ctx.downloads.clear_finished)
        top.addWidget(folder)
        top.addWidget(clear)
        self.root.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.list = QVBoxLayout(self.body)
        self.list.setContentsMargins(0, 0, 6, 0)
        self.list.setSpacing(8)
        self.list.addStretch(1)
        self.scroll.setWidget(self.body)
        self.root.addWidget(self.scroll, 1)
        self.empty = QLabel("No downloads yet.")
        self.empty.setProperty("muted", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root.addWidget(self.empty)
        self.rows: dict[str, DownloadRow] = {}
        m = ctx.downloads
        m.added.connect(self._add)
        m.updated.connect(self._update)
        m.removed.connect(self._remove)
        for item in reversed(m.items()):
            self._add(item)

    def _add(self, item: DownloadItem) -> None:
        if item.record.id in self.rows:
            return
        row = DownloadRow(self, item)
        self.rows[item.record.id] = row
        self.list.insertWidget(0, row)
        self.empty.setVisible(False)

    def _update(self, item: DownloadItem) -> None:
        row = self.rows.get(item.record.id)
        if row is not None:
            row.refresh()

    def _remove(self, item_id: str) -> None:
        row = self.rows.pop(item_id, None)
        if row is not None:
            row.deleteLater()
        self.empty.setVisible(not self.rows)
