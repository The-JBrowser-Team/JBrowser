"""Password manager UI for the encrypted local vault."""
from __future__ import annotations

import secrets
import string
import time

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QWidget)

from jbrowser.core.urls import origin_of
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.services.vault import password_problems
from jbrowser.ui.dialogs.base import JDialog, heading
from jbrowser.ui.theme import theme

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.?"


def generate_password(length: int = 20) -> str:
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
                and any(not c.isalnum() for c in pw)):
            return pw


def ask_master_password(ctx, parent: QWidget | None) -> bool:
    vault = ctx.vault
    for attempt in range(3):
        pw, ok = QInputDialog.getText(parent, "Unlock password vault",
                                      "Master password:" if attempt == 0 else "Incorrect password. Try again:",
                                      QLineEdit.EchoMode.Password)
        if not ok:
            return False
        if vault.unlock(pw):
            return True
    return False


class CredentialDialog(JDialog):
    def __init__(self, ctx, cred=None, parent: QWidget | None = None):
        super().__init__("Edit login" if cred else "Add login", parent, (500, 330), modal=True)
        self.ctx = ctx
        self.cred = cred
        form = QFormLayout()
        self.site = QLineEdit(cred.origin if cred else "")
        self.site.setPlaceholderText("https://example.com")
        self.user = QLineEdit(cred.username if cred else "")
        pw_row = QHBoxLayout()
        self.password = QLineEdit(cred.password if cred else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda on: (self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password), show.setText("Hide" if on else "Show")))
        gen = QPushButton("Generate")
        gen.clicked.connect(lambda: (self.password.setText(generate_password()), show.setChecked(True)))
        pw_row.addWidget(self.password, 1)
        pw_row.addWidget(show)
        pw_row.addWidget(gen)
        self.scope = QComboBox()
        self.scope.addItem("All spaces", "")
        for sp in ctx.state.spaces:
            if not sp.incognito:
                self.scope.addItem(f"{sp.icon}  {sp.name} only", sp.id)
        if cred:
            i = self.scope.findData(cred.space_id)
            self.scope.setCurrentIndex(max(0, i))
        self.note = QLineEdit(cred.note if cred else "")
        form.addRow("Website", self.site)
        form.addRow("Username", self.user)
        form.addRow("Password", pw_row)
        form.addRow("Available in", self.scope)
        form.addRow("Note", self.note)
        self.root.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)

    def _save(self) -> None:
        site = self.site.text().strip()
        if not site or not self.password.text():
            return
        url = QUrl(site if "://" in site else "https://" + site)
        if not url.host():
            return
        if self.cred:
            self.ctx.vault.update(self.cred.id, origin=origin_of(url), username=self.user.text(),
                                  password=self.password.text(), space_id=self.scope.currentData() or "",
                                  note=self.note.text())
        else:
            c = self.ctx.vault.save_credential(url, self.user.text(), self.password.text(),
                                               self.scope.currentData() or "")
            if self.note.text():
                self.ctx.vault.update(c.id, note=self.note.text())
        self.accept()


EXPORT_MIN_LENGTH = 10


class ExportDialog(JDialog):
    """Choose the password for an encrypted export (a CSV inside an AES-256 ZIP)."""

    def __init__(self, count: int, parent: QWidget | None = None):
        super().__init__("Export passwords", parent, (460, 300), modal=True)
        intro = QLabel(f"Your {count} saved logins go into a ZIP file locked with a password you choose.")
        intro.setWordWrap(True)
        self.root.addWidget(intro)
        form = QFormLayout()
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw1.setPlaceholderText(f"At least {EXPORT_MIN_LENGTH} characters")
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        row = QHBoxLayout()
        row.addWidget(self.pw1, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(self._show)
        row.addWidget(show)
        form.addRow("Password", row)
        form.addRow("Confirm", self.pw2)
        self.root.addLayout(form)
        self.hint = QLabel("Tip: a few random words make a strong password you can remember.")
        self.hint.setProperty("muted", True)
        self.hint.setWordWrap(True)
        self.root.addWidget(self.hint)
        self.root.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton("Export…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("primary", True)
        self.ok.setEnabled(False)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)
        self.pw1.textChanged.connect(self._check)
        self.pw2.textChanged.connect(self._check)

    def _show(self, on: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        self.pw1.setEchoMode(mode)
        self.pw2.setEchoMode(mode)

    def _check(self) -> None:
        a, b = self.pw1.text(), self.pw2.text()
        if len(a) < EXPORT_MIN_LENGTH:
            msg = f"Use at least {EXPORT_MIN_LENGTH} characters ({len(a)} so far)." if a else \
                "Tip: a few random words make a strong password you can remember."
        elif b and a != b:
            msg = "The passwords don't match."
        elif not b:
            msg = "Type the password again to confirm it."
        else:
            msg = "Don't lose this password: without it, nobody can open the file, not even you."
        self.hint.setText(msg)
        self.ok.setEnabled(len(a) >= EXPORT_MIN_LENGTH and a == b)

    def password(self) -> str:
        return self.pw1.text()


class PasswordsDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Passwords", parent, (940, 600))
        self.ctx = ctx
        self.ui = ui
        self._revealed = False
        top = QHBoxLayout()
        top.addWidget(heading("Passwords"))
        top.addStretch(1)
        self.protection = QLabel()
        self.protection.setProperty("muted", True)
        top.addWidget(self.protection)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sites and usernames…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        top.addWidget(self.search)
        self.root.addLayout(top)

        self.locked_panel = QWidget()
        lp = QHBoxLayout(self.locked_panel)
        lp.addWidget(QLabel("🔒  The vault is locked with your master password."))
        unlock = QPushButton("Unlock…")
        unlock.setProperty("primary", True)
        unlock.clicked.connect(lambda: (ask_master_password(ctx, self), self.reload()))
        lp.addWidget(unlock)
        lp.addStretch(1)
        self.root.addWidget(self.locked_panel)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Website", "Username", "Password", "Health", "Available in", "Last used"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 230)
        self.tree.setColumnWidth(1, 180)
        self.tree.setColumnWidth(2, 130)
        self.tree.setColumnWidth(3, 120)
        self.tree.setColumnWidth(4, 130)
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit())
        self.root.addWidget(self.tree, 1)
        self.health = QLabel()
        self.health.setProperty("muted", True)
        self.health.setWordWrap(True)
        self.root.addWidget(self.health)

        row = QHBoxLayout()
        spec = [("Add…", self._add, True), ("Edit…", self._edit, False), ("Delete", self._delete, False),
                ("Copy username", lambda: self._copy("username"), False),
                ("Copy password", lambda: self._copy("password"), False),
                ("Show passwords", self._toggle_reveal, False), ("Open site", self._open_site, False)]
        self.reveal_btn = None
        for text, fn, primary in spec:
            b = QPushButton(text)
            b.setProperty("primary", primary)
            b.clicked.connect(fn)
            row.addWidget(b)
            if text == "Show passwords":
                self.reveal_btn = b
        row.addStretch(1)
        self.root.addLayout(row)
        row2 = QHBoxLayout()
        imp = QPushButton("Import…")
        imp.setToolTip("Import a Chrome, Edge or Firefox password export (CSV), or a JBrowser export (encrypted ZIP)")
        imp.clicked.connect(self._import)
        exp = QPushButton("Export…")
        exp.setToolTip("Save every login as a CSV file inside a ZIP locked with a password you choose (AES-256)")
        exp.clicked.connect(self._export)
        never = QPushButton("Never-save list…")
        never.clicked.connect(self._never)
        self.master_btn = QPushButton()
        self.master_btn.clicked.connect(self._master)
        self.remove_master_btn = QPushButton("Use Windows protection instead")
        self.remove_master_btn.clicked.connect(self._remove_master)
        lock = QPushButton("Lock now")
        lock.clicked.connect(lambda: (ctx.vault.lock(), self.reload()))
        self.lock_btn = lock
        for b in (imp, exp, never):
            row2.addWidget(b)
        row2.addStretch(1)
        for b in (self.master_btn, self.remove_master_btn, lock):
            row2.addWidget(b)
        self.root.addLayout(row2)
        self.search.textChanged.connect(self.reload)
        ctx.vault.changed.connect(self.reload)
        self.reload()

    def reload(self) -> None:
        vault = self.ctx.vault
        locked = vault.mode == "master" and vault.is_locked
        self.locked_panel.setVisible(locked)
        self.tree.setEnabled(not locked)
        master = vault.mode == "master"
        self.protection.setText("Protected by master password (AES-256-GCM)" if master
                                else "Protected by your Windows account (DPAPI + AES-256-GCM)")
        self.master_btn.setText("Change master password…" if master else "Set master password…")
        self.remove_master_btn.setVisible(master and not locked)
        self.lock_btn.setVisible(master and not locked)
        self.tree.clear()
        if locked:
            self.health.setText("")
            return
        q = self.search.text().strip().lower()
        names = {sp.id: f"{sp.icon} {sp.name}" for sp in self.ctx.state.spaces}
        entries = vault.entries()
        problems = password_problems(entries)
        warn = theme().c("warning")
        for c in sorted(entries, key=lambda c: (c.host, c.username)):
            if q and q not in c.host.lower() and q not in c.username.lower():
                continue
            last = time.strftime("%d %b %Y", time.localtime(c.last_used)) if c.last_used else "Never"
            issues = problems.get(c.id, [])
            health = " and ".join(issues).capitalize() if issues else "Good"
            it = QTreeWidgetItem([c.host, c.username or "(none)", c.password if self._revealed else "•" * 10,
                                  health, names.get(c.space_id, "All spaces") if c.space_id else "All spaces", last])
            if issues:
                it.setForeground(3, warn)
                it.setToolTip(3, ("Weak: easy to guess. " if "weak" in issues else "")
                              + ("Reused: the same password is saved for another site, so one leak exposes "
                                 "both." if "reused" in issues else ""))
            it.setData(0, Qt.ItemDataRole.UserRole, c.id)
            it.setToolTip(0, c.origin)
            ic = self.ctx.favicons.get(c.origin)
            if not ic.isNull():
                it.setIcon(0, ic)
            self.tree.addTopLevelItem(it)
        weak = sum(1 for p in problems.values() if "weak" in p)
        reused = sum(1 for p in problems.values() if "reused" in p)
        if not entries:
            self.health.setText("No saved passwords yet. JBrowser offers to save them after you sign in to a site.")
        elif not problems:
            self.health.setText(f"Password check: all {len(entries)} saved passwords look strong and unique.")
        else:
            parts = [f"{weak} weak"] if weak else []
            parts += [f"{reused} reused"] if reused else []
            self.health.setText(f"Password check: {' and '.join(parts)}. Change them on the website, then update "
                                "them here. The check runs on this computer only.")

    def _selected(self):
        out = []
        for it in self.tree.selectedItems():
            c = self.ctx.vault.get(it.data(0, Qt.ItemDataRole.UserRole))
            if c:
                out.append(c)
        return out

    def _add(self) -> None:
        if not self.ui.unlock_vault():
            return
        dlg = CredentialDialog(self.ctx, None, self)
        tab = self.ctx.state.active_tab
        if tab and tab.url.startswith("http"):
            dlg.site.setText(origin_of(QUrl(tab.url)))
        dlg.exec()

    def _edit(self) -> None:
        sel = self._selected()
        if sel:
            CredentialDialog(self.ctx, sel[0], self).exec()

    def _delete(self) -> None:
        sel = self._selected()
        if sel and QMessageBox.question(self, "Delete logins", f"Delete {len(sel)} saved login(s)?") \
                == QMessageBox.StandardButton.Yes:
            for c in sel:
                self.ctx.vault.remove(c.id)

    def _copy(self, what: str) -> None:
        sel = self._selected()
        if not sel:
            return
        if what == "username":
            QGuiApplication.clipboard().setText(sel[0].username)
            self.ui.toast("Username copied", "copy")
        else:
            self.ui.copy_secret(sel[0].password, "Password copied. The clipboard clears in 30 seconds")

    def _toggle_reveal(self) -> None:
        if not self._revealed and self.ctx.vault.mode == "master":
            pw, ok = QInputDialog.getText(self, "Confirm", "Re-enter your master password to show passwords:",
                                          QLineEdit.EchoMode.Password)
            if not ok or not self.ctx.vault.verify_password(pw):
                return
        self._revealed = not self._revealed
        self.reveal_btn.setText("Hide passwords" if self._revealed else "Show passwords")
        self.reload()
        if self._revealed:
            QTimer.singleShot(60000, self._auto_hide)

    def _auto_hide(self) -> None:
        if self._revealed:
            self._toggle_reveal()

    def _open_site(self) -> None:
        for c in self._selected()[:10]:
            self.ui.open_url(QUrl(c.origin), "new", space_id=c.space_id or None)

    def _import(self) -> None:
        if not self.ui.unlock_vault():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import passwords", "",
                                              "Password exports (*.csv *.zip);;CSV files (*.csv);;ZIP files (*.zip)")
        if not path:
            return
        try:
            if path.lower().endswith(".zip"):
                n = self._import_zip(path)
                if n is None:
                    return
                self.ui.toast(f"Imported {n} logins", "key")
            else:
                n = self.ctx.vault.import_csv(path)
                self.ui.toast(f"Imported {n} logins. Delete the CSV file now: it is not encrypted", "key")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _import_zip(self, path: str) -> int | None:
        """A JBrowser export, or any ZIP with a password CSV inside (plain or AES encrypted)."""
        from jbrowser.core.aeszip import ZipPasswordError, read_zip
        password = ""
        for attempt in range(4):
            try:
                files = read_zip(path, password)
                break
            except ZipPasswordError:
                label = "Password for this ZIP file:" if attempt == 0 else "Wrong password. Try again:"
                password, ok = QInputDialog.getText(self, "Import passwords", label, QLineEdit.EchoMode.Password)
                if not ok:
                    return None
        else:
            QMessageBox.warning(self, "Import failed", "The password is wrong.")
            return None
        csvs = [data for name, data in files.items() if name.lower().endswith(".csv")]
        if not csvs:
            raise ValueError("The ZIP file has no CSV file in it")
        return sum(self.ctx.vault.import_csv("", data) for data in csvs)

    def _export(self) -> None:
        vault = self.ctx.vault
        if not self.ui.unlock_vault():
            return
        if vault.mode == "master":
            pw, ok = QInputDialog.getText(self, "Export passwords", "Enter your master password to export:",
                                          QLineEdit.EchoMode.Password)
            if not ok:
                return
            if not vault.verify_password(pw):
                QMessageBox.warning(self, "Export passwords", "That isn't your master password.")
                return
        data, count = vault.export_csv()
        if not count:
            QMessageBox.information(self, "Export passwords", "There are no saved logins to export.")
            return
        dlg = ExportDialog(count, self)
        if not dlg.exec():
            return
        from PyQt6.QtCore import QStandardPaths
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        suggested = f"{folder}/JBrowser passwords {time.strftime('%Y-%m-%d')}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Export passwords", suggested, "ZIP files (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        from jbrowser.core.aeszip import write_encrypted_zip
        try:
            write_encrypted_zip(path, {"passwords.csv": data}, dlg.password())
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self, "Passwords exported",
            f"Saved {count} logins to:\n{path}\n\nTo open it, use 7-Zip, WinRAR or PeaZip with your password, or "
            "import it into JBrowser. (Windows' own \"Extract All\" can't open encrypted ZIP files.)")

    def _never(self) -> None:
        if not self.ui.unlock_vault():
            return
        dlg = JDialog("Never-save list", self, (420, 380), modal=True)
        lst = QListWidget()
        lst.addItems(self.ctx.vault.never_list())
        dlg.root.addWidget(QLabel("JBrowser never offers to save passwords on these sites:"))
        dlg.root.addWidget(lst, 1)
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.ctx.vault.remove_never(i.text()) or lst.takeItem(lst.row(i))
                                    for i in lst.selectedItems()])
        dlg.root.addWidget(rm)
        dlg.exec()

    def _master(self) -> None:
        vault = self.ctx.vault
        if not self.ui.unlock_vault():
            return
        pw1, ok = QInputDialog.getText(self, "Master password", "New master password (min. 8 characters):",
                                       QLineEdit.EchoMode.Password)
        if not ok:
            return
        if len(pw1) < 8:
            QMessageBox.warning(self, "Master password", "Please use at least 8 characters.")
            return
        pw2, ok = QInputDialog.getText(self, "Master password", "Confirm master password:",
                                       QLineEdit.EchoMode.Password)
        if not ok or pw1 != pw2:
            QMessageBox.warning(self, "Master password", "The passwords did not match.")
            return
        if vault.set_master_password(pw1):
            self.ui.toast("Your passwords are now protected by your master password", "lock")
        self.reload()

    def _remove_master(self) -> None:
        if QMessageBox.question(self, "Remove master password",
                                "Protect the vault with your Windows account instead of a master password?") \
                == QMessageBox.StandardButton.Yes and self.ctx.vault.remove_master_password():
            self.ui.toast("Your passwords are protected by your Windows account", "key")
        self.reload()
