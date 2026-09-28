"""Shared base for small modal dialogs (credentials, bookmark editor, space editor, ...).

Larger tool windows (History, Downloads, Settings, ...) use the translucent
:class:`jbrowser.ui.chrome_window.ChromeWindow` instead.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from jbrowser.platform import win
from jbrowser.ui.theme import theme


class JDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None, size: tuple[int, int] = (720, 520),
                 modal: bool = False):
        super().__init__(parent)
        self.setObjectName("JDialog")
        self.setWindowTitle(title)
        self.setModal(modal)
        self.resize(*size)
        # Dialogs keep the native frame, so they use a solid themed surface and a matching
        # caption colour (a translucent client area can't blend with Mica under a native
        # frame when windows are composited through Direct3D).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 16)
        self.root.setSpacing(12)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        hwnd = int(self.winId())
        th = theme()
        win.set_dark_title(hwnd, th.dark)
        win.set_caption_colors(hwnd, th.c("dialog_solid"), th.c("text"))


def heading(text: str, sub: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("subheading" if sub else "heading", True)
    return lab
