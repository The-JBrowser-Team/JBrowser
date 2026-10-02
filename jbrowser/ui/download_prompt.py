"""The bubble that asks what to do with a flagged download (standard download protection)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from jbrowser.services.downloads import DownloadItem, describe
from jbrowser.ui.glass import GlassPopup
from jbrowser.ui.icons import draw_glyph
from jbrowser.ui.theme import theme

if TYPE_CHECKING:
    from jbrowser.context import AppContext


class _Glyph(QWidget):
    def __init__(self, name: str, token: str, parent: QWidget):
        super().__init__(parent)
        self.name, self.token = name, token
        self.setFixedSize(QSize(34, 34))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_glyph(p, QRectF(self.rect()), self.name, theme().c(self.token), 22)
        p.end()


class DownloadPrompt(GlassPopup):
    """Keep or delete a download that JBrowser flagged. Closing it leaves the choice in Downloads."""

    def __init__(self, ctx: "AppContext", item: DownloadItem, parent: QWidget | None):
        super().__init__(parent)
        self.ctx, self.item = ctx, item
        self.setObjectName("downloadPrompt")
        self.setFixedWidth(400)
        r = item.record
        host = QUrl(r.url).host() or QUrl(r.referrer).host()
        threat = "threat" in r.warning
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(_Glyph("error" if threat else "warning", "danger" if threat else "warning", self),
                       0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel("This download may be dangerous" if threat else "Keep this file?", self)
        f = title.font()
        f.setPointSizeF(11.5)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        name = QLabel(self)
        name.setText(name.fontMetrics().elidedText(r.filename, Qt.TextElideMode.ElideMiddle, 300))
        name.setToolTip(r.filename)
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(title)
        text.addWidget(name)
        head.addLayout(text, 1)
        lay.addLayout(head)
        why = QLabel(describe(r.warning, host) + " Only keep it if you trust where it came from.", self)
        why.setWordWrap(True)
        why.setProperty("muted", True)
        why.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lay.addWidget(why)
        hint = QLabel("Until you decide, it's saved so it can't be opened by accident.", self)
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        f2 = hint.font()
        f2.setPointSizeF(8.5)
        hint.setFont(f2)
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        self.keep_btn = QPushButton("Keep anyway" if threat else "Keep", self)
        self.keep_btn.setToolTip("Save the file under its real name")
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setToolTip("Stop the download and delete the file")
        self.delete_btn.setProperty("primary", True)
        self.delete_btn.setDefault(True)
        row.addWidget(self.keep_btn)
        row.addWidget(self.delete_btn)
        lay.addLayout(row)
        self.keep_btn.clicked.connect(self._keep)
        self.delete_btn.clicked.connect(self._delete)
        ctx.downloads.updated.connect(self._on_updated)

    def _keep(self) -> None:
        self.ctx.downloads.keep(self.item)
        self.close()

    def _delete(self) -> None:
        self.ctx.downloads.discard(self.item)
        self.close()

    def _on_updated(self, item: DownloadItem) -> None:
        if item is self.item and not item.waiting:
            self.close()                    # decided elsewhere (the Downloads window)

    def closeEvent(self, e) -> None:
        try:
            self.ctx.downloads.updated.disconnect(self._on_updated)
        except TypeError:
            pass
        super().closeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)
