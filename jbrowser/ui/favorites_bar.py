"""Collapsible bookmarks bar (Ctrl+Shift+B)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QUrl, pyqtProperty
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QMenu, QWidget

from jbrowser.core.motion import motion
from jbrowser.services.bookmarks import Bookmark
from jbrowser.ui.icons import draw_glyph
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton, menu_action, submenu

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

BAR_H = 34


class FavoriteChip(QAbstractButton):
    def __init__(self, bm: Bookmark, bar: "FavoritesBar"):
        super().__init__(bar)
        self.bm = bm
        self.bar = bar
        self._hover = False
        self.setToolTip(f"{bm.title}\n{bm.url}\nClick: new card · Shift: this card · Ctrl/middle: background")
        fm = self.fontMetrics()
        self._text = fm.elidedText(bm.title or bm.url, Qt.TextElideMode.ElideRight, 150)
        self.setFixedSize(min(190, fm.horizontalAdvance(self._text) + 38), 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        ui = self.bar.ui
        url = QUrl(self.bm.url)
        if e.button() == Qt.MouseButton.MiddleButton or (
                e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            ui.open_url(url, "background")
        elif e.button() == Qt.MouseButton.LeftButton:
            ui.open_url(url, "current" if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else "new")
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        self.bar.show_chip_menu(self.bm, e.globalPos())

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        if self._hover or self.isDown():
            path = QPainterPath()
            path.addRoundedRect(r, 7, 7)
            p.fillPath(path, th.c("pressed") if self.isDown() else th.c("hover"))
        ic = self.bar.ctx.favicons.get(self.bm.url)
        icon_rect = QRectF(10, (self.height() - 16) / 2, 16, 16)
        if not ic.isNull():
            p.drawPixmap(icon_rect.toRect(), ic.pixmap(QSize(16, 16), self.devicePixelRatioF()))
        else:
            draw_glyph(p, icon_rect, "globe", th.c("text2"), 12)
        p.setPen(th.c("text"))
        p.drawText(QRectF(32, 0, self.width() - 38, self.height()), Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()


class FavoritesBar(QWidget):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.ui = ui
        self._h = float(BAR_H if ctx.settings.get("appearance.favorites_bar") else 0)
        self.setFixedHeight(int(self._h))
        self._chips: list[FavoriteChip] = []
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(10, 0, 10, 2)
        self.lay.setSpacing(2)
        self.overflow = IconButton("chev_right", "More bookmarks", self, size=28, glyph_px=11)
        self.overflow.clicked.connect(self._show_overflow)
        self.add_btn = IconButton("add", "Bookmark this page (Ctrl+D)", self, size=28, glyph_px=12)
        self.add_btn.clicked.connect(ui.toggle_bookmark)
        ctx.bookmarks.changed.connect(self.rebuild)
        ctx.favicons.updated.connect(lambda _h: [c.update() for c in self._chips])
        self._hidden_items: list[Bookmark] = []
        self.rebuild()

    def _get_h(self) -> float:
        return self._h

    def _set_h(self, v: float) -> None:
        self._h = float(v)
        self.setFixedHeight(int(round(v)))

    barHeight = pyqtProperty(float, _get_h, _set_h)

    def set_shown(self, shown: bool) -> None:
        motion().animate_property(self, b"barHeight", self._h, float(BAR_H if shown else 0), 180)

    def rebuild(self) -> None:
        for c in self._chips:
            c.deleteLater()
        self._chips.clear()
        while self.lay.count():
            self.lay.takeAt(0)
        for bm in self.ctx.bookmarks.bar_items():
            chip = FavoriteChip(bm, self)
            self._chips.append(chip)
            self.lay.addWidget(chip)
        self.lay.addStretch(1)
        self.lay.addWidget(self.overflow)
        self.lay.addWidget(self.add_btn)
        self._fit()
        self.update()

    def _fit(self) -> None:
        avail = self.width() - 90
        used = 0
        self._hidden_items = []
        for chip in self._chips:
            used += chip.width() + 2
            fits = used <= avail
            chip.setVisible(fits)
            if not fits:
                self._hidden_items.append(chip.bm)
        self.overflow.setVisible(bool(self._hidden_items))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit()

    def _show_overflow(self) -> None:
        menu = QMenu(self)
        for bm in self._hidden_items:
            menu_action(menu, bm.title or bm.url, lambda u=bm.url: self.ui.open_url(QUrl(u), "new"))
        menu.exec(self.overflow.mapToGlobal(QPoint(0, self.overflow.height())))

    def show_chip_menu(self, bm: Bookmark, pos: QPoint) -> None:
        menu = QMenu(self)
        url = QUrl(bm.url)
        menu_action(menu, "Open in new card", lambda: self.ui.open_url(url, "new"), "add")
        menu_action(menu, "Open in this card", lambda: self.ui.open_url(url, "current"), "page")
        menu_action(menu, "Open in background card", lambda: self.ui.open_url(url, "background"), "taskview")
        sub = submenu(menu, "Open in space", "people")
        for sp in self.ctx.state.spaces:
            menu_action(sub, f"{sp.icon}  {sp.name}", lambda sid=sp.id: self.ui.open_url(url, "new", space_id=sid))
        menu.addSeparator()
        menu_action(menu, "Edit…", lambda: self.ui.edit_bookmark(bm.id), "edit")
        menu_action(menu, "Remove from bookmarks bar",
                    lambda: self.ctx.bookmarks.update(bm.id, on_bar=False), "clear")
        menu_action(menu, "Delete bookmark", lambda: self.ctx.bookmarks.remove(bm.id), "delete")
        menu.exec(pos)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        theme().paint_base(p, self.rect())           # never bare backdrop (Theme.backdrop_color)
        if not self._chips and self.height() > 10:
            p.setPen(theme().c("text3"))
            p.drawText(self.rect().adjusted(16, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter,
                       "Bookmark pages with Ctrl+D to pin them here")
        p.end()
