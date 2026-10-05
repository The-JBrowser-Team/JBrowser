"""Shared base for small modal dialogs (credentials, bookmark editor, space editor, ...).

Larger tool windows (History, Downloads, Settings, ...) use
:class:`jbrowser.ui.chrome_window.ChromeWindow` instead.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from jbrowser.ui.backdrop import Backdrop
from jbrowser.ui.theme import theme


class JDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None, size: tuple[int, int] = (720, 520),
                 modal: bool = False):
        super().__init__(parent)
        self.setObjectName("JDialog")
        self.setWindowTitle(title)
        self.setModal(modal)
        self.resize(*size)
        # Dialogs keep the native frame: a solid themed surface (painted below, with the colour tint) and a
        # matching caption colour.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.backdrop = Backdrop(self, "frame")      # light/dark title bar in step with the theme
        theme().changed.connect(self.update)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 16)
        self.root.setSpacing(12)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(e.rect(), theme().c("dialog_solid"))
        p.end()


def heading(text: str, sub: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("subheading" if sub else "heading", True)
    return lab
