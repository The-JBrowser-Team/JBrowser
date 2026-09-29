"""The Gallery (Ctrl+Shift+G, or the Gallery button on the ribbon): every card of a space, or of all
spaces, as a grid of live thumbnails.

* Cards pop in one after another; hovering lifts a card; opening one zooms into it as the Gallery
  fades away and the canvas behind scrolls to that card.
* "This space / All spaces" switches the scope (remembered in ``gallery.all_spaces``); with all
  spaces, every space gets its own colour-coded section.
* Type to filter by title or address. Drag a card to reorder it, or onto another space to move it.
* Keyboard: arrow keys move between cards, Enter opens, Delete closes the card, the Menu key opens
  the card menu, Esc (or the Gallery button) goes back. Everything respects "Fluid animations".

Thumbnails come from the card itself when it is on screen, otherwise from the snapshot JBrowser
keeps of cards that went out of sight or to sleep, otherwise a coloured placeholder with the
site's icon.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, \
    QRadialGradient
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                             QScrollArea, QVBoxLayout, QWidget)

from jbrowser.core.motion import motion
from jbrowser.models.space import Space
from jbrowser.models.tab import Tab
from jbrowser.ui.card import is_blank
from jbrowser.ui.icons import draw_emoji, draw_glyph
from jbrowser.ui.theme import mix, theme
from jbrowser.ui.widgets import IconButton

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

MARGIN = 28
GAP = 18
MIN_TILE_W = 210
MAX_TILE_W = 330
THUMB_RATIO = 0.62
FOOTER_H = 48
SECTION_H = 46
RADIUS = 12
STAGGER_MS = 26          # delay between tiles as they pop in
POP_MS = 420             # one tile's pop-in
DRAG_START = 8


def _stop(anim) -> None:
    """Stop an animation that may already have finished (motion animations delete themselves)."""
    if anim is not None:
        try:
            anim.stop()
        except RuntimeError:
            pass


def _out_back(x: float, s: float = 1.55) -> float:
    x -= 1.0
    return 1.0 + (s + 1.0) * x * x * x + s * x * x


def _out_cubic(x: float) -> float:
    return 1.0 - (1.0 - x) ** 3


@dataclass
class Item:
    tab: Tab | None               # None: the "New card" tile of a section
    space: Space
    rect: QRectF = field(default_factory=QRectF)
    order: int = 0                # position in the pop-in sequence

    @property
    def key(self) -> str:
        return self.tab.id if self.tab is not None else "new:" + self.space.id


@dataclass
class Section:
    space: Space
    header: QRectF = field(default_factory=QRectF)
    area: QRectF = field(default_factory=QRectF)     # header + tiles (a drop target for moving cards)
    items: list[Item] = field(default_factory=list)


class ScopeToggle(QAbstractButton):
    """Two-segment switch: "This space" | "All spaces", with a sliding highlight."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Show cards from")
        self._labels = ("This space", "All spaces")
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        self.setFont(f)
        fm = QFontMetrics(f)
        self._seg_w = max(fm.horizontalAdvance(t) for t in self._labels) + 40
        self.setFixedSize(self._seg_w * 2 + 6, 34)
        self._pos = 0.0
        self._anim: QVariantAnimation | None = None
        self.toggled.connect(self._slide)
        self._sync_text()

    def _sync_text(self) -> None:
        self.setAccessibleDescription(self._labels[1 if self.isChecked() else 0])
        self.setToolTip("Showing cards from all spaces" if self.isChecked() else "Showing cards from this space")

    def set_checked_quiet(self, on: bool) -> None:
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._pos = 1.0 if on else 0.0
        self._sync_text()
        self.update()

    def _slide(self, on: bool) -> None:
        self._sync_text()
        _stop(self._anim)

        def frame(v):
            self._pos = float(v)
            self.update()
        self._anim = motion().animate_value(self, self._pos, 1.0 if on else 0.0, frame, 220,
                                            QEasingCurve.Type.OutCubic,
                                            on_finished=lambda: setattr(self, "_anim", None))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            want = e.position().x() > self.width() / 2
            if want != self.isChecked():
                self.setChecked(want)
                self.clicked.emit()
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        e.accept()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            want = (e.key() == Qt.Key.Key_Right) if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) \
                else not self.isChecked()
            if want != self.isChecked():
                self.setChecked(want)
                self.clicked.emit()
            return
        super().keyPressEvent(e)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, th.c("input"))
        p.setPen(QPen(th.c("focus_ring") if self.hasFocus() else th.c("input_border"), 1.2 if self.hasFocus() else 1))
        p.drawPath(path)
        knob = QRectF(3 + self._pos * self._seg_w, 3, self._seg_w, r.height() - 5)
        kp = QPainterPath()
        kp.addRoundedRect(knob, knob.height() / 2, knob.height() / 2)
        p.fillPath(kp, th.c("accent"))
        for i, text in enumerate(self._labels):
            seg = QRectF(3 + i * self._seg_w, 0, self._seg_w, self.height())
            on = abs(self._pos - i) < 0.5
            glyph_r = QRectF(seg.left() + 12, 0, 16, self.height())
            color = th.accent_text() if on else th.c("text2")
            draw_glyph(p, glyph_r, "grid" if i == 0 else "layers", color, 11)
            p.setPen(color)
            p.drawText(seg.adjusted(30, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()


class GalleryGrid(QWidget):
    """Custom-painted grid of card tiles (inside the Gallery's scroll area)."""

    opened = pyqtSignal(str)              # tab id
    newCard = pyqtSignal(str)             # space id
    spaceChosen = pyqtSignal(str)         # space id (its section header was clicked)

    def __init__(self, gallery: "Gallery"):
        super().__init__(gallery)
        self.gallery = gallery
        self.sections: list[Section] = []
        self.items: list[Item] = []       # every visible tile, in reading order
        self.show_headers = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Cards")
        self.focus_index = 0
        self.hover: str | None = None
        self.hover_close = False
        self._hover_p: dict[str, float] = {}
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(16)
        self._hover_timer.timeout.connect(self._step_hover)
        self.intro_ms = 0.0                # pop-in clock in ms (see _tile_progress)
        self.exit = 0.0
        self.exit_key: str | None = None
        self._scaled: dict[tuple, QPixmap] = {}
        self._press: tuple[str, QPoint] | None = None
        self.drag_key: str | None = None
        self.drag_pos = QPointF()
        self.drop_section: Section | None = None
        self.drop_index = -1
        self.empty_text = ""

    # ------------------------------------------------------------------ layout
    def set_content(self, sections: list[Section], show_headers: bool, empty_text: str) -> None:
        keep = self.items[self.focus_index].key if 0 <= self.focus_index < len(self.items) else None
        self.sections = sections
        self.show_headers = show_headers
        self.empty_text = empty_text
        self.relayout()
        keys = [it.key for it in self.items]
        self.focus_index = keys.index(keep) if keep in keys else self._initial_focus()
        self._scaled.clear()
        self._announce()
        self.update()

    def _initial_focus(self) -> int:
        active = self.gallery.ctx.state.active_tab
        for i, it in enumerate(self.items):
            if active is not None and it.tab is active:
                return i
        return 0

    def relayout(self) -> None:
        width = max(320, self.parentWidget().width() if self.parentWidget() else self.width())
        avail = width - 2 * MARGIN
        cols = max(1, int((avail + GAP) // (MIN_TILE_W + GAP)))
        tile_w = min(MAX_TILE_W, (avail - (cols - 1) * GAP) / cols)
        cols = max(1, min(cols, int((avail + GAP) // (tile_w + GAP))))
        grid_w = cols * tile_w + (cols - 1) * GAP
        left = (width - grid_w) / 2
        tile_h = tile_w * THUMB_RATIO + FOOTER_H
        y = 12.0
        self.items = []
        order = 0
        for sec in self.sections:
            top = y
            if self.show_headers:
                sec.header = QRectF(left, y, grid_w, SECTION_H)
                y += SECTION_H + 8
            for i, it in enumerate(sec.items):
                c, r = i % cols, i // cols
                it.rect = QRectF(left + c * (tile_w + GAP), y + r * (tile_h + GAP), tile_w, tile_h)
                it.order = order
                order += 1
                self.items.append(it)
            rows = math.ceil(len(sec.items) / cols) if sec.items else 0
            y += rows * (tile_h + GAP)
            sec.area = QRectF(left - 10, top - 6, grid_w + 20, y - top + 6)
            y += 14 if self.show_headers else 0
        self.setFixedSize(width, int(max(y + 20, 200)))

    # ------------------------------------------------------------- animation
    def pop_in_duration(self) -> int:
        return POP_MS + STAGGER_MS * min(len(self.items), 24)

    def _tile_progress(self, it: Item) -> float:
        start = STAGGER_MS * min(it.order, 24)
        return max(0.0, min(1.0, (self.intro_ms - start) / POP_MS))

    def _step_hover(self) -> None:
        busy = False
        for key in set(self._hover_p) | ({self.hover} if self.hover else set()):
            target = 1.0 if key == self.hover or (self.hasFocus() and self._focused_key() == key) else 0.0
            cur = self._hover_p.get(key, 0.0)
            nxt = cur + (target - cur) * (0.28 if motion().enabled else 1.0)
            if abs(nxt - target) < 0.01:
                nxt = target
            else:
                busy = True
            if nxt <= 0.0:
                self._hover_p.pop(key, None)
            else:
                self._hover_p[key] = nxt
        self.update()
        if not busy:
            self._hover_timer.stop()

    def _focused_key(self) -> str | None:
        return self.items[self.focus_index].key if 0 <= self.focus_index < len(self.items) else None

    # ----------------------------------------------------------------- input
    def _item_at(self, pos: QPointF) -> Item | None:
        for it in self.items:
            if it.rect.contains(pos):
                return it
        return None

    def _close_rect(self, it: Item) -> QRectF:
        return QRectF(it.rect.right() - 34, it.rect.top() + 10, 24, 24)

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        if self._press is not None and e.buttons() & Qt.MouseButton.LeftButton:
            key, start = self._press
            if self.drag_key is None and (pos.toPoint() - start).manhattanLength() > DRAG_START and \
                    not key.startswith("new:"):
                self.drag_key = key
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self.drag_key is not None:
                self.drag_pos = pos
                self._update_drop(pos)
                self.gallery.autoscroll(e.position().toPoint())
                self.update()
                return
        it = self._item_at(pos)
        key = it.key if it else None
        on_close = bool(it and it.tab is not None and self._close_rect(it).contains(pos))
        if key != self.hover or on_close != self.hover_close:
            self.hover = key
            self.hover_close = on_close
            self.setCursor(Qt.CursorShape.PointingHandCursor if it else Qt.CursorShape.ArrowCursor)
            if it is not None:
                self.setToolTip(self._describe(it))
            self._hover_timer.start()
        header = next((s for s in self.sections if self.show_headers and s.header.contains(pos)), None)
        if header is not None and it is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Switch to {header.space.name}")

    def leaveEvent(self, e) -> None:
        self.hover = None
        self.hover_close = False
        self._hover_timer.start()

    def mousePressEvent(self, e) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = e.position()
        it = self._item_at(pos)
        if it is None:
            header = next((s for s in self.sections if self.show_headers and s.header.contains(pos)), None)
            if header is not None and e.button() == Qt.MouseButton.LeftButton:
                self.spaceChosen.emit(header.space.id)
            return
        self.focus_index = self.items.index(it)
        if e.button() == Qt.MouseButton.MiddleButton and it.tab is not None:
            self.gallery.ui.close_tab(it.tab.id)
        elif e.button() == Qt.MouseButton.RightButton and it.tab is not None:
            self.gallery.ui.show_card_menu(it.tab.id, e.globalPosition().toPoint())
        elif e.button() == Qt.MouseButton.LeftButton:
            if it.tab is not None and self._close_rect(it).contains(pos):
                self.gallery.ui.close_tab(it.tab.id)
                return
            self._press = (it.key, pos.toPoint())
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        press, self._press = self._press, None
        if self.drag_key is not None:
            self._finish_drag()
            return
        if press is None or e.button() != Qt.MouseButton.LeftButton:
            return
        it = self._item_at(e.position())
        if it is None or it.key != press[0]:
            return
        self._activate(it)

    def _activate(self, it: Item) -> None:
        if it.tab is None:
            self.newCard.emit(it.space.id)
        else:
            self.opened.emit(it.tab.id)

    def keyPressEvent(self, e) -> None:
        k = e.key()
        n = len(self.items)
        if not n:
            super().keyPressEvent(e)
            return
        cur = self.items[max(0, min(self.focus_index, n - 1))]
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._move_focus(self.focus_index + (1 if k == Qt.Key.Key_Right else -1))
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._move_focus(self._vertical_neighbour(cur, -1 if k == Qt.Key.Key_Up else 1))
        elif k == Qt.Key.Key_Home:
            self._move_focus(0)
        elif k == Qt.Key.Key_End:
            self._move_focus(n - 1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._activate(cur)
        elif k == Qt.Key.Key_Delete and cur.tab is not None:
            self.gallery.ui.close_tab(cur.tab.id)
        elif k == Qt.Key.Key_Menu or (k == Qt.Key.Key_F10 and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if cur.tab is not None:
                self.gallery.ui.show_card_menu(cur.tab.id, self.mapToGlobal(cur.rect.center().toPoint()))
        elif k == Qt.Key.Key_Escape:
            self.gallery.close_gallery()
        elif e.text() and e.text().isprintable() and not e.modifiers() & ~Qt.KeyboardModifier.ShiftModifier:
            self.gallery.start_typing(e.text())      # typing filters the cards
        else:
            super().keyPressEvent(e)

    def _vertical_neighbour(self, cur: Item, direction: int) -> int:
        cx = cur.rect.center().x()
        rows = sorted({round(it.rect.top()) for it in self.items})
        row = rows.index(round(cur.rect.top()))
        target_row = row + direction
        if not 0 <= target_row < len(rows):
            return self.focus_index
        y = rows[target_row]
        candidates = [(abs(it.rect.center().x() - cx), i) for i, it in enumerate(self.items) if round(it.rect.top()) == y]
        return min(candidates)[1] if candidates else self.focus_index

    def _move_focus(self, index: int) -> None:
        if not self.items:
            return
        self.focus_index = max(0, min(len(self.items) - 1, index))
        it = self.items[self.focus_index]
        self.gallery.ensure_visible(it.rect)
        self._announce()
        self._hover_timer.start()
        self.update()

    def _describe(self, it: Item) -> str:
        if it.tab is None:
            return f"New card in {it.space.name}"
        state = []
        if it.tab.pinned:
            state.append("pinned")
        if it.tab.sleeping:
            state.append("sleeping")
        if it.tab.audible:
            state.append("playing sound")
        extra = f" ({', '.join(state)})" if state else ""
        return f"{it.tab.display_title()}{extra}\n{_host(it.tab.url) or it.tab.url}\n{it.space.name}"

    def _announce(self) -> None:
        if not self.items:
            self.setAccessibleDescription(self.empty_text)
            return
        it = self.items[self.focus_index]
        self.setAccessibleDescription(f"{self.focus_index + 1} of {len(self.items)}: " +
                                      self._describe(it).replace("\n", ", "))

    def focusInEvent(self, e) -> None:
        self._announce()
        self._hover_timer.start()
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:
        self._hover_timer.start()
        super().focusOutEvent(e)

    # -------------------------------------------------------------- dragging
    def _update_drop(self, pos: QPointF) -> None:
        sec = next((s for s in self.sections if s.area.contains(pos)), None)
        if sec is None and self.sections and not self.show_headers:
            sec = self.sections[0]
        self.drop_section = sec
        self.drop_index = -1
        if sec is None:
            return
        tiles = [it for it in sec.items if it.tab is not None]
        index = len(tiles)
        for i, it in enumerate(tiles):
            r = it.rect
            if pos.y() < r.bottom() + GAP / 2 and (pos.y() < r.top() - GAP / 2 or pos.x() < r.center().x()):
                index = i
                break
        self.drop_index = index

    def _finish_drag(self) -> None:
        key, sec, index = self.drag_key, self.drop_section, self.drop_index
        self.drag_key = None
        self.drop_section = None
        self.drop_index = -1
        self.unsetCursor()
        self.update()
        tab = self.gallery.ctx.state.tab(key) if key else None
        if tab is None or sec is None:
            return
        if sec.space.id != tab.space_id:
            self.gallery.ui.move_tab_to_space(tab.id, sec.space.id)
            return
        old = sec.space.index_of(tab.id)
        new = index - 1 if index > old else index
        self.gallery.ctx.state.move_tab(tab.id, max(0, new))

    # ----------------------------------------------------------------- paint
    def paintEvent(self, e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QRectF(e.rect()).adjusted(-40, -40, 40, 40)
        if not self.items and self.empty_text:
            p.setPen(th.c("text2"))
            f = QFont(self.font())
            f.setPointSizeF(11)
            p.setFont(f)
            p.drawText(QRectF(0, 40, self.width(), 60), Qt.AlignmentFlag.AlignCenter, self.empty_text)
        for sec in self.sections:
            if self.show_headers and sec.area.intersects(clip):
                p.save()                   # keeps the header's brush / pen from filling the tiles' outlines
                self._paint_section(p, sec)
                p.restore()
        focused = self._focused_key() if self.hasFocus() else None
        for it in self.items:
            if not it.rect.adjusted(-30, -30, 30, 30).intersects(clip):
                continue
            if it.key == self.drag_key:
                self._paint_placeholder(p, it.rect)
                continue
            self._paint_tile(p, it, focused == it.key)
        if self.drag_key is not None:
            self._paint_drop_marker(p)
            drag = next((it for it in self.items if it.key == self.drag_key), None)
            if drag is not None:
                r = QRectF(drag.rect)
                r.moveCenter(self.drag_pos)
                p.save()
                p.setOpacity(0.92)
                self._paint_tile(p, Item(drag.tab, drag.space, r, drag.order), False, lifted=True)
                p.restore()
        p.end()

    def _paint_section(self, p: QPainter, sec: Section) -> None:
        th = theme()
        r = sec.header
        color = QColor(sec.space.color)
        if self.drag_key is not None and sec is self.drop_section:
            tab = self.gallery.ctx.state.tab(self.drag_key)
            if tab is not None and tab.space_id != sec.space.id:
                path = QPainterPath()
                path.addRoundedRect(sec.area, 16, 16)
                p.fillPath(path, th.accent_alpha(0.08))
                p.setPen(QPen(th.c("accent"), 1.5, Qt.PenStyle.DashLine))
                p.drawPath(path)
        grad = QLinearGradient(r.topLeft(), r.topRight())
        a = QColor(color)
        a.setAlphaF(0.22)
        b = QColor(color)
        b.setAlphaF(0.0)
        grad.setColorAt(0, a)
        grad.setColorAt(0.6, b)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, grad)
        circle = QRectF(r.left() + 6, r.top() + 6, r.height() - 12, r.height() - 12)
        bg = QColor(color)
        bg.setAlphaF(0.35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(circle)
        draw_emoji(p, circle, sec.space.icon, 15)
        f = QFont(self.font())
        f.setPointSizeF(11.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(th.c("text"))
        fm = QFontMetrics(f)
        name_x = circle.right() + 12
        p.drawText(QRectF(name_x, r.top(), r.width() / 2, r.height()), Qt.AlignmentFlag.AlignVCenter, sec.space.name)
        n = sum(1 for it in sec.items if it.tab is not None)
        f2 = QFont(self.font())
        f2.setPointSizeF(9)
        p.setFont(f2)
        p.setPen(th.c("text3"))
        label = f"{n} card{'s' if n != 1 else ''}" + ("  ·  incognito" if sec.space.incognito else "")
        if sec.space.id == self.gallery.ctx.state.active_space_id:
            label += "  ·  current space"
        p.drawText(QRectF(name_x + fm.horizontalAdvance(sec.space.name) + 14, r.top(), r.width(), r.height()),
                   Qt.AlignmentFlag.AlignVCenter, label)

    def _thumb(self, it: Item, size: QSize) -> QPixmap | None:
        src = self.gallery.thumbnail(it.tab) if it.tab is not None else None
        if src is None or src.isNull():
            return None
        dpr = self.devicePixelRatioF()
        key = (it.key, src.cacheKey(), size.width(), size.height())
        pm = self._scaled.get(key)
        if pm is None:
            target = QSize(int(size.width() * dpr), int(size.height() * dpr))
            scaled = src.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            pm = scaled.copy(0, 0, min(scaled.width(), target.width()), min(scaled.height(), target.height()))
            pm.setDevicePixelRatio(dpr)
            if len(self._scaled) > 400:
                self._scaled.clear()
            self._scaled[key] = pm
        return pm

    def _paint_tile(self, p: QPainter, it: Item, focused: bool, lifted: bool = False) -> None:
        th = theme()
        prog = 1.0 if lifted else self._tile_progress(it)
        if prog <= 0.0:
            return
        hov = 1.0 if lifted else self._hover_p.get(it.key, 0.0)
        ease = _out_back(prog)
        scale = (0.82 + 0.18 * ease) * (1.0 + 0.025 * hov)
        lift = -4.0 * hov + (1.0 - _out_cubic(prog)) * 22.0
        opacity = min(1.0, prog * 1.7)
        if self.exit > 0:
            chosen = it.key == self.exit_key
            scale *= 1.0 + (0.14 if chosen else -0.06) * _out_cubic(self.exit)
            opacity *= 1.0 - self.exit * (0.6 if chosen else 1.0)
        r = it.rect
        p.save()
        p.setOpacity(p.opacity() * opacity)
        base_opacity = p.opacity()
        c = r.center()
        p.translate(c.x(), c.y() + lift)
        p.scale(scale, scale)
        p.translate(-c.x(), -c.y())
        # shadow
        shadow = th.c("shadow")
        for spread, alpha in ((14, 0.07), (8, 0.12), (3, 0.20)):
            sc = QColor(shadow)
            sc.setAlphaF(shadow.alphaF() * alpha * (1.0 + 1.4 * hov))
            sp = QPainterPath()
            sp.addRoundedRect(r.adjusted(-spread, -spread + 4 + 3 * hov, spread, spread + 6 + 3 * hov),
                              RADIUS + spread, RADIUS + spread)
            p.fillPath(sp, sc)
        tile = QPainterPath()
        tile.addRoundedRect(r, RADIUS, RADIUS)
        p.setBrush(Qt.BrushStyle.NoBrush)  # drawPath(tile) below only outlines
        if it.tab is None:
            self._paint_new_tile(p, it, tile, hov)
            if focused:
                self._paint_focus(p, r)
            p.restore()
            return
        tab = it.tab
        p.fillPath(tile, th.surface("card"))
        thumb_r = QRectF(r.left(), r.top(), r.width(), r.width() * THUMB_RATIO)
        p.save()
        p.setClipPath(tile)
        pm = self._thumb(it, QSize(int(thumb_r.width()), int(thumb_r.height())))
        if pm is not None:
            if tab.sleeping:
                p.setOpacity(p.opacity() * 0.55)
            p.drawPixmap(thumb_r.topLeft(), pm)
        else:
            self._paint_placeholder_thumb(p, thumb_r, it)
        p.restore()
        p.setPen(QPen(th.c("divider"), 1))
        p.drawLine(QPointF(r.left(), thumb_r.bottom()), QPointF(r.right(), thumb_r.bottom()))
        # footer: favicon, title, site
        foot = QRectF(r.left(), thumb_r.bottom(), r.width(), r.bottom() - thumb_r.bottom())
        icon_r = QRectF(foot.left() + 12, foot.center().y() - 8, 16, 16)
        if not tab.icon.isNull():
            p.drawPixmap(icon_r.toRect(), tab.icon.pixmap(QSize(16, 16), self.devicePixelRatioF()))
        else:
            draw_glyph(p, icon_r, "globe", th.c("text3"), 13)
        badges = []
        if tab.pinned:
            badges.append("pin")
        if tab.audible or tab.muted:
            badges.append("mute" if tab.muted else "volume")
        if tab.sleeping:
            badges.append("moon")
        bx = foot.right() - 12
        for g in badges:
            br = QRectF(bx - 16, foot.center().y() - 8, 16, 16)
            draw_glyph(p, br, g, th.c("sleep") if g == "moon" else th.c("text2"), 11)
            bx -= 20
        text_w = bx - icon_r.right() - 16
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(th.c("text"))
        fm = QFontMetrics(f)
        p.drawText(QRectF(icon_r.right() + 10, foot.top() + 7, text_w, 18), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(tab.display_title(), Qt.TextElideMode.ElideRight, int(text_w)))
        f.setPointSizeF(8.5)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(th.c("text3"))
        host = _host(tab.url) or ("New card" if not tab.url else tab.url)
        p.drawText(QRectF(icon_r.right() + 10, foot.top() + 25, text_w, 16), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f).elidedText(host, Qt.TextElideMode.ElideRight, int(text_w)))
        # current card of its space
        space_active = it.space.active_tab_id == tab.id
        if space_active:
            p.setPen(QPen(th.c("accent"), 2))
            p.drawPath(tile)
            chip = QRectF(r.left() + 10, r.top() + 10, 64, 20)
            cp = QPainterPath()
            cp.addRoundedRect(chip, 10, 10)
            p.fillPath(cp, th.c("accent"))
            f.setPointSizeF(8)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(th.accent_text())
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, "Current")
        else:
            p.setPen(QPen(th.c("card_border"), 1))
            p.drawPath(tile)
        # close button (hover / keyboard focus)
        if (hov > 0.05 or focused) and not lifted:
            cr = self._close_rect(it)
            p.setOpacity(base_opacity * max(hov, 1.0 if focused else 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            bg = QColor(0, 0, 0, 150) if not (self.hover == it.key and self.hover_close) else th.c("danger")
            p.setBrush(bg)
            p.drawEllipse(cr)
            draw_glyph(p, cr, "close", QColor("#ffffff"), 9)
        if focused:
            p.setOpacity(base_opacity)
            self._paint_focus(p, r)
        p.restore()

    def _paint_focus(self, p: QPainter, r: QRectF) -> None:
        th = theme()
        path = QPainterPath()
        path.addRoundedRect(r.adjusted(-5, -5, 5, 5), RADIUS + 5, RADIUS + 5)
        p.setPen(QPen(th.c("accent"), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _paint_placeholder_thumb(self, p: QPainter, r: QRectF, it: Item) -> None:
        th = theme()
        base = QColor(it.space.color)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, mix(th.surface("card"), base, 0.30))
        grad.setColorAt(1, mix(th.surface("card"), base, 0.08))
        p.fillRect(r, grad)
        tab = it.tab
        icon_r = QRectF(r.center().x() - 20, r.center().y() - 30, 40, 40)
        if tab is not None and not tab.icon.isNull():
            p.drawPixmap(icon_r.toRect(), tab.icon.pixmap(QSize(40, 40), self.devicePixelRatioF()))
        else:
            draw_glyph(p, icon_r, "globe", th.c("text2"), 30)
        f = QFont(self.font())
        f.setPointSizeF(9)
        p.setFont(f)
        p.setPen(th.c("text2"))
        text = _host(tab.url) if tab is not None and tab.url else "New card"
        p.drawText(QRectF(r.left() + 10, icon_r.bottom() + 8, r.width() - 20, 20), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_new_tile(self, p: QPainter, it: Item, tile: QPainterPath, hov: float) -> None:
        th = theme()
        p.fillPath(tile, mix(th.surface("card"), th.c("accent"), 0.06 + 0.10 * hov))
        p.setPen(QPen(th.accent_alpha(0.45 + 0.4 * hov), 1.6, Qt.PenStyle.DashLine))
        p.drawPath(tile)
        r = it.rect
        circle = QRectF(r.center().x() - 24, r.center().y() - 34, 48, 48)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(th.accent_alpha(0.16 + 0.2 * hov))
        p.drawEllipse(circle)
        draw_glyph(p, circle, "add", th.c("accent"), 18)
        p.setPen(th.c("text2"))
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.drawText(QRectF(r.left(), circle.bottom() + 10, r.width(), 22), Qt.AlignmentFlag.AlignCenter, "New card")

    def _paint_placeholder(self, p: QPainter, r: QRectF) -> None:
        th = theme()
        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        p.fillPath(path, th.c("hover"))
        p.setPen(QPen(th.c("text3"), 1.2, Qt.PenStyle.DashLine))
        p.drawPath(path)

    def _paint_drop_marker(self, p: QPainter) -> None:
        sec = self.drop_section
        if sec is None or self.drop_index < 0:
            return
        tab = self.gallery.ctx.state.tab(self.drag_key) if self.drag_key else None
        if tab is not None and tab.space_id != sec.space.id:
            return                                  # moving to another space: the section is highlighted
        tiles = [it for it in sec.items if it.tab is not None]
        if not tiles:
            return
        if self.drop_index < len(tiles):
            r = tiles[self.drop_index].rect
            x = r.left() - GAP / 2
        else:
            r = tiles[-1].rect
            x = r.right() + GAP / 2
        th = theme()
        p.setPen(QPen(th.c("accent"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x, r.top() + 6), QPointF(x, r.bottom() - 6))


def _host(url: str) -> str:
    h = QUrl(url).host()
    return h[4:] if h.startswith("www.") else h


class Gallery(QWidget):
    """The overlay that holds the header and the scrolling grid (child of the SpaceStack)."""

    visibilityChanged = pyqtSignal(bool)

    def __init__(self, ctx: "AppContext", ui: "BrowserController", host: QWidget):
        super().__init__(host)
        self.ctx = ctx
        self.ui = ui
        self._host = host
        self._thumbs: dict[str, QPixmap] = {}
        self._snap_seen: dict[str, int] = {}   # tab id → cacheKey of the card snapshot already considered
        self._closing = False
        self._anim: QVariantAnimation | None = None
        self.stays_on_top = True           # SpaceStack keeps it above canvases sliding in
        self.hide()
        host.installEventFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QWidget(self)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(MARGIN, 18, MARGIN, 8)
        hl.setSpacing(12)
        mark = QLabel(head)
        mark.setFixedSize(40, 40)
        mark.paintEvent = lambda _e, w=mark: self._paint_mark(w)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel("Gallery", head)
        f = QFont(self.font())
        f.setPointSizeF(17)
        f.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(f)
        self.subtitle = QLabel("", head)
        self.subtitle.setProperty("muted", True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        hl.addWidget(mark)
        hl.addLayout(titles)
        hl.addStretch(1)
        self.search = QLineEdit(head)
        self.search.setPlaceholderText("Filter cards by title or address")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(270)
        self.search.setAccessibleName("Filter cards")
        self.search.textChanged.connect(lambda _t: self.rebuild())
        self.search.installEventFilter(self)
        self.scope = ScopeToggle(head)
        self.scope.set_checked_quiet(bool(ctx.settings.get("gallery.all_spaces")))
        self.scope.clicked.connect(self._on_scope)
        self.close_btn = IconButton("close", "Close the Gallery (Esc)", head, size=34, glyph_px=11)
        self.close_btn.clicked.connect(lambda: self.close_gallery())
        hl.addWidget(self.search)
        hl.addWidget(self.scope)
        hl.addWidget(self.close_btn)
        root.addWidget(head)
        self.hint = QLabel("Click a card to open it  ·  drag to reorder it or move it to another space  ·  "
                           "Delete closes the focused card  ·  Esc goes back", self)
        self.hint.setProperty("hint", True)
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(MARGIN + 52, 0, MARGIN, 6)
        hint_row.addWidget(self.hint)
        root.addLayout(hint_row)
        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.viewport().setAutoFillBackground(False)
        self.grid = GalleryGrid(self)
        self.scroll.setWidget(self.grid)
        root.addWidget(self.scroll, 1)
        self.grid.opened.connect(self._open_card)
        self.grid.newCard.connect(self._new_card)
        self.grid.spaceChosen.connect(self._choose_space)

        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(40)
        self._rebuild_timer.timeout.connect(self.rebuild)
        st = ctx.state
        for sig in (st.tabAdded, st.tabRemoved, st.tabMoved, st.spaceAdded, st.spaceRemoved, st.spacesReordered,
                    st.spaceUpdated, st.activeTabChanged, st.activeSpaceChanged):
            sig.connect(lambda *_a: self._rebuild_timer.start() if self.isVisible() and not self._closing else None)
        ctx.pipeline.flushed.connect(lambda *_a: self.grid.update() if self.isVisible() else None)
        st.activeSpaceChanged.connect(lambda *_a: self._on_space_switched())

    # ------------------------------------------------------------- open / close
    def toggle(self, all_spaces: bool | None = None) -> None:
        if self.isVisible() and not self._closing:
            if all_spaces is not None and all_spaces != self.scope.isChecked():
                self.scope.setChecked(all_spaces)
                self._on_scope()
                return
            self.close_gallery()
        else:
            self.open_gallery(all_spaces)

    def open_gallery(self, all_spaces: bool | None = None) -> None:
        if all_spaces is not None:
            self.scope.set_checked_quiet(all_spaces)
        self._closing = False
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.capture_visible()
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        self._hide_canvases()
        self.rebuild()
        self.grid.exit = 0.0
        self.grid.exit_key = None
        self._play_intro()
        self.grid.setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, lambda: self.ensure_visible(self.grid.items[self.grid.focus_index].rect)
                          if self.grid.items else None)
        self.visibilityChanged.emit(True)

    def _play_intro(self) -> None:
        _stop(self._anim)
        total = self.grid.pop_in_duration()
        fx = QGraphicsOpacityEffect(self)
        fx.setOpacity(0.0)
        self.setGraphicsEffect(fx)

        def frame(v):
            ms = float(v)
            self.grid.intro_ms = ms
            try:
                fx.setOpacity(min(1.0, ms / 160.0))
            except RuntimeError:
                pass
            self.grid.update()

        def done():
            self._anim = None
            self.grid.intro_ms = float(total) + 1
            self.setGraphicsEffect(None)
            self.grid.update()
        self._anim = motion().animate_value(self, 0.0, float(total), frame, total, QEasingCurve.Type.Linear,
                                            on_finished=done)

    def close_gallery(self, chosen: str | None = None) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        _stop(self._anim)
        self._anim = None
        self.grid.intro_ms = float(self.grid.pop_in_duration()) + 1
        self.grid.exit_key = chosen
        self._show_canvas()                # the canvas reappears underneath as the Gallery fades
        fx = QGraphicsOpacityEffect(self)
        fx.setOpacity(1.0)
        self.setGraphicsEffect(fx)

        def frame(v):
            t = float(v)
            self.grid.exit = t
            try:
                fx.setOpacity(1.0 - _out_cubic(t))
            except RuntimeError:
                pass
            self.grid.update()

        def done():
            self._anim = None
            self.setGraphicsEffect(None)
            self.hide()
            self.grid.exit = 0.0
            self._closing = False
            self.visibilityChanged.emit(False)
            QTimer.singleShot(0, self.ui.focus_active_card)
        self._anim = motion().animate_value(self, 0.0, 1.0, frame, 240 if chosen else 170,
                                            QEasingCurve.Type.Linear, on_finished=done)

    def _open_card(self, tab_id: str) -> None:
        # The canvas behind switches space and scrolls to the card while the Gallery fades away:
        # it looks like zooming into the card.
        self.ui.activate_card(tab_id, Qt.KeyboardModifier.NoModifier, wake=True, center=True)
        self.close_gallery(chosen=tab_id)

    def _new_card(self, space_id: str) -> None:
        if space_id != self.ctx.state.active_space_id:
            self.ui.select_space(space_id)
        space = self.ctx.state.space(space_id)
        self.close_gallery()
        QTimer.singleShot(0, lambda: self.ui.open_lazy_toolbar("new", insert_at=len(space.tabs) if space else None))

    def _choose_space(self, space_id: str) -> None:
        self.ui.select_space(space_id)
        self.close_gallery()

    def _on_scope(self) -> None:
        self.ctx.settings.set("gallery.all_spaces", self.scope.isChecked())
        self.capture_visible()
        self.rebuild()
        self._play_intro()

    # While the Gallery is open the canvases are hidden: it then sits on the window's frosted
    # backdrop rather than over live web pages (which Windows would blend into it), and the cards
    # stop drawing frames nobody can see.
    def _hide_canvases(self) -> None:
        stack = self.ui.window.stack
        for canvas in stack.canvases.values():
            if canvas.isVisible():
                canvas.hide()

    def _show_canvas(self) -> None:
        stack = self.ui.window.stack
        current = stack.current()
        if current is not None and not current.isVisible():
            current.setGeometry(stack.rect())
            current.show()
        self.raise_()

    def _on_space_switched(self) -> None:
        # (after the space's canvas has been shown, and again once its slide-in has finished)
        for delay in (0, 320):
            QTimer.singleShot(delay, lambda: self._hide_canvases() if self.isVisible() and not self._closing else None)

    # ------------------------------------------------------------- content
    def rebuild(self) -> None:
        if not self.isVisible():
            return
        st = self.ctx.state
        query = self.search.text().strip().lower()
        all_spaces = self.scope.isChecked()
        spaces = list(st.spaces) if all_spaces else [st.active_space] if st.active_space else []
        sections: list[Section] = []
        total = 0
        for sp in spaces:
            sec = Section(sp)
            for tab in sp.tabs:
                if query and query not in tab.display_title().lower() and query not in tab.url.lower():
                    continue
                sec.items.append(Item(tab, sp))
            total += len(sec.items)
            if not query:
                sec.items.append(Item(None, sp))           # "New card" tile
            if sec.items or not query:
                sections.append(sec)
        if all_spaces:
            self.subtitle.setText(f"All spaces  ·  {total} card{'s' if total != 1 else ''} in "
                                  f"{len(spaces)} space{'s' if len(spaces) != 1 else ''}")
        elif spaces:
            self.subtitle.setText(f"{spaces[0].icon}  {spaces[0].name}  ·  {total} card{'s' if total != 1 else ''}")
        empty = f"No cards match “{self.search.text().strip()}”" if query and not total else ""
        self.grid.set_content(sections, all_spaces, empty)

    def thumbnail(self, tab: Tab) -> QPixmap | None:
        card = self.ui.card(tab.id)
        if card is not None:
            snap = getattr(card.snapshot, "pixmap", None)
            if snap is not None and not snap.isNull() and self._snap_seen.get(tab.id) != snap.cacheKey():
                # a snapshot taken since our last picture (leaving the space, or going to sleep): newer
                self._snap_seen[tab.id] = snap.cacheKey()
                self._thumbs[tab.id] = snap
        return self._thumbs.get(tab.id)

    def capture_visible(self) -> None:
        """Fresh pictures of the cards that are on screen right now (others use their snapshots)."""
        for canvas in self.ui.window.stack.canvases.values():
            if not canvas.isVisible():
                continue
            for tid, card in canvas.cards.items():
                tab = card.tab
                if card.on_screen and tab.loaded and not tab.sleeping and card.view.isVisible() \
                        and card.view.width() > 40 and card.view.height() > 40:
                    pm = card.view.grab()
                    if not pm.isNull():
                        if pm.width() > 900:
                            pm = pm.scaledToWidth(900, Qt.TransformationMode.SmoothTransformation)
                        if is_blank(pm):               # not painted yet: keep the placeholder / older picture
                            continue
                        self._thumbs[tid] = pm
                        snap = getattr(card.snapshot, "pixmap", None)
                        if snap is not None:           # older than this picture
                            self._snap_seen[tid] = snap.cacheKey()
        live = {t.id for t in self.ctx.state.all_tabs()}
        for tid in [t for t in self._thumbs if t not in live]:
            del self._thumbs[tid]
        for tid in [t for t in self._snap_seen if t not in live]:
            del self._snap_seen[tid]

    # --------------------------------------------------------------- helpers
    def ensure_visible(self, rect: QRectF) -> None:
        self.scroll.ensureVisible(int(rect.center().x()), int(rect.center().y()),
                                  int(rect.width() / 2 + 24), int(rect.height() / 2 + 24))

    def autoscroll(self, grid_pos: QPoint) -> None:
        vp = self.scroll.viewport()
        y = self.grid.mapTo(vp, grid_pos).y()
        bar = self.scroll.verticalScrollBar()
        if y < 40:
            bar.setValue(bar.value() - 14)
        elif y > vp.height() - 40:
            bar.setValue(bar.value() + 14)

    def start_typing(self, text: str) -> None:
        self.search.setFocus()
        self.search.setText(self.search.text() + text)

    def eventFilter(self, obj, ev) -> bool:
        from PyQt6.QtCore import QEvent
        if obj is self._host and ev.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self._host.rect())
        elif obj is self.search and ev.type() == QEvent.Type.KeyPress:
            k = ev.key()
            if k == Qt.Key.Key_Escape:
                if self.search.text():
                    self.search.clear()
                else:
                    self.close_gallery()
                return True
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self.grid.setFocus(Qt.FocusReason.TabFocusReason)
                if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.grid.items:
                    self.grid._activate(self.grid.items[0])
                return True
        return False

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.isVisible():
            QTimer.singleShot(0, lambda: (self.grid.relayout(), self.grid.update()))

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close_gallery()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        e.accept()                       # clicks never fall through to the cards underneath

    def _paint_mark(self, w: QWidget) -> None:
        th = theme()
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(w.rect()).adjusted(1, 1, -1, -1)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, th.c("accent"))
        grad.setColorAt(1, th.accent_alpha(0.55))
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        p.fillPath(path, grad)
        draw_glyph(p, r, "gallery", th.accent_text(), 17)
        p.end()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        base = th.c("canvas_solid")
        base.setAlphaF(0.84 if th.translucent else 1.0)      # frosted over Acrylic / Mica
        p.fillRect(r, base)
        # a soft glow of the accent at the top and of the space's colour at the bottom
        glow = QRadialGradient(QPointF(r.center().x(), r.top() - r.height() * 0.15), r.width() * 0.6)
        glow.setColorAt(0, th.accent_alpha(0.16))
        glow.setColorAt(1, th.accent_alpha(0.0))
        p.fillRect(r, glow)
        space = self.ctx.state.active_space
        if space is not None:
            c = QColor(space.color)
            c.setAlphaF(0.12)
            glow2 = QRadialGradient(QPointF(r.left() + r.width() * 0.15, r.bottom() + 40), r.width() * 0.5)
            glow2.setColorAt(0, c)
            c2 = QColor(c)
            c2.setAlphaF(0.0)
            glow2.setColorAt(1, c2)
            p.fillRect(r, glow2)
        p.end()
