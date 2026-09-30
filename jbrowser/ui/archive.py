"""Archive popup: cards closed in the last 48 hours, grouped by when they were closed."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

from jbrowser.core.urls import pretty_url
from jbrowser.ui.icons import draw_emoji, draw_glyph
from jbrowser.ui.theme import mix, theme

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.services.archive import ArchiveEntry
    from jbrowser.ui.controller import BrowserController

EntryRole = Qt.ItemDataRole.UserRole + 1
HeaderRole = Qt.ItemDataRole.UserRole + 2
EMPTY_TEXT = "Cards you close appear here"


def ago(ts: float, now: float | None = None) -> str:
    secs = max(0, int((now or time.time()) - ts))
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    hours = secs // 3600
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


def group_of(ts: float, now: float | None = None) -> str:
    now = now or time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    if now - ts < 3600:
        return "Last hour"
    if ts >= midnight:
        return "Earlier today"
    if ts >= midnight - 86400:
        return "Yesterday"
    return "Two days ago"


class _Delegate(QStyledItemDelegate):
    ROW_H = 48
    HEAD_H = 28

    def __init__(self, popup: "ArchivePopup"):
        super().__init__(popup.list)
        self.popup = popup

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.HEAD_H if index.data(HeaderRole) else self.ROW_H)

    def remove_rect(self, rect: QRect) -> QRect:
        return QRect(rect.right() - 34, rect.top() + (rect.height() - 26) // 2, 26, 26)

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        th = theme()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        header = index.data(HeaderRole)
        if header:
            f = p.font()
            f.setPointSizeF(7.5)
            f.setWeight(QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(th.c("text3"))
            p.drawText(QRectF(option.rect).adjusted(12, 6, 0, 0), Qt.AlignmentFlag.AlignVCenter, header.upper())
            p.restore()
            return
        entry: ArchiveEntry = self.popup.entry_for(index)
        if entry is None:
            p.restore()
            return
        r = QRectF(option.rect).adjusted(4, 2, -4, -2)
        hover = self.popup.hover_row == index.row()
        if hover:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, th.c("hover"))
        icon = self.popup.ctx.favicons.get(entry.url)
        ir = QRect(int(r.left()) + 10, int(r.center().y()) - 9, 18, 18)
        if not icon.isNull():
            p.drawPixmap(ir, icon.pixmap(QSize(18, 18), self.popup.devicePixelRatioF()))
        else:
            draw_glyph(p, QRectF(ir), "globe", th.c("text3"), 14)
        right = r.right() - 8
        if hover:
            rr = self.remove_rect(option.rect)
            if self.popup.hover_remove:
                hp = QPainterPath()
                hp.addRoundedRect(QRectF(rr), 6, 6)
                p.fillPath(hp, th.c("pressed"))
            draw_glyph(p, QRectF(rr), "close", th.c("text"), 9)
            right = rr.left() - 4
        tx = ir.right() + 12
        fm = p.fontMetrics()
        p.setPen(th.c("text"))
        title = entry.title or pretty_url(entry.url)
        p.drawText(QRectF(tx, r.top() + 5, right - tx, 20), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, int(right - tx)))
        f = p.font()
        f.setPointSizeF(8.3)
        p.setFont(f)
        fm2 = p.fontMetrics()
        sub_y = r.top() + 25
        x = tx
        if entry.space_icon:
            draw_emoji(p, QRectF(x, sub_y, 14, 16), entry.space_icon, 10)
            x += 17
        p.setPen(th.c("text3"))
        sub = f"{entry.host or pretty_url(entry.url)} · {ago(entry.closed_at)}"   # the space: its icon, and the tooltip
        p.drawText(QRectF(x, sub_y, right - x, 16), Qt.AlignmentFlag.AlignVCenter,
                   fm2.elidedText(sub, Qt.TextElideMode.ElideRight, int(right - x)))
        p.restore()


class _List(QListWidget):
    def __init__(self, popup: "ArchivePopup"):
        super().__init__(popup)
        self.popup = popup
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QListWidget{background:transparent;border:none;} QListWidget::item{background:transparent;}")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def mouseMoveEvent(self, e) -> None:
        pos = e.position().toPoint()
        idx = self.indexAt(pos)
        row = idx.row() if idx.isValid() and not idx.data(HeaderRole) else -1
        on_remove = row >= 0 and self.itemDelegate().remove_rect(self.visualRect(idx)).contains(pos)
        if row != self.popup.hover_row or on_remove != self.popup.hover_remove:
            self.popup.hover_row = row
            self.popup.hover_remove = on_remove
            self.setCursor(Qt.CursorShape.PointingHandCursor if row >= 0 else Qt.CursorShape.ArrowCursor)
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self.popup.hover_row = -1
        self.popup.hover_remove = False
        self.viewport().update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        pos = e.position().toPoint()
        idx = self.indexAt(pos)
        if not idx.isValid() or idx.data(HeaderRole):
            return
        entry_id = idx.data(EntryRole)
        if e.button() == Qt.MouseButton.LeftButton:
            if self.itemDelegate().remove_rect(self.visualRect(idx)).contains(pos):
                self.popup.ctx.archive.remove(entry_id)
            else:
                self.popup.reopen(entry_id)
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.popup.reopen(entry_id, background=True)


class ArchivePopup(QFrame):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.ctx, self.ui = ctx, ui
        self.hover_row = -1
        self.hover_remove = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(380, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        # One label, so "last 48 hours" sits on the same baseline as the larger "Archive". The muted text
        # colour is translucent; rich text needs it solid, so it is blended with the popup's background.
        th = theme()
        muted = th.c("text3")
        solid = mix(th.c("dialog_solid"), QColor(muted.red(), muted.green(), muted.blue()), muted.alphaF())
        title = QLabel(f"Archive&nbsp;&nbsp;<span style='font-size:9pt; color:{solid.name()}'>"
                       "last 48 hours</span>", self)
        title.setTextFormat(Qt.TextFormat.RichText)
        f = title.font()
        f.setPointSizeF(12)
        title.setFont(f)
        head.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.setToolTip("Remove every card from the Archive")
        self.clear_btn.clicked.connect(self._clear)
        head.addWidget(self.clear_btn)
        lay.addLayout(head)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload)
        lay.addWidget(self.search)
        self.list = _List(self)
        self.list.setItemDelegate(_Delegate(self))
        lay.addWidget(self.list, 1)
        self.empty = QLabel(EMPTY_TEXT, self)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("muted", True)
        lay.addWidget(self.empty, 1)
        self._entries: dict[str, "ArchiveEntry"] = {}
        ctx.archive.changed.connect(self.reload)
        self.reload()

    def entry_for(self, index: QModelIndex) -> "ArchiveEntry | None":
        return self._entries.get(index.data(EntryRole))

    def reload(self) -> None:
        q = self.search.text().strip().lower()
        self.list.clear()
        self._entries = {}
        now = time.time()
        last_group = None
        for e in self.ctx.archive.entries():
            if q and q not in (e.title or "").lower() and q not in e.url.lower():
                continue
            g = group_of(e.closed_at, now)
            if g != last_group:
                head = QListWidgetItem()
                head.setData(HeaderRole, g)
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list.addItem(head)
                last_group = g
            it = QListWidgetItem()
            it.setData(EntryRole, e.id)
            it.setToolTip(f"{e.title}\n{e.url}\n{e.space_name} · closed {ago(e.closed_at, now)}\n"
                          "Click to reopen · middle-click to open in the background")
            self.list.addItem(it)
            self._entries[e.id] = e
        has = bool(self._entries)
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            self.empty.setText("No matches" if q else EMPTY_TEXT)
        self.clear_btn.setEnabled(len(self.ctx.archive) > 0)

    def reopen(self, entry_id: str, background: bool = False) -> None:
        self.ui.reopen_archive_entry(entry_id, background=background)
        if not background:
            self.close()

    def _clear(self) -> None:
        self.ctx.archive.clear()

    def popup_above(self, anchor: QWidget) -> None:
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = max(avail.left() + 8, min(top_left.x() - 8, avail.right() - self.width() - 8))
        y = top_left.y() - self.height() - 6
        if y < avail.top() + 8:
            y = min(avail.bottom() - self.height() - 8, top_left.y() + anchor.height() + 6)
        self.move(x, y)
        self.show()
        self.search.setFocus()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), th.c("dialog_solid"))
        p.setPen(QPen(th.c("panel_border"), 1))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()
