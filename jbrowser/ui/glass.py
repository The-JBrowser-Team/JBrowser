"""GlassPopup: a small popup panel (the downloads bubble and similar), opaque like menus."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QWidget

from jbrowser.ui.backdrop import Backdrop
from jbrowser.ui.theme import theme


class GlassPopup(QFrame):
    """Closes when the user clicks elsewhere (Qt.Popup). Subclasses add their own layout."""

    def __init__(self, parent: QWidget | None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.backdrop = Backdrop(self, "popup")      # rounded corners, light/dark frame

    def show_below(self, anchor: QWidget, align_right: bool = True) -> None:
        """Open under ``anchor`` (right edges aligned), kept on the anchor's screen."""
        self.adjustSize()
        origin = anchor.mapToGlobal(QPoint(anchor.width() if align_right else 0, anchor.height() + 6))
        screen = QGuiApplication.screenAt(origin) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = origin.x() - self.width() if align_right else origin.x()
        x = max(avail.left() + 8, min(x, avail.right() - self.width() - 8))
        y = min(origin.y(), avail.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.fillRect(self.rect(), th.c("dialog_solid"))
        p.setPen(QPen(th.c("panel_border"), 1))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()
