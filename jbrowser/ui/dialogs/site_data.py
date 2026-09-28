"""Cookie manager and site permission manager."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTreeWidget, QTreeWidgetItem, QWidget)

from jbrowser.services.permissions import STATE_NAMES, describe
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import heading


def _space_combo(ctx, include_all: bool = False) -> QComboBox:
    combo = QComboBox()
    if include_all:
        combo.addItem("All spaces", None)
    for sp in ctx.state.spaces:
        combo.addItem(f"{sp.icon}  {sp.name}" + ("  (incognito)" if sp.incognito else ""), sp.id)
    active = combo.findData(ctx.state.active_space_id)
    if active >= 0 and not include_all:
        combo.setCurrentIndex(active)
    return combo


class CookiesDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Cookies", parent, (940, 600))
        self.ctx = ctx
        self.ui = ui
        top = QHBoxLayout()
        top.addWidget(heading("Cookies"))
        top.addStretch(1)
        self.space = _space_combo(ctx)
        top.addWidget(self.space)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by site…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        top.addWidget(self.search)
        self.root.addLayout(top)
        self.summary = QLabel()
        self.summary.setProperty("muted", True)
        self.root.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Site / name", "Value", "Path", "Expires", "Flags"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 240)
        self.tree.setColumnWidth(2, 80)
        self.tree.setColumnWidth(3, 150)
        self.root.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for text, fn in (("Delete selected", self._delete_selected), ("Delete session cookies", self._delete_session),
                         ("Delete all in this space…", self._delete_all)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.root.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.reload)
        self.space.currentIndexChanged.connect(self._on_space)
        self.search.textChanged.connect(self._timer.start)
        ctx.cookies.changed.connect(self._on_cookies_changed)
        self._on_space()

    def _on_cookies_changed(self, sid: str) -> None:
        if sid == self.space.currentData():
            self._timer.start()

    def _on_space(self) -> None:
        sp = self.ctx.state.space(self.space.currentData())
        if sp is not None:
            self.ctx.profiles.profile_for(sp)  # ensures the cookie store is loaded
        self.reload()

    def reload(self) -> None:
        sid = self.space.currentData()
        q = self.search.text().strip().lower()
        groups: dict[str, list] = {}
        for c in self.ctx.cookies.cookies(sid):
            dom = c.domain().lstrip(".").lower()
            if q and q not in dom:
                continue
            groups.setdefault(dom, []).append(c)
        self.tree.clear()
        total = 0
        for dom in sorted(groups):
            cookies = groups[dom]
            total += len(cookies)
            parent = QTreeWidgetItem([f"{dom}  ({len(cookies)})", "", "", "", ""])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("domain", dom))
            ic = self.ctx.favicons.get(dom)
            if not ic.isNull():
                parent.setIcon(0, ic)
            for c in cookies:
                value = bytes(c.value()).decode("utf-8", "replace")
                exp = "Session" if c.isSessionCookie() else c.expirationDate().toString("yyyy-MM-dd HH:mm")
                flags = []
                if c.isSecure():
                    flags.append("Secure")
                if c.isHttpOnly():
                    flags.append("HttpOnly")
                try:
                    flags.append(f"SameSite={c.sameSitePolicy().name}")
                except AttributeError:
                    pass
                child = QTreeWidgetItem([bytes(c.name()).decode("utf-8", "replace"),
                                         value[:80] + ("…" if len(value) > 80 else ""), c.path(), exp,
                                         " · ".join(flags)])
                child.setData(0, Qt.ItemDataRole.UserRole, ("cookie", c))
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)
        self.summary.setText(f"{total:,} cookies across {len(groups):,} sites in this space")

    def _delete_selected(self) -> None:
        sid = self.space.currentData()
        victims = []
        for it in self.tree.selectedItems():
            kind, payload = it.data(0, Qt.ItemDataRole.UserRole)
            if kind == "cookie":
                victims.append(payload)
            else:
                for i in range(it.childCount()):
                    victims.append(it.child(i).data(0, Qt.ItemDataRole.UserRole)[1])
        self.ctx.cookies.delete(sid, victims)

    def _delete_session(self) -> None:
        self.ctx.cookies.delete_session(self.space.currentData())

    def _delete_all(self) -> None:
        if QMessageBox.question(self, "Delete cookies", "Delete every cookie in this space? You will be signed out "
                                                        "of websites in this space.") == QMessageBox.StandardButton.Yes:
            self.ctx.cookies.delete_all(self.space.currentData())


class PermissionsDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Site permissions", parent, (820, 520))
        self.ctx = ctx
        self.ui = ui
        top = QHBoxLayout()
        top.addWidget(heading("Site permissions"))
        top.addStretch(1)
        self.space = _space_combo(ctx)
        top.addWidget(self.space)
        self.root.addLayout(top)
        info = QLabel("Decisions you made for camera, microphone, location, notifications, clipboard and more. "
                      "Each space keeps its own permissions.")
        info.setProperty("muted", True)
        info.setWordWrap(True)
        self.root.addWidget(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Site", "Permission", "Setting"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 220)
        self.root.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for text, fn in (("Allow", lambda: self._apply("grant")), ("Block", lambda: self._apply("deny")),
                         ("Reset (ask again)", lambda: self._apply("reset"))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.root.addLayout(row)
        self.space.currentIndexChanged.connect(self.reload)
        self._perms: list = []
        self.reload()

    def reload(self) -> None:
        sp = self.ctx.state.space(self.space.currentData())
        self.tree.clear()
        self._perms = []
        if sp is None:
            return
        prof = self.ctx.profiles.profile_for(sp)
        for i, perm in enumerate(prof.listAllPermissions()):
            name, _phrase, _glyph = describe(perm.permissionType())
            it = QTreeWidgetItem([perm.origin().toString(), name, STATE_NAMES.get(perm.state(), "?")])
            it.setData(0, Qt.ItemDataRole.UserRole, i)
            self._perms.append(perm)
            self.tree.addTopLevelItem(it)
        if not self._perms:
            it = QTreeWidgetItem(["No saved permission decisions in this space", "", ""])
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree.addTopLevelItem(it)

    def _apply(self, action: str) -> None:
        for it in self.tree.selectedItems():
            idx = it.data(0, Qt.ItemDataRole.UserRole)
            if idx is None:
                continue
            perm = self._perms[idx]
            getattr(perm, action)()
        QTimer.singleShot(100, self.reload)
