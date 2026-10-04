"""GlassPopup: a small popup window with the system Acrylic behind it, like the Archive and menus."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QWidget

from jbrowser.ui.backdrop import Backdrop
from jbrowser.ui.theme import theme

GLASS_ALPHA = (0.42, 0.50)      # how much of the dialog colour lies over the Acrylic (dark, light)


class GlassPopup(QFrame):
    """Closes when the user clicks elsewhere (Qt.Popup). Subclasses add their own layout."""

    def __init__(self, parent: QWidget | None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.backdrop = Backdrop(self, "popup")

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
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.backdrop.active and th.see_through:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            layer = th.c("dialog")
            layer.setAlphaF(GLASS_ALPHA[0 if th.dark else 1])
            p.fillRect(self.rect(), layer)
            wash = th.backdrop_wash()
            if wash is not None:
                p.fillRect(self.rect(), wash)
        else:
            p.fillRect(self.rect(), th.c("dialog_solid"))
            p.setPen(QPen(th.c("panel_border"), 1))
            p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()
