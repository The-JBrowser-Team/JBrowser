"""Bookmarks manager with Netscape-format (HTML) import/export."""
from __future__ import annotations

import html
import re
import time

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QWidget)

from jbrowser.core.urls import pretty_url
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import JDialog, heading

_ANCHOR = re.compile(r'<A\s+[^>]*HREF="([^"]+)"[^>]*>(.*?)</A>', re.IGNORECASE | re.DOTALL)
_FOLDER = re.compile(r"<H3[^>]*>(.*?)</H3>", re.IGNORECASE | re.DOTALL)


def parse_netscape(text: str) -> list[tuple[str, str, str]]:
    """Returns (title, url, folder) triples from a browser bookmark export."""
    out = []
    folders: list[str] = []
    for line in text.splitlines():
        f = _FOLDER.search(line)
        if f:
            folders.append(html.unescape(re.sub(r"<[^>]+>", "", f.group(1))).strip())
            continue
        if re.search(r"</DL>", line, re.IGNORECASE) and folders:
            folders.pop()
        a = _ANCHOR.search(line)
        if a:
            url = html.unescape(a.group(1))
            if url.startswith(("http://", "https://", "file:", "ftp:")):
                out.append((html.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip(), url,
                            folders[-1] if folders else ""))
    return out


class BookmarkEditDialog(JDialog):
    def __init__(self, ctx, bookmark_id: str | None, parent: QWidget | None = None, url: str = "", title: str = ""):
        super().__init__("Edit bookmark" if bookmark_id else "Add bookmark", parent, (480, 260), modal=True)
        self.ctx = ctx
        self.bid = bookmark_id
        bm = ctx.bookmarks.get(bookmark_id) if bookmark_id else None
        form = QFormLayout()
        self.title = QLineEdit(bm.title if bm else title)
        self.url = QLineEdit(bm.url if bm else url)
        self.folder = QComboBox()
        self.folder.setEditable(True)
        self.folder.addItems([""] + ctx.bookmarks.folders())
        self.folder.setCurrentText(bm.folder if bm else "")
        self.on_bar = QCheckBox("Show on the bookmarks bar")
        self.on_bar.setChecked(bm.on_bar if bm else True)
        form.addRow("Title", self.title)
        form.addRow("Address", self.url)
        form.addRow("Folder", self.folder)
        form.addRow("", self.on_bar)
        self.root.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)

    def _save(self) -> None:
        url = self.url.text().strip()
        if not url:
            return
        if "://" not in url:
            url = self.ctx.resolve_input(url, remember=False).toString()
        if self.bid:
            self.ctx.bookmarks.update(self.bid, title=self.title.text().strip() or url, url=url,
                                      folder=self.folder.currentText().strip(), on_bar=self.on_bar.isChecked())
        else:
            b = self.ctx.bookmarks.add(self.title.text().strip() or url, url, self.folder.currentText().strip(),
                                       self.on_bar.isChecked())
            self.ctx.bookmarks.update(b.id, on_bar=self.on_bar.isChecked())
        self.accept()


class BookmarksDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Bookmarks", parent, (920, 600))
        self.ctx = ctx
        self.ui = ui
        top = QHBoxLayout()
        top.addWidget(heading("Bookmarks"))
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search bookmarks…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(280)
        top.addWidget(self.search)
        self.root.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Title", "Address", "Folder", "Bookmarks bar"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 300)
        self.tree.setColumnWidth(2, 120)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._open([it]))
        self.tree.itemChanged.connect(self._on_item_changed)
        self.root.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for text, fn, primary in (("Open", lambda: self._open(self.tree.selectedItems()), True),
                                  ("Add…", self._add, False), ("Edit…", self._edit, False),
                                  ("Delete", self._delete, False), ("Move up", lambda: self._move(-1), False),
                                  ("Move down", lambda: self._move(1), False)):
            b = QPushButton(text)
            b.setProperty("primary", primary)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        imp = QPushButton("Import HTML…")
        imp.clicked.connect(self._import)
        exp = QPushButton("Export HTML…")
        exp.clicked.connect(self._export)
        row.addWidget(imp)
        row.addWidget(exp)
        self.root.addLayout(row)
        self.search.textChanged.connect(self.reload)
        ctx.bookmarks.changed.connect(self.reload)
        self._loading = False
        self.reload()

    def reload(self) -> None:
        self._loading = True
        q = self.search.text().strip().lower()
        self.tree.clear()
        for b in self.ctx.bookmarks.all():
            if q and q not in b.title.lower() and q not in b.url.lower() and q not in b.folder.lower():
                continue
            it = QTreeWidgetItem([b.title, pretty_url(b.url), b.folder, ""])
            it.setData(0, Qt.ItemDataRole.UserRole, b.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(3, Qt.CheckState.Checked if b.on_bar else Qt.CheckState.Unchecked)
            it.setToolTip(1, b.url)
            ic = self.ctx.favicons.get(b.url)
            if not ic.isNull():
                it.setIcon(0, ic)
            self.tree.addTopLevelItem(it)
        self._loading = False

    def _on_item_changed(self, it: QTreeWidgetItem, col: int) -> None:
        if self._loading or col != 3:
            return
        self.ctx.bookmarks.update(it.data(0, Qt.ItemDataRole.UserRole),
                                  on_bar=it.checkState(3) == Qt.CheckState.Checked)

    def _ids(self) -> list[str]:
        return [it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()]

    def _open(self, items) -> None:
        for it in items[:20]:
            b = self.ctx.bookmarks.get(it.data(0, Qt.ItemDataRole.UserRole))
            if b:
                self.ui.open_url(QUrl(b.url), "new")

    def _add(self) -> None:
        tab = self.ctx.state.active_tab
        BookmarkEditDialog(self.ctx, None, self, tab.url if tab else "", tab.display_title() if tab else "").exec()

    def _edit(self) -> None:
        ids = self._ids()
        if ids:
            BookmarkEditDialog(self.ctx, ids[0], self).exec()

    def _delete(self) -> None:
        for bid in self._ids():
            self.ctx.bookmarks.remove(bid)

    def _move(self, delta: int) -> None:
        ids = self._ids()
        if len(ids) != 1:
            return
        items = self.ctx.bookmarks.all()
        idx = next((i for i, b in enumerate(items) if b.id == ids[0]), -1)
        if idx >= 0:
            self.ctx.bookmarks.move(ids[0], idx + delta)
            for i in range(self.tree.topLevelItemCount()):
                if self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) == ids[0]:
                    self.tree.setCurrentItem(self.tree.topLevelItem(i))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import bookmarks", "", "Bookmark files (*.html *.htm)")
        if not path:
            return
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            self.ui.toast(f"Import failed: {exc}", "error")
            return
        n = 0
        for title, url, folder in parse_netscape(text):
            if not self.ctx.bookmarks.find_url(url):
                self.ctx.bookmarks.add(title, url, folder, on_bar=False)
                n += 1
        self.ui.toast(f"Imported {n} bookmarks", "bookmarks")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export bookmarks", "jbrowser-bookmarks.html",
                                              "Bookmark files (*.html)")
        if not path:
            return
        lines = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>",
                 '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
                 "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks</H1>", "<DL><p>"]
        by_folder: dict[str, list] = {}
        for b in self.ctx.bookmarks.all():
            by_folder.setdefault(b.folder, []).append(b)
        for folder, items in by_folder.items():
            indent = "    "
            if folder:
                lines.append(f"    <DT><H3>{html.escape(folder)}</H3>")
                lines.append("    <DL><p>")
                indent = "        "
            for b in items:
                lines.append(f'{indent}<DT><A HREF="{html.escape(b.url, quote=True)}" '
                             f'ADD_DATE="{int(b.created or time.time())}">{html.escape(b.title)}</A>')
            if folder:
                lines.append("    </DL><p>")
        lines.append("</DL><p>")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        self.ui.toast("Bookmarks exported", "save")
