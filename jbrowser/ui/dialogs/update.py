"""The *Update JBrowser* dialog: release notes, download progress and install."""
from __future__ import annotations

import os

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QWidget

from jbrowser import RELEASES_PAGE, __version__
from jbrowser.ui.dialogs.base import JDialog, heading


class UpdateDialog(JDialog):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Update JBrowser", parent, (620, 520), modal=False)
        self.ctx, self.ui = ctx, ui
        self.updater = ctx.updater
        info = self.updater.latest
        self.title = heading(f"JBrowser {info.version} is available" if info else "Updates")
        self.root.addWidget(self.title)
        self.sub = QLabel(self)
        self.sub.setProperty("muted", True)
        self.sub.setWordWrap(True)
        self.root.addWidget(self.sub)
        self.notes = QTextBrowser(self)
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(info.notes if info and info.notes.strip() else "_No release notes were published._")
        self.root.addWidget(self.notes, 1)
        self.progress = QProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        self.root.addWidget(self.progress)
        self.status = QLabel(self)
        self.status.setProperty("hint", True)
        self.root.addWidget(self.status)
        row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip this version", self)
        self.later_btn = QPushButton("Later", self)
        self.go_btn = QPushButton(self)
        self.go_btn.setProperty("primary", True)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self.later_btn)
        row.addWidget(self.go_btn)
        self.root.addLayout(row)
        self.skip_btn.clicked.connect(self._skip)
        self.later_btn.clicked.connect(self._later)
        self.go_btn.clicked.connect(self._go)
        self.updater.downloadProgress.connect(self._on_progress)
        self.updater.stateChanged.connect(self._on_state)
        self.updater.readyToInstall.connect(self._on_ready)
        self._refresh()

    # ---------------------------------------------------------------- state
    def _refresh(self) -> None:
        info = self.updater.latest
        can_install = self.updater.can_install()
        if info is None:
            self.sub.setText(self.updater.message or "No update information yet.")
            self.go_btn.setText("Check now")
            self.skip_btn.hide()
            return
        size = f", {info.installer_size / 1048576:.0f} MB" if info.installer_size else ""
        if can_install:
            self.sub.setText(f"You have version {__version__}. The update downloads{size} in the background, is "
                             "checked for tampering, and then JBrowser restarts on the new version. Your cards, "
                             "spaces, passwords and settings stay exactly as they are.")
            self.go_btn.setText("Install and restart")
        else:
            self.sub.setText(f"You have version {__version__}. This copy of JBrowser was not installed with the "
                             "JBrowser installer (for example it runs from source or a portable folder), so it "
                             "cannot update itself. Download the installer from GitHub instead.")
            self.go_btn.setText("Open the download page")
        self.skip_btn.setVisible(True)

    def _on_state(self, state: str) -> None:
        self.status.setText(self.updater.message)
        busy = state == "downloading"
        self.progress.setVisible(busy or state == "ready")
        self.go_btn.setEnabled(not busy)
        self.skip_btn.setEnabled(not busy)
        self.later_btn.setText("Cancel download" if busy else "Later")
        if state in ("available", "uptodate", "error"):
            self._refresh()

    def _on_progress(self, got: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(got * 1000 / total))
            self.status.setText(f"Downloading… {got / 1048576:.0f} of {total / 1048576:.0f} MB")
        else:
            self.progress.setRange(0, 0)

    def _on_ready(self, _path: str) -> None:
        self.status.setText("Update verified. JBrowser will close and reopen in a moment…")
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        QTimer.singleShot(900, self._install_now)

    def _install_now(self) -> None:
        if self.updater.launch_installer(os.getpid()):
            self.ui.window.close()
        else:
            self.status.setText("The installer could not be started. You can run it from "
                                f"{os.path.dirname(self.updater.installer_path)}")

    # --------------------------------------------------------------- buttons
    def _go(self) -> None:
        info = self.updater.latest
        if info is None:
            self.updater.check(manual=True)
            return
        if self.updater.can_install():
            self.updater.download()
        else:
            QDesktopServices.openUrl(QUrl(info.page_url or RELEASES_PAGE))
            self.close()

    def _later(self) -> None:
        if self.updater.state == "downloading":
            self.updater.cancel_download()
            return
        self.close()

    def _skip(self) -> None:
        if self.updater.latest is not None:
            self.updater.skip(self.updater.latest.version)
            self.ui.toast(f"Version {self.updater.latest.version} skipped. You'll hear about the next one", "info")
        self.close()

    def closeEvent(self, e) -> None:
        for sig, slot in ((self.updater.downloadProgress, self._on_progress),
                          (self.updater.stateChanged, self._on_state),
                          (self.updater.readyToInstall, self._on_ready)):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        super().closeEvent(e)


def status_text(updater) -> str:
    """One-line status used by Settings → About."""
    if updater.state in ("idle", "") and not updater.message:
        return f"Version {__version__}. Updates are checked once a day."
    return updater.message or f"Version {__version__}"

