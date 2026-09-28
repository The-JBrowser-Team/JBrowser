"""Screen / window picker for getDisplayMedia() screen-sharing requests."""
from __future__ import annotations

from PyQt6.QtWidgets import QDialogButtonBox, QLabel, QListView, QTabWidget, QWidget

from jbrowser.ui.dialogs.base import JDialog


class DesktopMediaDialog(JDialog):
    def __init__(self, request, parent: QWidget | None = None):
        super().__init__("Share your screen", parent, (520, 420), modal=True)
        self.request = request
        self._done = False
        self.root.addWidget(QLabel("Choose what to share with the page:"))
        self.tabs = QTabWidget()
        self.screens = QListView()
        self.screens.setModel(request.screensModel())
        self.windows = QListView()
        self.windows.setModel(request.windowsModel())
        self.tabs.addTab(self.screens, "Entire screen")
        self.tabs.addTab(self.windows, "Window")
        self.root.addWidget(self.tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Share")
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        bb.accepted.connect(self._share)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)
        if request.screensModel().rowCount() > 0:
            self.screens.setCurrentIndex(request.screensModel().index(0, 0))

    def _share(self) -> None:
        view = self.screens if self.tabs.currentIndex() == 0 else self.windows
        idx = view.currentIndex()
        if not idx.isValid():
            return
        if view is self.screens:
            self.request.selectScreen(idx)
        else:
            self.request.selectWindow(idx)
        self._done = True
        self.accept()

    def done(self, result: int) -> None:
        if not self._done:
            self._done = True
            self.request.cancel()
        super().done(result)
