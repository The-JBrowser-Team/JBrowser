"""Translucent tool windows (Settings, History, Downloads, ...).

They use the same technique as the main window: the whole window is client area, the
Windows 11 system backdrop (Acrylic / Mica) shows through transparent pixels, and a slim
custom caption provides drag, Snap Layouts and minimise / maximise / close.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QPoint, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from jbrowser.platform import win
from jbrowser.ui.backdrop import Backdrop, caption_hit
from jbrowser.ui.icons import app_icon, paint_logo
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton

CAPTION_H = 40
log = logging.getLogger(__name__)


class _Caption(QWidget):
    def __init__(self, window: "ChromeWindow", title: str):
        super().__init__(window)
        self.setFixedHeight(CAPTION_H)
        self.setProperty("dragRegion", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(10)
        self.logo = QWidget(self)
        self.logo.setFixedSize(16, 16)
        self.logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title = QLabel(title, self)
        self.title.setProperty("muted", True)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.logo)
        lay.addWidget(self.title)
        lay.addStretch(1)
        self.min_btn = IconButton("min", "Minimize", self, size=CAPTION_H, glyph_px=9, width=46)
        self.max_btn = IconButton("max", "Maximize", self, size=CAPTION_H, glyph_px=9, width=46)
        self.close_btn = IconButton("close", "Close", self, size=CAPTION_H, glyph_px=9, width=46, variant="close")
        for b in (self.min_btn, self.max_btn, self.close_btn):
            lay.addWidget(b)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        paint_logo(p, QRectF(self.logo.geometry()))
        p.end()


class ChromeWindow(QWidget):
    """Top-level window with a system backdrop. Subclasses populate ``self.root``."""

    def __init__(self, title: str, parent: QWidget | None = None, size: tuple[int, int] = (900, 620),
                 nav_width: int = 0):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(*size)
        self.setMinimumSize(520, 380)
        self.nav_width = nav_width
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.caption = _Caption(self, title)
        outer.addWidget(self.caption)
        self.body = QWidget(self)
        outer.addWidget(self.body, 1)
        self.root = QVBoxLayout(self.body)
        self.root.setContentsMargins(nav_width + 24, 14, 24, 18)
        self.root.setSpacing(12)
        c = self.caption
        c.min_btn.clicked.connect(self.showMinimized)
        c.max_btn.clicked.connect(self._toggle_max)
        c.close_btn.clicked.connect(self.close)
        self.native = win.NativeFrame(lambda: int(self.winId()), self.devicePixelRatioF, self._hit_test,
                                      c.max_btn.set_force_hover, c.max_btn.set_force_pressed, self._toggle_max)
        self.native.resizable = lambda: not self.isFullScreen()
        self.backdrop = Backdrop(self)               # the material and light/dark mode (ui/backdrop.py)
        self.native.on_system_change = self.backdrop.schedule
        theme().changed.connect(self.update)
        if parent is not None:
            g = parent.geometry()
            self.move(g.x() + (g.width() - size[0]) // 2, g.y() + max(20, (g.height() - size[1]) // 2))

    # --------------------------------------------------------------- frame
    def _toggle_max(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _hit_test(self, local: QPoint) -> int:
        return caption_hit(self, local, self.caption.max_btn)

    def nativeEvent(self, event_type, message):
        try:
            handled, result = self.native.handle(int(message))
        except Exception:  # never let an exception escape a window procedure
            log.exception("nativeEvent failed")
            return False, 0
        return (True, result) if handled else (False, 0)

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.Type.WindowStateChange:
            self.caption.max_btn.set_glyph("restore" if self.isMaximized() else "max")
        super().changeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    # --------------------------------------------------------------- paint
    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if th.translucent:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for layer in th.backdrop_layers():     # JBrowser's base colour, then the tint
                p.fillRect(self.rect(), layer)
        else:
            p.fillRect(self.rect(), th.c("window"))
        # Content layer: slightly raised surface, rounded where it meets the navigation pane.
        top = CAPTION_H
        r = QRectF(self.nav_width, top, self.width() - self.nav_width, self.height() - top)
        path = QPainterPath()
        if self.nav_width:
            path.addRoundedRect(r.adjusted(0, 0, 12, 12), 10, 10)
        else:
            path.addRect(r)
        p.fillPath(path, th.surface("layer"))
        p.end()
