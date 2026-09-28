"""Editor for injectable user scripts (JS) and user styles (CSS), per space or domain."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout,
                             QWidget)

from jbrowser.services.userscripts import UserScript
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import heading

TEMPLATES = {
    "js": "// Runs on matching pages. `document` and page globals are available.\n"
          "console.log('Hello from a JBrowser user script on', location.hostname);\n",
    "css": "/* Applied to matching pages */\nbody {\n  /* font-family: 'Segoe UI Variable Text', sans-serif; */\n}\n",
}


class UserScriptsDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("User scripts & styles", parent, (1000, 640))
        self.ctx = ctx
        self.ui = ui
        self.current: UserScript | None = None
        top = QHBoxLayout()
        top.addWidget(heading("User scripts & styles"))
        top.addStretch(1)
        self.root.addLayout(top)
        note = QLabel("Inject your own JavaScript or CSS into matching sites. Patterns: “example.com” (includes "
                      "sub-domains), “https://*.example.com/docs/*”, or “*” for every site. Changes apply on the next "
                      "page load.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        self.root.addWidget(note)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda cur, _prev: self._select(cur))
        ll.addWidget(self.list, 1)
        brow = QHBoxLayout()
        new_js = QPushButton("+ Script")
        new_js.clicked.connect(lambda: self._new("js"))
        new_css = QPushButton("+ Style")
        new_css.clicked.connect(lambda: self._new("css"))
        brow.addWidget(new_js)
        brow.addWidget(new_css)
        ll.addLayout(brow)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        form = QFormLayout()
        self.name = QLineEdit()
        self.kind = QComboBox()
        self.kind.addItem("JavaScript", "js")
        self.kind.addItem("CSS style", "css")
        self.matches = QLineEdit()
        self.matches.setPlaceholderText("example.com, *.github.com, https://news.ycombinator.com/*")
        self.run_at = QComboBox()
        self.run_at.addItem("Document start", "start")
        self.run_at.addItem("DOM ready", "ready")
        self.run_at.addItem("Page idle", "idle")
        self.spaces = QListWidget()
        self.spaces.setMaximumHeight(96)
        for sp in ctx.state.spaces:
            it = QListWidgetItem(f"{sp.icon}  {sp.name}")
            it.setData(Qt.ItemDataRole.UserRole, sp.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.spaces.addItem(it)
        self.all_frames = QCheckBox("Also run inside iframes")
        self.enabled = QCheckBox("Enabled")
        form.addRow("Name", self.name)
        form.addRow("Type", self.kind)
        form.addRow("Sites", self.matches)
        form.addRow("Run at", self.run_at)
        form.addRow("Spaces\n(none = all)", self.spaces)
        opts = QHBoxLayout()
        opts.addWidget(self.enabled)
        opts.addWidget(self.all_frames)
        opts.addStretch(1)
        form.addRow("", opts)
        rl.addLayout(form)
        self.code = QPlainTextEdit()
        mono = QFont("Cascadia Code")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSizeF(10)
        self.code.setFont(mono)
        self.code.setTabStopDistance(self.code.fontMetrics().horizontalAdvance(" ") * 2)
        rl.addWidget(self.code, 1)
        actions = QHBoxLayout()
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        save = QPushButton("Save")
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        actions.addWidget(save)
        rl.addLayout(actions)
        split.addWidget(right)
        split.setSizes([260, 700])
        self.root.addWidget(split, 1)
        self.editor = right
        self._reload_list()

    def _reload_list(self, select: str | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        target = None
        for s in self.ctx.userscripts.all():
            badge = "JS" if s.kind == "js" else "CSS"
            it = QListWidgetItem(f"[{badge}]  {s.name}" + ("" if s.enabled else "  (disabled)"))
            it.setData(Qt.ItemDataRole.UserRole, s.id)
            self.list.addItem(it)
            if s.id == select:
                target = it
        self.list.blockSignals(False)
        if target is not None:
            self.list.setCurrentItem(target)
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._select(None)

    def _select(self, item: QListWidgetItem | None) -> None:
        s = self.ctx.userscripts.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self.current = s
        self.editor.setEnabled(s is not None)
        if s is None:
            return
        self.name.setText(s.name)
        self.kind.setCurrentIndex(self.kind.findData(s.kind))
        self.matches.setText(", ".join(s.matches))
        self.run_at.setCurrentIndex(max(0, self.run_at.findData(s.run_at)))
        for i in range(self.spaces.count()):
            it = self.spaces.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in s.spaces
                             else Qt.CheckState.Unchecked)
        self.enabled.setChecked(s.enabled)
        self.all_frames.setChecked(s.all_frames)
        self.code.setPlainText(s.code)

    def _new(self, kind: str) -> None:
        tab = self.ctx.state.active_tab
        from PyQt6.QtCore import QUrl
        host = QUrl(tab.url).host() if tab else ""
        s = UserScript(name="New user style" if kind == "css" else "New user script", kind=kind,
                       code=TEMPLATES[kind], matches=[host] if host else ["*"])
        self.ctx.userscripts.upsert(s)
        self._reload_list(s.id)

    def _save(self) -> None:
        s = self.current
        if s is None:
            return
        s.name = self.name.text().strip() or "Untitled"
        s.kind = self.kind.currentData()
        s.matches = [m.strip() for m in self.matches.text().replace("\n", ",").split(",") if m.strip()] or ["*"]
        s.run_at = self.run_at.currentData()
        s.spaces = [self.spaces.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.spaces.count())
                    if self.spaces.item(i).checkState() == Qt.CheckState.Checked]
        s.enabled = self.enabled.isChecked()
        s.all_frames = self.all_frames.isChecked()
        s.code = self.code.toPlainText()
        self.ctx.userscripts.upsert(s)
        self._reload_list(s.id)
        self.ui.toast("Saved. Reload matching pages to apply", "code")

    def _delete(self) -> None:
        if self.current and QMessageBox.question(self, "Delete", f"Delete “{self.current.name}”?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.userscripts.remove(self.current.id)
            self._reload_list()
