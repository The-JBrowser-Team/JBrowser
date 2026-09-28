"""Searchable, space-filterable history vault with date-range filtering and 1-click clearing."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, QDateTime, QTime, QTimer, Qt, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTreeWidget, QTreeWidgetItem, QWidget)

from jbrowser.core.urls import pretty_url
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import heading

RANGES = [("any", "Any time"), ("today", "Today"), ("7d", "Last 7 days"), ("30d", "Last 30 days"),
          ("custom", "Custom range…")]


class HistoryDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("History", parent, (980, 640))
        self.ctx = ctx
        self.ui = ui
        top = QHBoxLayout()
        top.addWidget(heading("History"))
        top.addStretch(1)
        self.count = QLabel()
        self.count.setProperty("muted", True)
        top.addWidget(self.count)
        self.root.addLayout(top)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles and addresses…")
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 2)
        self.space = QComboBox()
        self.space.addItem("All spaces", None)
        for sp in ctx.state.spaces:
            if not sp.incognito:
                self.space.addItem(f"{sp.icon}  {sp.name}", sp.id)
        filters.addWidget(self.space, 1)
        self.range = QComboBox()
        for key, label in RANGES:
            self.range.addItem(label, key)
        filters.addWidget(self.range)
        self.date_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_to = QDateEdit(QDate.currentDate())
        for d in (self.date_from, self.date_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setVisible(False)
        filters.addWidget(self.date_from)
        filters.addWidget(self.date_to)
        self.root.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Title", "Address", "Space", "Time"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setColumnWidth(0, 360)
        self.tree.setColumnWidth(1, 300)
        self.tree.setColumnWidth(2, 120)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._open(it))
        self.root.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.open_btn = QPushButton("Open in new card")
        self.open_btn.setProperty("primary", True)
        self.delete_btn = QPushButton("Delete selected")
        self.clear_range_btn = QPushButton("Clear shown results…")
        self.clear_all_btn = QPushButton("Clear all history…")
        self.clear_all_btn.setProperty("danger", True)
        for b in (self.open_btn, self.delete_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.clear_range_btn)
        buttons.addWidget(self.clear_all_btn)
        self.root.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self.reload)
        self.search.textChanged.connect(self._timer.start)
        self.space.currentIndexChanged.connect(self._timer.start)
        self.range.currentIndexChanged.connect(self._on_range)
        self.date_from.dateChanged.connect(self._timer.start)
        self.date_to.dateChanged.connect(self._timer.start)
        self.open_btn.clicked.connect(self._open_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.clear_range_btn.clicked.connect(self._clear_range)
        self.clear_all_btn.clicked.connect(self._clear_all)
        ctx.history.changed.connect(self._timer.start)
        self.reload()
        self.search.setFocus()

    def _on_range(self) -> None:
        custom = self.range.currentData() == "custom"
        self.date_from.setVisible(custom)
        self.date_to.setVisible(custom)
        self._timer.start()

    def _bounds(self) -> tuple[float | None, float | None]:
        key = self.range.currentData()
        now = dt.datetime.now()
        if key == "today":
            start = dt.datetime.combine(now.date(), dt.time.min)
            return start.timestamp(), None
        if key == "7d":
            return (now - dt.timedelta(days=7)).timestamp(), None
        if key == "30d":
            return (now - dt.timedelta(days=30)).timestamp(), None
        if key == "custom":
            start = QDateTime(self.date_from.date(), QTime(0, 0)).toSecsSinceEpoch()
            end = QDateTime(self.date_to.date().addDays(1), QTime(0, 0)).toSecsSinceEpoch()
            return float(start), float(end)
        return None, None

    def reload(self) -> None:
        start, end = self._bounds()
        entries = self.ctx.history.search(self.search.text().strip(), self.space.currentData(), start, end, 3000)
        names = {sp.id: sp.name for sp in self.ctx.state.spaces}
        self.tree.clear()
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.Medium)
        last_day = None
        items = []
        for e in entries:
            when = dt.datetime.fromtimestamp(e.ts)
            day = when.date()
            if day != last_day:
                last_day = day
                label = "Today" if day == dt.date.today() else \
                    "Yesterday" if day == dt.date.today() - dt.timedelta(days=1) else when.strftime("%A, %d %B %Y")
                head = QTreeWidgetItem([label, "", "", ""])
                head.setFirstColumnSpanned(True)
                head.setFont(0, bold)
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                items.append(head)
            it = QTreeWidgetItem([e.title or pretty_url(e.url), pretty_url(e.url), names.get(e.space_id, ""),
                                  when.strftime("%H:%M")])
            it.setData(0, Qt.ItemDataRole.UserRole, (e.id, e.url, e.space_id))
            it.setToolTip(0, e.title)
            it.setToolTip(1, e.url)
            ic = self.ctx.favicons.get(e.url)
            if not ic.isNull():
                it.setIcon(0, ic)
            items.append(it)
        self.tree.addTopLevelItems(items)
        for it in items:
            if it.flags() == Qt.ItemFlag.NoItemFlags:
                it.setFirstColumnSpanned(True)
        self.count.setText(f"{len(entries):,} visits shown · {self.ctx.history.count():,} total")

    def _selected(self) -> list[tuple[int, str, str]]:
        out = []
        for it in self.tree.selectedItems():
            data = it.data(0, Qt.ItemDataRole.UserRole)
            if data:
                out.append(data)
        return out

    def _open(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        _id, url, space_id = data
        target_space = space_id if self.ctx.state.space(space_id) else None
        self.ui.open_url(QUrl(url), "new", space_id=target_space)

    def _open_selected(self) -> None:
        for it in self.tree.selectedItems()[:20]:
            self._open(it)

    def _delete_selected(self) -> None:
        ids = [d[0] for d in self._selected()]
        if ids:
            self.ctx.history.delete_ids(ids)

    def _clear_range(self) -> None:
        start, end = self._bounds()
        space_id = self.space.currentData()
        if self.search.text().strip():
            ids = [e.id for e in self.ctx.history.search(self.search.text().strip(), space_id, start, end, 100000)]
            if ids and QMessageBox.question(self, "Clear history", f"Delete {len(ids):,} matching visits?") \
                    == QMessageBox.StandardButton.Yes:
                self.ctx.history.delete_ids(ids)
            return
        if QMessageBox.question(self, "Clear history", "Delete all visits currently shown?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.history.clear(start, end, space_id)

    def _clear_all(self) -> None:
        if QMessageBox.question(self, "Clear all history",
                                "Permanently delete your entire browsing history for every space?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.history.clear()
            self.ui.toast("History cleared", "history")
