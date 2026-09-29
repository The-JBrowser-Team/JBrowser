"""Vertical sidebar: favourites, spaces, the active space's cards and tools.

The sidebar can be hidden completely (Ctrl+B, its hide button, or right-click → Hide
sidebar). While hidden, pointing at the left edge of the window slides it in over the
canvas (a "peek"); it tucks itself away again when the pointer leaves.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import (QAbstractListModel, QDate, QEasingCurve, QModelIndex, QPoint, QRect, QRectF, QSize, Qt,
                          QTime, QTimer, pyqtProperty, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QHBoxLayout, QLabel, QListView,
                             QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget)

from jbrowser.core.motion import motion
from jbrowser.models.space import Space
from jbrowser.models.tab import Tab
from jbrowser.ui.icons import draw_emoji, draw_glyph, paint_logo
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.services.favourites import Favourite
    from jbrowser.ui.controller import BrowserController

EXPANDED_W = 256
PEEK_EDGE = 10          # px from the window's left edge that summon the hidden sidebar
TabRole = Qt.ItemDataRole.UserRole + 1
FooterRole = Qt.ItemDataRole.UserRole + 2


class SpaceRow(QWidget):
    clicked = pyqtSignal(str)
    menuRequested = pyqtSignal(str, QPoint)

    def __init__(self, space: Space, sidebar: "Sidebar"):
        super().__init__(sidebar)
        self.space = space
        self.sidebar = sidebar
        self._hover = False
        self.drop = False            # a dragged card would move to this space
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.space.id)
        elif e.button() == Qt.MouseButton.RightButton:
            self.menuRequested.emit(self.space.id, e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e) -> None:
        self.sidebar.ui.edit_space(self.space.id)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self.space.id == self.sidebar.ctx.state.active_space_id
        r = QRectF(self.rect()).adjusted(6, 2, -6, -2)
        if self.drop:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, th.accent_alpha(0.20))
            p.setPen(QPen(th.c("accent"), 1.5, Qt.PenStyle.DashLine))
            p.drawPath(path)
        elif active or self._hover:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, th.c("selected") if active else th.c("hover"))
        color = QColor(self.space.color)
        if active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(r.left() - 3, r.center().y() - 8, 3, 16), 1.5, 1.5)
        circle = QRectF(r.left() + 6, r.center().y() - 14, 28, 28)
        bg = QColor(color)
        bg.setAlphaF(0.24 if active else 0.16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(circle)
        draw_emoji(p, circle, self.space.icon, 15)
        if self.space.incognito:
            badge = QRectF(circle.right() - 11, circle.bottom() - 11, 13, 13)
            p.setBrush(th.c("panel"))
            p.drawEllipse(badge)
            draw_glyph(p, badge, "incognito", th.c("text"), 8)
        f = p.font()
        f.setWeight(QFont.Weight.Medium if active else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(th.c("text") if active else th.c("text2"))
        count = len(self.space.tabs)
        text_r = QRectF(circle.right() + 10, r.top(), r.width() - circle.width() - 56, r.height())
        fm = p.fontMetrics()
        p.drawText(text_r, Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.space.name, Qt.TextElideMode.ElideRight, int(text_r.width())))
        if count:
            f.setWeight(QFont.Weight.Normal)
            f.setPointSizeF(8.5)
            p.setFont(f)
            p.setPen(th.c("text3"))
            p.drawText(QRectF(r.right() - 36, r.top(), 28, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(count))
        p.end()


# ------------------------------------------------------------------ favourites
class FavouriteTile(QAbstractButton):
    TILE_H = 42

    def __init__(self, fav: "Favourite", grid: "FavouritesGrid"):
        super().__init__(grid)
        self.fav = fav
        self.grid = grid
        self._hover = False
        self._press: QPoint | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{fav.label()}\n{fav.url}\nClick to open · Right-click for options · Drag to reorder")

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.grid.sidebar.ui.open_url(self.fav.url, "background")
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._press is not None and (e.position().toPoint() - self._press).manhattanLength() > 10:
            self.grid.drag_to(self, self.mapTo(self.grid, e.position().toPoint()))
            self.setDown(False)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        dragged = self.grid.dragging is self
        self._press = None
        if dragged:
            self.grid.end_drag()
            self.setDown(False)
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        self.grid.sidebar.ui.show_favourite_menu(self.fav.id, e.globalPos())

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        ui = self.grid.sidebar.ui
        state = ui.favourite_state(self.fav.id)        # "", "open" or "active"
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        base = th.c("pressed") if self.isDown() else (th.c("hover") if self._hover else th.c("input"))
        p.fillPath(path, base)
        if state == "active":
            p.fillPath(path, th.accent_alpha(0.16))
            p.setPen(QPen(th.accent_alpha(0.55), 1.2))
            p.drawPath(path)
        ic = self.grid.sidebar.ctx.favicons.get(self.fav.url)
        icon_r = QRect(int(r.center().x()) - 10, int(r.center().y()) - 10, 20, 20)
        if not ic.isNull():
            p.drawPixmap(icon_r, ic.pixmap(QSize(20, 20), self.devicePixelRatioF()))
        else:
            letter = (self.fav.host or self.fav.label() or "?")[:1].upper()
            f = QFont(self.font())
            f.setPixelSize(15)
            f.setWeight(QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(th.c("text2"))
            p.drawText(QRectF(icon_r), Qt.AlignmentFlag.AlignCenter, letter)
        if state:
            dot = QRectF(r.center().x() - 2.5, r.bottom() - 6, 5, 5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(th.c("accent") if state == "active" else th.c("text3"))
            p.drawEllipse(dot)
        p.end()


class FavouritesGrid(QWidget):
    COLS = 4
    GAP = 6

    def __init__(self, sidebar: "Sidebar"):
        super().__init__(sidebar)
        self.sidebar = sidebar
        self.tiles: list[FavouriteTile] = []
        self.dragging: FavouriteTile | None = None
        sidebar.ctx.favourites.changed.connect(self.rebuild)
        sidebar.ctx.favicons.updated.connect(lambda *_: [t.update() for t in self.tiles])
        self.rebuild()

    def rebuild(self) -> None:
        for t in self.tiles:
            t.deleteLater()
        self.tiles = [FavouriteTile(f, self) for f in self.sidebar.ctx.favourites.all()]
        for t in self.tiles:
            t.clicked.connect(lambda _c=False, fid=t.fav.id: self.sidebar.ui.open_favourite(fid))
            t.show()
        self.setVisible(bool(self.tiles))
        self._relayout()
        self.updateGeometry()

    def _cell(self) -> tuple[float, int]:
        w = self.width() - 24
        return (w - self.GAP * (self.COLS - 1)) / self.COLS, FavouriteTile.TILE_H

    def _relayout(self) -> None:
        cw, ch = self._cell()
        for i, t in enumerate(self.tiles):
            if t is self.dragging:
                continue
            row, col = divmod(i, self.COLS)
            t.setGeometry(int(12 + col * (cw + self.GAP)), int(4 + row * (ch + self.GAP)), int(cw), ch)
        rows = (len(self.tiles) + self.COLS - 1) // self.COLS
        self.setFixedHeight(rows * ch + max(0, rows - 1) * self.GAP + 10 if rows else 0)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._relayout()

    def refresh(self) -> None:
        for t in self.tiles:
            t.update()

    def drag_to(self, tile: FavouriteTile, pos: QPoint) -> None:
        self.dragging = tile
        tile.raise_()
        cw, ch = self._cell()
        tile.move(int(pos.x() - cw / 2), int(pos.y() - ch / 2))
        col = int(max(0, min(self.COLS - 1, (pos.x() - 12) // (cw + self.GAP))))
        row = int(max(0, pos.y() // (ch + self.GAP)))
        target = min(len(self.tiles) - 1, row * self.COLS + col)
        cur = self.tiles.index(tile)
        if target != cur:
            self.tiles.insert(target, self.tiles.pop(cur))
            self._relayout()

    def end_drag(self) -> None:
        tile = self.dragging
        self.dragging = None
        if tile is not None:
            self.sidebar.ctx.favourites.move(tile.fav.id, self.tiles.index(tile))   # rebuilds


# --------------------------------------------------------------------- cards
class TabListModel(QAbstractListModel):
    """The active space's cards, pinned first, followed by a "New card" row."""

    def __init__(self, ctx: "AppContext", parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.space: Space | None = None

    def set_space(self, space: Space | None) -> None:
        self.beginResetModel()
        self.space = space
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid() or self.space is None:
            return 0
        if not self.space.tabs and not self.ctx.settings.get("sidebar.new_card_always"):
            return 0
        return len(self.space.tabs) + 1           # + the "New card" row

    def is_footer(self, row: int) -> bool:
        return self.space is not None and row == len(self.space.tabs)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.space is None:
            return None
        if self.is_footer(index.row()):
            if role == FooterRole:
                return True
            if role == Qt.ItemDataRole.ToolTipRole:
                return "Open a new card at the end of this space (Ctrl+T opens one next to the current card)"
            return None
        if index.row() >= len(self.space.tabs):
            return None
        tab = self.space.tabs[index.row()]
        if role == TabRole:
            return tab
        if role == Qt.ItemDataRole.DisplayRole:
            return tab.display_title()
        if role == Qt.ItemDataRole.ToolTipRole:
            state = " (sleeping)" if tab.sleeping else ""
            pin = "Pinned · " if tab.pinned else ""
            return f"{pin}{tab.display_title()}{state}\n{tab.url}"
        return None

    def refresh_tab(self, tab_id: str) -> None:
        if self.space is None:
            return
        row = self.space.index_of(tab_id)
        if row >= 0:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)


class TabDelegate(QStyledItemDelegate):
    ROW_H = 34
    DIVIDER = 9     # extra space under the last pinned card

    def __init__(self, view: "TabListView"):
        super().__init__(view)
        self.view = view

    def _last_pinned(self, index: QModelIndex) -> bool:
        space = self.view.model().space
        row = index.row()
        if space is None or row >= len(space.tabs) or not space.tabs[row].pinned:
            return False
        return row + 1 < len(space.tabs) and not space.tabs[row + 1].pinned

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_H + (self.DIVIDER if self._last_pinned(index) else 0))

    def close_rect(self, row_rect: QRect) -> QRect:
        return QRect(row_rect.right() - 30, row_rect.top() + 5, 24, 24)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        th = theme()
        if index.data(FooterRole):
            self._paint_footer(p, option, index)
            return
        tab: Tab = index.data(TabRole)
        if tab is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        row_rect = QRect(option.rect)
        divider = self._last_pinned(index)
        if divider:
            row_rect.setHeight(self.ROW_H)
        r = QRectF(row_rect).adjusted(6, 1, -6, -1)
        space = self.view.model().space
        active = space is not None and tab.id == space.active_tab_id
        selected = space is not None and tab.id in space.selected and len(space.selected) > 1
        hover = self.view.hover_row == index.row()
        if active or selected or hover:
            path = QPainterPath()
            path.addRoundedRect(r, 7, 7)
            if active:
                p.fillPath(path, th.c("selected"))
            elif selected:
                p.fillPath(path, th.accent_alpha(0.16))
            else:
                p.fillPath(path, th.c("hover"))
        icon_r = QRect(int(r.left()) + 10, int(r.center().y()) - 8, 16, 16)
        if tab.loading and not tab.sleeping:
            draw_glyph(p, QRectF(icon_r), "sync", th.c("accent"), 12)
        elif not tab.icon.isNull():
            p.setOpacity(0.4 if tab.sleeping else 1.0)
            p.drawPixmap(icon_r, tab.icon.pixmap(QSize(16, 16), self.view.devicePixelRatioF()))
            p.setOpacity(1.0)
        else:
            draw_glyph(p, QRectF(icon_r), "globe", th.c("text3"), 13)
        if tab.sleeping:
            br = QRectF(icon_r.right() - 5, icon_r.bottom() - 5, 10, 10)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(th.c("panel"))
            p.drawEllipse(br.adjusted(-1, -1, 1, 1))
            draw_glyph(p, br, "moon", th.c("sleep"), 7)
        right = r.right() - 8
        if tab.pinned:
            pr = QRectF(r.right() - 26, r.center().y() - 9, 18, 18)
            draw_glyph(p, pr, "pin", th.c("text2") if hover else th.c("text3"), 10)
            right = pr.left() - 2
        elif hover:
            cr = self.close_rect(row_rect)
            if self.view.hover_close:
                path = QPainterPath()
                path.addRoundedRect(QRectF(cr), 5, 5)
                p.fillPath(path, th.c("pressed"))
            draw_glyph(p, QRectF(cr), "close", th.c("text"), 9)
            right = cr.left() - 2
        if tab.audible or tab.muted:
            ar = QRectF(right - 18, r.center().y() - 9, 18, 18)
            draw_glyph(p, ar, "mute" if tab.muted else "volume", th.c("text2"), 11)
            right = ar.left() - 2
        f = p.font()
        f.setWeight(QFont.Weight.Medium if active else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(th.c("text3") if tab.sleeping else (th.c("text") if active else th.c("text2")))
        text_r = QRectF(icon_r.right() + 10, r.top(), right - icon_r.right() - 12, r.height())
        p.drawText(text_r, Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(tab.display_title(), Qt.TextElideMode.ElideRight, int(text_r.width())))
        if divider:
            y = option.rect.top() + self.ROW_H + self.DIVIDER / 2
            p.setPen(QPen(th.c("divider"), 1))
            p.drawLine(int(r.left() + 8), int(y), int(r.right() - 8), int(y))
        p.restore()

    def _paint_footer(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        th = theme()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 1, -6, -1)
        hover = self.view.hover_row == index.row()
        if hover:
            path = QPainterPath()
            path.addRoundedRect(r, 7, 7)
            p.fillPath(path, th.c("hover"))
        icon_r = QRectF(r.left() + 10, r.center().y() - 8, 16, 16)
        draw_glyph(p, icon_r, "add", th.c("text") if hover else th.c("text3"), 12)
        p.setPen(th.c("text2") if hover else th.c("text3"))
        p.drawText(QRectF(icon_r.right() + 10, r.top(), r.width() - 40, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   "New card")
        p.restore()


class TabListView(QListView):
    """The current space's cards. Drag a card to reorder it, or onto a space above to move it there."""

    DRAG_START = 6

    def __init__(self, sidebar: "Sidebar"):
        super().__init__(sidebar)
        self.sidebar = sidebar
        self.hover_row = -1
        self.hover_close = False
        self._press: tuple[str, QPoint] | None = None    # (tab id, press position)
        self._dragging = False
        self._drop_row = -1                               # insert before this row (-1: none)
        self._drop_space: str | None = None
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setStyleSheet("QListView{background:transparent;border:none;} QListView::item{background:transparent;}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setItemDelegate(TabDelegate(self))

    def _row_rect(self, idx: QModelIndex) -> QRect:
        rect = self.visualRect(idx)
        rect.setHeight(TabDelegate.ROW_H)
        return rect

    def _tab_at(self, pos: QPoint) -> tuple[Tab | None, QModelIndex]:
        idx = self.indexAt(pos)
        return (idx.data(TabRole) if idx.isValid() else None), idx

    def mouseMoveEvent(self, e) -> None:
        pos = e.position().toPoint()
        if self._press is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if not self._dragging and (pos - self._press[1]).manhattanLength() > self.DRAG_START:
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging:
                self._drag_to(pos, e.globalPosition().toPoint())
                return
        idx = self.indexAt(pos)
        row = idx.row() if idx.isValid() and self._row_rect(idx).contains(pos) else -1
        tab = idx.data(TabRole) if row >= 0 else None
        on_close = bool(tab and not tab.pinned and self.itemDelegate().close_rect(self._row_rect(idx)).contains(pos))
        if row != self.hover_row or on_close != self.hover_close:
            self.hover_row = row
            self.hover_close = on_close
            self.setCursor(Qt.CursorShape.PointingHandCursor if row >= 0 else Qt.CursorShape.ArrowCursor)
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self.hover_row = -1
        self.hover_close = False
        self.viewport().update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        pos = e.position().toPoint()
        tab, idx = self._tab_at(pos)
        ui = self.sidebar.ui
        if idx.isValid() and idx.data(FooterRole):
            if e.button() == Qt.MouseButton.LeftButton:
                space = self.model().space
                ui.open_lazy_toolbar("new", insert_at=len(space.tabs) if space else None)
            return
        if tab is None:
            if e.button() == Qt.MouseButton.RightButton:
                ui.show_sidebar_menu(e.globalPosition().toPoint())
            return
        if e.button() == Qt.MouseButton.MiddleButton:
            ui.close_tab(tab.id)
        elif e.button() == Qt.MouseButton.LeftButton:
            if not tab.pinned and self.itemDelegate().close_rect(self._row_rect(idx)).contains(pos):
                ui.close_tab(tab.id)
            else:
                self._press = (tab.id, pos)
                ui.activate_card(tab.id, e.modifiers(), wake=True, center=True)
        elif e.button() == Qt.MouseButton.RightButton:
            ui.show_card_menu(tab.id, e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e) -> None:
        press, self._press = self._press, None
        if self._dragging and press is not None:
            self._finish_drag(press[0])
        super().mouseReleaseEvent(e)

    # ------------------------------------------------------------------ dragging
    def _drag_to(self, pos: QPoint, global_pos: QPoint) -> None:
        model = self.model()
        space = model.space if model else None
        if space is None or self._press is None:
            return
        self._drop_space = self.sidebar.drop_target_at(global_pos, exclude=space.id)
        row = -1
        if self._drop_space is None and self.viewport().rect().adjusted(0, -30, 0, 30).contains(pos):
            row = len(space.tabs)
            for r in range(len(space.tabs)):
                rect = self._row_rect(model.index(r))
                if pos.y() < rect.center().y():
                    row = r
                    break
        if row != self._drop_row:
            self._drop_row = row
            self.viewport().update()
        bar = self.verticalScrollBar()
        if pos.y() < 20:
            bar.setValue(bar.value() - 8)
        elif pos.y() > self.viewport().height() - 20:
            bar.setValue(bar.value() + 8)

    def _finish_drag(self, tab_id: str) -> None:
        space = self.model().space
        target, row = self._drop_space, self._drop_row
        self._dragging = False
        self._drop_row = -1
        self._drop_space = None
        self.unsetCursor()
        self.sidebar.clear_drop_target()
        self.viewport().update()
        if space is None:
            return
        if target:
            self.sidebar.ui.move_tab_to_space(tab_id, target)
        elif row >= 0:
            old = space.index_of(tab_id)
            new = row - 1 if row > old else row
            self.sidebar.ctx.state.move_tab(tab_id, new)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self._dragging and self._drop_row >= 0:
            model = self.model()
            space = model.space
            if space is None:
                return
            if self._drop_row < len(space.tabs):
                y = self._row_rect(model.index(self._drop_row)).top()
            else:
                y = self._row_rect(model.index(len(space.tabs) - 1)).bottom() + 1 if space.tabs else 0
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            th = theme()
            p.setPen(QPen(th.c("accent"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(14, y, self.viewport().width() - 14, y)
            p.setBrush(th.c("accent"))
            p.drawEllipse(QRectF(9, y - 3.5, 7, 7))
            p.end()

    def keyPressEvent(self, e) -> None:
        model = self.model()
        space = model.space if model else None
        if space and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and space.tabs:
            cur = space.index_of(space.active_tab_id)
            nxt = max(0, min(len(space.tabs) - 1, cur + (1 if e.key() == Qt.Key.Key_Down else -1)))
            self.sidebar.ui.activate_card(space.tabs[nxt].id, Qt.KeyboardModifier.NoModifier, focus=False)
            return
        if space and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.sidebar.ui.focus_active_card()
            return
        if space and e.key() == Qt.Key.Key_Delete and space.active_tab_id:
            self.sidebar.ui.close_tab(space.active_tab_id)
            return
        super().keyPressEvent(e)


class SpaceSection(QWidget):
    """Focusable container for the space rows: Up / Down switches spaces."""

    def __init__(self, sidebar: "Sidebar"):
        super().__init__(sidebar)
        self.sidebar = sidebar
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(1)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Up:
            self.sidebar.ui.switch_space(-1)
            return
        if e.key() == Qt.Key.Key_Down:
            self.sidebar.ui.switch_space(1)
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.sidebar.ui.focus_active_card()
            return
        super().keyPressEvent(e)

    def paintEvent(self, _e) -> None:
        if self.hasFocus():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(theme().c("focus_ring"), 1.0))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4.5, 0.5, -4.5, -0.5), 9, 9)
            p.end()

    def focusInEvent(self, e) -> None:
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:
        self.update()
        super().focusOutEvent(e)


class LogoButton(QAbstractButton):
    """The JBrowser mark doubles as the Settings button."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setToolTip("Settings (Ctrl+,)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover or self.isDown():
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
            p.fillPath(path, theme().c("pressed" if self.isDown() else "hover"))
        paint_logo(p, QRectF(5, 5, 22, 22))
        p.end()


class ClockLabel(QLabel):
    """12-hour clock in the middle of the sidebar header; re-aligns itself to every minute boundary."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = self.font()
        f.setPointSizeF(10.5)
        f.setWeight(QFont.Weight.Normal)
        self.setFont(f)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._tick()

    def _tick(self) -> None:
        now = QTime.currentTime()
        self.setText(now.toString("h:mm AP"))
        self.setToolTip(QDate.currentDate().toString("dddd, d MMMM yyyy"))
        self._timer.start(max(1000, (60 - now.second()) * 1000 - now.msec() + 50))


class SidebarHeader(QWidget):
    """Logo (Settings) on the left, hide button on the right, and the clock centred between them."""

    def __init__(self, sidebar: "Sidebar"):
        super().__init__(sidebar)
        self.sidebar = sidebar
        self.setFixedHeight(46)
        self.setProperty("dragRegion", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 0)
        lay.setSpacing(8)
        self.logo = LogoButton(self)
        self.logo.clicked.connect(lambda: sidebar.ui.open_settings())
        self.toggle = IconButton("closepane", "Hide sidebar (Ctrl+B)", self, size=30, glyph_px=14)
        lay.addWidget(self.logo)
        lay.addStretch(1)
        lay.addWidget(self.toggle)
        # Positioned by hand so it sits in the true centre of the sidebar, not between two
        # buttons of different widths.
        self.clock = ClockLabel(self)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        top = self.layout().contentsMargins().top()
        self.clock.setGeometry(44, top, max(0, self.width() - 88), self.height() - top)


class Sidebar(QWidget):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.ui = ui
        self.hidden_mode = bool(ctx.settings.get("appearance.sidebar_collapsed"))
        self.floating = False                 # peeking over the canvas while hidden
        self.collapsed_visual = False         # kept for callers from the old rail mode
        self._width = 0.0 if self.hidden_mode else float(EXPANDED_W)
        self._slide = 0.0                     # peek slide-in progress (0 hidden … 1 shown)
        self._anim = None
        self._rows: dict[str, SpaceRow] = {}
        self.setFixedWidth(int(self._width))
        if self.hidden_mode:
            self.hide()
        self._peek_hide = QTimer(self)
        self._peek_hide.setSingleShot(True)
        self._peek_hide.setInterval(380)
        self._peek_hide.timeout.connect(self._maybe_end_peek)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(4)
        self.header = SidebarHeader(self)
        self.header.toggle.clicked.connect(ui.toggle_sidebar)
        root.addWidget(self.header)

        self.favourites = FavouritesGrid(self)
        root.addWidget(self.favourites)

        lab = QLabel("SPACES", self)
        lab.setProperty("muted", True)
        f = lab.font()
        f.setPointSizeF(7.5)
        f.setWeight(QFont.Weight.Medium)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        lab.setFont(f)
        lab.setContentsMargins(18, 6, 0, 2)
        self.spaces_label = lab
        root.addWidget(lab)

        self.section = SpaceSection(self)
        root.addWidget(self.section)

        new_row = QHBoxLayout()
        new_row.setContentsMargins(10, 2, 10, 2)
        new_row.setSpacing(4)
        self.new_space = IconButton("add", "New space (Ctrl+N)", self, size=30, glyph_px=13)
        self.new_incog = IconButton("incognito", "New incognito space (Ctrl+Shift+N)", self, size=30, glyph_px=14)
        self.new_space.clicked.connect(lambda: ui.new_space(False))
        self.new_incog.clicked.connect(lambda: ui.new_space(True))
        self.new_label = QLabel("New space", self)
        self.new_label.setProperty("muted", True)
        new_row.addWidget(self.new_space)
        new_row.addWidget(self.new_label)
        new_row.addStretch(1)
        new_row.addWidget(self.new_incog)
        root.addLayout(new_row)
        self.divider = QWidget(self)
        self.divider.setFixedHeight(9)
        self.divider.paintEvent = self._paint_divider
        root.addWidget(self.divider)

        self.model = TabListModel(ctx, self)
        self.list = TabListView(self)
        self.list.setModel(self.model)
        root.addWidget(self.list, 1)

        self.tools = QWidget(self)
        self.tools_lay = QHBoxLayout(self.tools)
        self.tools_lay.setContentsMargins(10, 0, 10, 0)
        self.tools_lay.setSpacing(2)
        self.tool_buttons = []
        for glyph_name, tip, cmd in (("download", "Downloads (Ctrl+J)", "downloads.show"),
                                     ("history", "History (Ctrl+H)", "history.show"),
                                     ("bookmarks", "Bookmarks (Ctrl+Shift+O)", "bookmarks.show"),
                                     ("key", "Passwords", "passwords.show")):
            b = IconButton(glyph_name, tip, self.tools, size=34, glyph_px=15)
            b.clicked.connect(lambda _c=False, c=cmd: ctx.commands.run(c))
            self.tools_lay.addWidget(b)
            self.tool_buttons.append(b)
        self.tools_lay.addStretch(1)
        self.archive_btn = IconButton("archive", "Archive: cards closed in the last 48 hours (Ctrl+Shift+Y)",
                                      self.tools, size=34, glyph_px=15)
        self.archive_btn.clicked.connect(lambda: ui.show_archive(self.archive_btn))
        self.tools_lay.addWidget(self.archive_btn)
        root.addWidget(self.tools)

        st = ctx.state
        st.spaceAdded.connect(lambda *_: self.rebuild())
        st.spaceRemoved.connect(lambda *_: self.rebuild())
        st.spacesReordered.connect(self.rebuild)
        st.spaceUpdated.connect(lambda *_: self._repaint_rows())
        st.activeSpaceChanged.connect(self._on_active_space)
        st.tabAdded.connect(self._on_tabs_changed)
        st.tabRemoved.connect(self._on_tabs_changed)
        st.tabMoved.connect(self._on_tabs_changed)
        st.activeTabChanged.connect(lambda *_: (self.list.viewport().update(), self.favourites.refresh()))
        st.selectionChanged.connect(lambda *_: self.list.viewport().update())
        ctx.pipeline.flushed.connect(self._on_flush)
        ctx.downloads.activeCountChanged.connect(self._on_downloads)
        ctx.downloads.updated.connect(lambda *_: self._on_downloads())
        ctx.archive.changed.connect(self._on_archive)
        ctx.settings.changed.connect(lambda k, _v: self._on_tabs_changed() if k == "sidebar.new_card_always" else None)
        self.rebuild()
        self._on_archive()

    # --------------------------------------------------------------- spaces
    def rebuild(self) -> None:
        for row in self._rows.values():
            row.deleteLater()
        self._rows.clear()
        while self.section.lay.count():
            self.section.lay.takeAt(0)
        for sp in self.ctx.state.spaces:
            row = SpaceRow(sp, self)
            row.clicked.connect(self.ui.select_space)
            row.menuRequested.connect(self.ui.show_space_menu)
            self._rows[sp.id] = row
            self.section.lay.addWidget(row)
        self.model.set_space(self.ctx.state.active_space)
        self.favourites.refresh()
        self.update()

    def _repaint_rows(self) -> None:
        for row in self._rows.values():
            row.update()
        self.update()

    def _on_active_space(self, space: Space, _prev) -> None:
        self.model.set_space(space)
        self.favourites.refresh()
        self._repaint_rows()

    def _on_tabs_changed(self, *args) -> None:
        self.model.set_space(self.ctx.state.active_space)
        self.favourites.refresh()
        self._repaint_rows()

    def _on_flush(self, summary: dict) -> None:
        space = self.model.space
        if space is None or not self.isVisible():
            return
        interesting = {"title", "icon", "sleeping", "audible", "muted", "loading", "url", "pinned"}
        for tid, fields in summary.items():
            if fields & interesting:
                self.model.refresh_tab(tid)
        if any("url" in f for f in summary.values()):
            self.favourites.refresh()

    def _on_downloads(self) -> None:
        active = self.ctx.downloads.active_items()
        self.tool_buttons[0].set_progress(self.ctx.downloads.overall_progress() if active else None)

    def _on_archive(self) -> None:
        n = len(self.ctx.archive)
        self.archive_btn.setToolTip(f"Archive: {n} card{'s' if n != 1 else ''} closed in the last 48 hours"
                                    if n else "Archive: cards you close are kept here for 48 hours")

    def _paint_divider(self, _e) -> None:
        p = QPainter(self.divider)
        p.setPen(QPen(theme().c("divider"), 1))
        y = self.divider.height() // 2
        p.drawLine(18, y, self.divider.width() - 18, y)
        p.end()

    # --------------------------------------------------- drag and drop target
    def drop_target_at(self, global_pos: QPoint, exclude: str = "") -> str | None:
        """The space whose row is under ``global_pos`` (a card being dragged there would move to
        it), highlighting that row. None, and no highlight, anywhere else."""
        found = None
        for sid, row in self._rows.items():
            over = (sid != exclude and row.isVisible() and self.isVisible()
                    and row.rect().contains(row.mapFromGlobal(global_pos)))
            if over:
                found = sid
            if row.drop != over:
                row.drop = over
                row.update()
        return found

    def clear_drop_target(self) -> None:
        for row in self._rows.values():
            if row.drop:
                row.drop = False
                row.update()

    def focus_spaces(self) -> None:
        if self.hidden_mode and not self.floating:
            self.peek()
        self.section.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def contextMenuEvent(self, e) -> None:
        self.ui.show_sidebar_menu(e.globalPos())

    # ------------------------------------------------------ hide and show
    def _get_w(self) -> float:
        return self._width

    def _set_w(self, v: float) -> None:
        self._width = float(v)
        self.setFixedWidth(max(0, int(round(v))))

    sidebarWidth = pyqtProperty(float, _get_w, _set_w)

    def _stop_anim(self) -> None:
        if self._anim is not None:
            try:
                self._anim.stop()
            except RuntimeError:
                pass
            self._anim = None

    def set_collapsed(self, hidden: bool) -> None:
        """Hide the sidebar completely (``True``) or bring it back (``False``)."""
        if self.floating:
            self._end_peek(immediate=True)
        self.hidden_mode = hidden
        self._stop_anim()
        if hidden:
            self._anim = motion().animate_property(self, b"sidebarWidth", self._width, 0.0, 220,
                                                   on_finished=self._finish_hide)
        else:
            self.show()
            self._anim = motion().animate_property(self, b"sidebarWidth", self._width, float(EXPANDED_W), 240)

    def _finish_hide(self) -> None:
        self._anim = None
        if self.hidden_mode and not self.floating:
            self.hide()

    # Peek: slide in over the canvas while hidden.
    def _get_slide(self) -> float:
        return self._slide

    def _set_slide(self, v: float) -> None:
        self._slide = float(v)
        self.move(int(round(-EXPANDED_W * (1.0 - self._slide))), 0)

    slide = pyqtProperty(float, _get_slide, _set_slide)

    def peek(self) -> None:
        if not self.hidden_mode or self.floating:
            return
        host = self.parentWidget()
        lay = host.layout() if host is not None else None
        if lay is not None:
            lay.removeWidget(self)
        self.floating = True
        self.header.toggle.set_glyph("openpane")
        self.header.toggle.setToolTip("Keep the sidebar open (Ctrl+B)")
        self._stop_anim()
        self._width = float(EXPANDED_W)
        self.setFixedWidth(EXPANDED_W)
        self.setGeometry(-EXPANDED_W, 0, EXPANDED_W, host.height() if host else self.height())
        self.show()
        self.raise_()
        self._anim = motion().animate_property(self, b"slide", 0.0, 1.0, 220, QEasingCurve.Type.OutCubic)

    def _maybe_end_peek(self) -> None:
        if not self.floating:
            return
        if QApplication.activePopupWidget() is not None or self.underMouse():
            self._peek_hide.start()
            return
        self._end_peek()

    def _end_peek(self, immediate: bool = False) -> None:
        if not self.floating:
            return
        self._stop_anim()

        def done():
            self._anim = None
            self.floating = False
            self.header.toggle.set_glyph("closepane")
            self.header.toggle.setToolTip("Hide sidebar (Ctrl+B)")
            self.hide()
            self._width = 0.0
            self.setFixedWidth(0)
            host = self.parentWidget()
            lay = host.layout() if host is not None else None
            if lay is not None and lay.indexOf(self) < 0:
                lay.insertWidget(0, self)
        if immediate:
            done()
            return
        self._anim = motion().animate_property(self, b"slide", self._slide, 0.0, 180, QEasingCurve.Type.InCubic,
                                               on_finished=done)

    def enterEvent(self, e) -> None:
        self._peek_hide.stop()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        if self.floating:
            self._peek_hide.start()
        super().leaveEvent(e)

    def host_resized(self, height: int) -> None:
        if self.floating:
            self.resize(EXPANDED_W, height)

    # ---------------------------------------------------------------- paint
    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        if self.floating:
            p.fillRect(self.rect(), th.c("panel"))
            p.setPen(QPen(th.c("panel_border"), 1))
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        else:
            p.fillRect(self.rect(), th.surface("sidebar"))
        sp = self.ctx.state.active_space
        if sp is not None:
            # A faint wash of the active space's colour gives every space its own mood.
            grad = QLinearGradient(0, 0, 0, 220)
            c = QColor(sp.color)
            c.setAlphaF(0.10 if th.dark else 0.08)
            grad.setColorAt(0, c)
            c.setAlphaF(0.0)
            grad.setColorAt(1, c)
            p.fillRect(QRect(0, 0, self.width(), 220), grad)
        p.end()
