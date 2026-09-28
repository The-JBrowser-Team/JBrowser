"""HTTP / proxy authentication prompt."""
from __future__ import annotations

from PyQt6.QtWidgets import QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QWidget

from jbrowser.ui.dialogs.base import JDialog


class CredentialsDialog(JDialog):
    def __init__(self, title: str, message: str, parent: QWidget | None = None):
        super().__init__(title, parent, (420, 230), modal=True)
        msg = QLabel(message)
        msg.setWordWrap(True)
        self.root.addWidget(msg)
        form = QFormLayout()
        self.user = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.user)
        form.addRow("Password", self.password)
        self.root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Sign in")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.root.addWidget(buttons)
        self.user.setFocus()


def ask_credentials(parent: QWidget | None, title: str, message: str) -> tuple[str, str] | None:
    dlg = CredentialsDialog(title, message, parent)
    if dlg.exec():
        return dlg.user.text(), dlg.password.text()
    return None
