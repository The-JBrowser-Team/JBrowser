"""The stack picker: the empty place that opens below a card, offering what to stack there.

It lives in the canvas, in the slot it fills (Canvas.open_stack_picker), so the column already shows where
the new card will go: a new card (search or type an address), a card that is already open in this space,
a favourite or a bookmark. Choosing one makes the slot grow into that card. The footer sets the width of
the whole column, which its cards always share.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from jbrowser.core.urls import pretty_url
from jbrowser.models.state import MAX_STACK
from jbrowser.ui.icons import icon as make_icon
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.canvas import Canvas
    from jbrowser.ui.controller import BrowserController

SECTIONS = (("new", "New"), ("cards", "Open cards"), ("favourites", "Favourites"), ("bookmarks", "Bookmarks"))
PLACEHOLDERS = {"new": "Search or type an address", "cards": "Find an open card",
                "favourites": "Find a favourite", "bookmarks": "Find a bookmark"}
WIDTHS = (("⅓", 1 / 3), ("½", 0.5), ("⅔", 2 / 3), ("Full", 1.0))
ROLE = Qt.ItemDataRole.UserRole


class StackPicker(QFrame):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", canvas: "Canvas", anchor_id: str):
        super().__init__(canvas)
        self.ctx, self.ui, self.canvas, self.anchor = ctx, ui, canvas, anchor_id
        self.setObjectName("StackPicker")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.section = "new"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("Add a card here", self)
        f = QFont(self.title.font())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(f)
        head.addSpacing(22)                               # the stack glyph is painted here
        head.addWidget(self.title, 1)
        self.close_btn = IconButton("close", "Close (Esc)", self, size=26, glyph_px=10)
        self.close_btn.clicked.connect(lambda: self.canvas.close_stack_picker())
        head.addWidget(self.close_btn)
        lay.addLayout(head)

        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for key, label in SECTIONS:
            b = QPushButton(label, self)
            b.setCheckable(True)
            b.setProperty("segment", True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.set_section(k))
            self.group.addButton(b)
            seg.addWidget(b)
            if key == "new":
                b.setChecked(True)
        seg.addStretch(1)
        lay.addLayout(seg)

        self.input = QLineEdit(self)
        self.input.setPlaceholderText(PLACEHOLDERS["new"])
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self.refresh)
        self.input.returnPressed.connect(self._enter)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setIconSize(QSize(16, 16))
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemActivated.connect(self._choose)
        self.list.itemClicked.connect(self._choose)
        lay.addWidget(self.list, 1)
        self.empty = QLabel("", self)
        self.empty.setProperty("hint", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty, 1)

        self.footer = QWidget(self)
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(4)
        lab = QLabel("Column width", self.footer)
        lab.setProperty("hint", True)
        foot.addWidget(lab)
        foot.addStretch(1)
        for text, frac in WIDTHS:
            b = QPushButton(text, self.footer)
            b.setProperty("segment", True)
            b.setToolTip("Full width" if frac >= 1 else f"{round(frac * 100)} % of the window")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, fr=frac: self._set_width(fr))
            foot.addWidget(b)
        self.layouts_btn = IconButton("columns", "More layouts: split views, widths and focus view", self.footer,
                                      size=28, glyph_px=13)
        self.layouts_btn.clicked.connect(self._more_layouts)
        foot.addWidget(self.layouts_btn)
        lay.addWidget(self.footer)

        self.setStyleSheet(self._style())
        theme().changed.connect(self._restyle)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        self.refresh()

    # ----------------------------------------------------------------- look
    def _style(self) -> str:
        th = theme()
        t = th.tokens
        sel = f"rgba({th.accent.red()},{th.accent.green()},{th.accent.blue()},0.22)"
        return f"""
QPushButton[segment="true"] {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 4px 10px; color: {t['text2']}; }}
QPushButton[segment="true"]:hover {{ background: {t['hover']}; color: {t['text']}; }}
QPushButton[segment="true"]:checked {{ background: {sel}; color: {t['text']}; border-color: {sel}; }}
QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 7px; }}
QListWidget::item:selected {{ background: {sel}; color: {t['text']}; }}
QListWidget::item:hover {{ background: {t['hover']}; }}
"""

    def _restyle(self) -> None:
        try:
            self.setStyleSheet(self._style())
            self.refresh()
        except RuntimeError:
            pass

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.fillPath(path, th.c("layer"))             # frosted: the backdrop shows through
        p.fillPath(path, th.accent_alpha(0.05))
        p.setPen(QPen(th.accent_alpha(0.45), 1.2))
        p.drawPath(path)
        from jbrowser.ui.icons import draw_glyph
        draw_glyph(p, QRectF(12, 12, 20, 20), "stack", th.c("accent"), 15)
        p.end()

    def resizeEvent(self, e) -> None:
        # Small slots (a third of the window) keep the essentials.
        self.footer.setVisible(self.height() >= 250)
        super().resizeEvent(e)

    # ---------------------------------------------------------------- state
    def focus_input(self) -> None:
        self.input.setFocus()

    def set_section(self, key: str) -> None:
        self.section = key
        for b, (k, _l) in zip(self.group.buttons(), SECTIONS):
            b.setChecked(k == key)
        self.input.setPlaceholderText(PLACEHOLDERS[key])
        self.refresh()
        self.input.setFocus()

    def _space(self):
        tab = self.ctx.state.tab(self.anchor)
        return self.ctx.state.space_of(tab) if tab else None

    def _items(self, text: str) -> list[tuple[str, str, str, str]]:
        """(kind, value, title, subtitle) for the current section, filtered by ``text``."""
        q = text.strip().lower()

        def match(*fields: str) -> bool:
            return not q or any(q in (f or "").lower() for f in fields)

        out: list[tuple[str, str, str, str]] = []
        if self.section == "new":
            if q:
                out.append(("url", text.strip(), f"Open “{text.strip()}”", "Search or go to this address"))
            for page in self.ctx.history.pages_matching(text.strip(), limit=8):
                out.append(("url", page.url, page.title or pretty_url(page.url), pretty_url(page.url)))
        elif self.section == "cards":
            space = self._space()
            column = {t.id for t in self.ctx.state.column_of(self.anchor)}
            for t in (space.tabs if space else []):
                if t.id not in column and not t.pinned and match(t.title, t.url):
                    out.append(("card", t.id, t.display_title(), pretty_url(t.url)))
        elif self.section == "favourites":
            for fav in self.ctx.favourites.all():
                if match(fav.title, fav.url):
                    out.append(("url", fav.url, fav.title or pretty_url(fav.url), pretty_url(fav.url)))
        else:
            for bm in self.ctx.bookmarks.all():
                if match(bm.title, bm.url):
                    out.append(("url", bm.url, bm.title or pretty_url(bm.url), pretty_url(bm.url)))
        return out[:200]

    def refresh(self, *_a) -> None:
        self.list.clear()
        items = self._items(self.input.text())
        for kind, value, title, sub in items:
            it = QListWidgetItem(f"{title}   ·   {sub}" if sub and sub != title else title)
            it.setData(ROLE, (kind, value))
            it.setToolTip(value if kind == "url" else sub)
            icon = self.ctx.favicons.get(value) if kind == "url" else None
            if kind == "card":
                tab = self.ctx.state.tab(value)
                icon = tab.icon if tab is not None and not tab.icon.isNull() else None
            it.setIcon(icon if icon is not None and not icon.isNull() else make_icon("globe"))
            self.list.addItem(it)
        if items:
            self.list.setCurrentRow(0)
        empty_text = {"new": "Type to search the web or open an address.",
                      "cards": "No other cards in this space can move here.",
                      "favourites": "No favourites yet. Add one from a card's menu.",
                      "bookmarks": "No bookmarks yet. Press Ctrl+D on a page to add one."}
        self.empty.setText("Nothing matches." if self.input.text().strip() and not items else empty_text[self.section])
        self.list.setVisible(bool(items))
        self.empty.setVisible(not items)

    # -------------------------------------------------------------- choices
    def _enter(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self._choose(item)
        elif self.section == "new" and self.input.text().strip():
            self._open_url(self.input.text().strip())

    def _choose(self, item: QListWidgetItem) -> None:
        kind, value = item.data(ROLE)
        if kind == "card":
            self._stack_card(value)
        else:
            self._open_url(value)

    def _open_url(self, text: str) -> None:
        anchor, ui = self.anchor, self.ui
        self.canvas.finish_stack_picker(lambda: ui.open_url(text if "://" not in text else QUrl(text), "new",
                                                            stack_onto=anchor))

    def _stack_card(self, tab_id: str) -> None:
        st, anchor, ui = self.ctx.state, self.anchor, self.ui

        def move():
            if st.stack_tab(tab_id, anchor):
                QTimer.singleShot(0, lambda: ui.activate_card(tab_id, focus=True))
            else:
                ui.toast(f"That column is full ({MAX_STACK} cards at most)", "stack")
        self.canvas.finish_stack_picker(move)

    def _more_layouts(self) -> None:
        pos = self.layouts_btn.mapToGlobal(QPoint(0, self.layouts_btn.height()))
        ui = self.ui
        self.canvas.close_stack_picker(animated=False)
        QTimer.singleShot(0, lambda: ui.show_layout_menu(pos))

    def _set_width(self, frac: float) -> None:
        for t in self.ctx.state.column_of(self.anchor):
            t.update(width=frac)
        QTimer.singleShot(0, lambda: self.canvas.ensure_visible(self.anchor))

    # ------------------------------------------------------------- keyboard
    def eventFilter(self, obj, ev) -> bool:
        if obj is self.input and ev.type() == QEvent.Type.KeyPress:
            key = ev.key()
            if key == Qt.Key.Key_Escape:
                self.canvas.close_stack_picker()
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.list.count():
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key == Qt.Key.Key_Tab and ev.modifiers() == Qt.KeyboardModifier.ControlModifier:
                keys = [k for k, _l in SECTIONS]
                self.set_section(keys[(keys.index(self.section) + 1) % len(keys)])
                return True
        return False

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.canvas.close_stack_picker()
            return
        super().keyPressEvent(e)

    def _on_focus_changed(self, _old, new) -> None:
        # Clicking anywhere else (a page, the ribbon) closes the picker.
        try:
            if new is not None and new is not self and not self.isAncestorOf(new) and self.isVisible():
                QTimer.singleShot(0, self._close_if_still_outside)
        except RuntimeError:
            pass

    def _close_if_still_outside(self) -> None:
        try:
            focus = QApplication.focusWidget()
            if self.isVisible() and (focus is None or not (focus is self or self.isAncestorOf(focus))):
                self.canvas.close_stack_picker()
        except RuntimeError:
            pass

    def closeEvent(self, e) -> None:
        try:
            QApplication.instance().focusChanged.disconnect(self._on_focus_changed)
        except (TypeError, RuntimeError):
            pass
        super().closeEvent(e)
