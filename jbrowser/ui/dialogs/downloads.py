"""Download manager window: live progress, speed/ETA, pause/resume/cancel and file launcher."""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import QEvent, QFileInfo, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QFileIconProvider, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from jbrowser.services.downloads import DownloadItem, describe
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
    """One download. A finished file opens when you click anywhere on its row."""

    def __init__(self, dlg: "DownloadsDialog", item: DownloadItem):
        super().__init__(dlg)
        self.dlg = dlg
        self.item = item
        self._hover = False
        self._pressed = False
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
        self.keep = QPushButton("Keep", self)
        self.keep.setToolTip("Save the file under its real name")
        self.discard = QPushButton("Delete", self)
        self.discard.setToolTip("Stop the download and delete the file")
        self.discard.setProperty("primary", True)
        self.pause = IconButton("pause", "Pause", self, size=32, glyph_px=12)
        self.cancel = IconButton("close", "Cancel", self, size=32, glyph_px=10)
        self.folder = IconButton("folder_open", "Show in folder", self, size=32, glyph_px=13)
        self.remove = IconButton("delete", "Remove from list", self, size=32, glyph_px=12)
        for b in (self.keep, self.discard, self.pause, self.cancel, self.folder, self.remove):
            lay.addWidget(b)
        m = dlg.ctx.downloads
        self.keep.clicked.connect(lambda: m.keep(item))
        self.discard.clicked.connect(lambda: m.discard(item))
        self.pause.clicked.connect(lambda: m.resume(item) if item.paused else m.pause(item))
        self.cancel.clicked.connect(lambda: m.cancel(item))
        self.folder.clicked.connect(lambda: m.show_in_folder(item))
        self.remove.clicked.connect(lambda: m.remove(item))
        self.refresh()

    def openable(self) -> bool:
        r = self.item.record
        return r.state == "completed" and not r.held and os.path.exists(r.path)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = self._pressed = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.openable():
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._pressed and e.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()) and self.openable():
                self.dlg.ctx.downloads.open(self.item)

    def refresh(self) -> None:
        r = self.item.record
        self.name.setText(r.filename)
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
        waiting = self.item.waiting
        host = QUrl(r.url).host() or QUrl(r.referrer).host()
        if r.state == "in_progress":
            parts = [f"{int(self.item.fraction * 100)}%"] if r.total > 0 else []
            parts.append(f"{human_size(r.received)} of {human_size(r.total)}" if r.total > 0
                         else human_size(r.received))
            if self.item.speed > 1:
                parts.append(f"{human_size(self.item.speed)}/s")
                if r.total > 0:
                    parts.append(human_eta((r.total - r.received) / max(1.0, self.item.speed)))
            text = " · ".join(parts)
        elif r.state == "paused":
            text = f"Paused · {int(self.item.fraction * 100)}% · {human_size(r.received)} of {human_size(r.total)}"
        elif r.state == "completed":
            exists = os.path.exists(r.path)
            when = time.strftime("%d %b %Y %H:%M", time.localtime(r.finished or r.started))
            text = f"{human_size(r.total if r.total > 0 else r.received)} · {when}" + (
                "" if exists else " · file moved or deleted")
        elif r.state == "cancelled":
            text = "Cancelled"
        elif r.state == "deleted":
            text = "Deleted"
        elif r.state == "blocked":
            text = f"Blocked: {r.error}"
        else:
            text = f"Failed: {r.error or 'interrupted'}"
        if waiting:
            text = describe(r.warning, host) + " Keep it?" + (f"  ({text})" if active else "")
        self.status.setText(text)
        self.status.setWordWrap(waiting or r.state == "blocked")
        self.status.setProperty("muted", not (waiting or r.state == "blocked"))
        self.status.setStyleSheet(f"color: {theme().c('warning').name()};" if waiting else
                                  f"color: {theme().c('danger').name()};" if r.state == "blocked" else "")
        self.keep.setVisible(waiting)
        self.discard.setVisible(waiting)
        self.pause.setVisible(active and self.item.request is not None)
        self.pause.set_glyph("play" if self.item.paused else "pause")
        self.pause.setToolTip("Resume" if self.item.paused else "Pause")
        self.cancel.setVisible(active and not waiting)
        done = r.state == "completed" and not waiting
        self.folder.setVisible(done)
        self.remove.setVisible(not active and not waiting)
        can_open = self.openable()
        self.setCursor(Qt.CursorShape.PointingHandCursor if can_open else Qt.CursorShape.ArrowCursor)
        self.setToolTip(f"Open {r.filename}\n{r.path}" if can_open else f"{r.path or r.filename}\n{r.url}")

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.fillPath(path, th.c("input"))
        if self.openable() and (self._hover or self._pressed):
            p.fillPath(path, th.c("pressed" if self._pressed else "hover"))
        if self.item.waiting:
            p.setPen(QPen(th.c("warning"), 1))
            p.drawPath(path)
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

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.ctx.downloads.mark_seen()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.ctx.downloads.mark_seen()

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
