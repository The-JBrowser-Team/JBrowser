"""The infinite horizontal canvas: cards laid out left→right, panned smoothly, resized with
animated transitions, and reporting viewport visibility to the lifecycle manager."""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from jbrowser.core.motion import motion
from jbrowser.models.space import Space
from jbrowser.models.tab import Tab
from jbrowser.ui.card import WebCard
from jbrowser.ui.icons import draw_glyph, paint_logo
from jbrowser.ui.theme import theme

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

MARGIN = 12
GAP = 12
TOP = 10
BOTTOM = 22
MIN_CARD_W = 120
LAYOUT_MS = 230
ADD_BTN = 44
PULL_DIST = 440.0   # wheel / trackpad travel past an end of the canvas that opens a new card there
REVEAL = 88.0       # how far the cards slide aside while being pulled
DRAG_LIFT = 6       # px a card rises while it is being dragged
SLOT = "__slot__"   # layout key of the empty place in a column (stack picker, or a stacking drop)
SMOOTH_TAU = 0.055  # s: wheel scrolling covers 95 % of the way to where it is heading in ~0.17 s

# Card shadows: (spread, opacity) layers, resting and lifted (dragged).
SHADOW_LAYERS = {False: ((9, 0.10), (5, 0.16), (2, 0.24)), True: ((22, 0.10), (13, 0.18), (6, 0.26))}
_shadow_cache: dict[tuple, tuple[QPixmap, int, int]] = {}


def _shadow_tile(color: QColor, lifted: bool, dpr: float) -> tuple[QPixmap, int, int]:
    """A card's soft shadow as a small nine-slice image, its padding around the card and its slice
    margin. Drawn once: painting the image's edges every frame is far cheaper than filling large
    anti-aliased shapes."""
    key = (color.rgba(), lifted, round(dpr, 2))
    cached = _shadow_cache.get(key)
    if cached is not None:
        return cached
    layers = SHADOW_LAYERS[lifted]
    spread = max(s for s, _a in layers)
    pad = spread + 5                       # room for the shadow's spread and its downward offset
    margin = pad + 10 + spread + 2         # slice margin: covers the widest rounded corner
    side = 2 * margin + 4                  # a 4 px stretchable band between the slices
    card = QRectF(pad, pad, side - 2 * pad, side - 2 * pad)
    pm = QPixmap(int(side * dpr), int(side * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for s, alpha in layers:
        c = QColor(color)
        c.setAlphaF(color.alphaF() * alpha)
        path = QPainterPath()
        path.addRoundedRect(card.adjusted(-s, -s + 3, s, s + 4), 10 + s, 10 + s)
        p.fillPath(path, c)
    p.end()
    if len(_shadow_cache) > 16:
        _shadow_cache.clear()
    _shadow_cache[key] = (pm, pad, margin)
    return _shadow_cache[key]


def _paint_shadow(p: QPainter, card: QRectF, color: QColor, lifted: bool, dpr: float) -> None:
    """Paint the shadow around ``card`` from the nine-slice tile (the middle is hidden by the card)."""
    pm, pad, m = _shadow_tile(color, lifted, dpr)
    t = card.adjusted(-pad, -pad, pad, pad)
    if t.width() < 2 * m or t.height() < 2 * m:
        return
    side = pm.width() / dpr                     # the tile is square
    xs = ((0.0, m, t.left(), m), (m, side - 2 * m, t.left() + m, t.width() - 2 * m),
          (side - m, m, t.right() - m, m))
    ys = ((0.0, m, t.top(), m), (m, side - 2 * m, t.top() + m, t.height() - 2 * m),
          (side - m, m, t.bottom() - m, m))
    for i, (sx, sw, tx, tw) in enumerate(xs):
        for j, (sy, sh, ty, th) in enumerate(ys):
            if i == 1 and j == 1:
                continue
            p.drawPixmap(QRectF(tx, ty, tw, th), pm, QRectF(sx * dpr, sy * dpr, sw * dpr, sh * dpr))


class EdgePullIndicator(QWidget):
    """The "+" that appears when the canvas is pushed past its first or last card.

    It is not a button: it grows with the push and, once the ring is full, the canvas opens a
    new card at that end. Purely visual, so it never steals clicks from the cards.
    """

    W, H = 112, 96

    def __init__(self, canvas: "Canvas"):
        super().__init__(canvas)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(self.W, self.H)
        self.progress = 0.0
        self.fired = False
        self.hint = ""
        self.hide()

    def set_state(self, progress: float, fired: bool, hint: str) -> None:
        self.progress = max(0.0, min(1.0, progress))
        self.fired = fired
        self.hint = hint
        self.setVisible(self.progress > 0.01 or fired)
        self.update()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        prog = self.progress
        ease = 1 - (1 - prog) ** 3
        p.setOpacity(min(1.0, prog * 1.8) if not self.fired else 1.0)
        d = ADD_BTN * (0.55 + 0.45 * ease) * (1.08 if self.fired else 1.0)
        c = QRectF((self.W - d) / 2, 8 + (ADD_BTN - d) / 2, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        glow = th.accent_alpha(0.18 * ease)
        p.setBrush(glow)
        p.drawEllipse(c.adjusted(-6 * ease, -6 * ease, 6 * ease, 6 * ease))
        p.setBrush(th.c("accent") if self.fired else th.surface("card"))
        p.setPen(QPen(th.c("panel_border"), 1.0))
        p.drawEllipse(c)
        if not self.fired and prog > 0:
            ring = c.adjusted(-3, -3, 3, 3)
            p.setPen(QPen(th.c("accent"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(ring, 90 * 16, -int(360 * 16 * prog))
        draw_glyph(p, c, "add", th.accent_text() if self.fired else th.c("text"), 16 * (0.7 + 0.3 * ease))
        text = self.hint or ("New card" if self.fired else "Add a card")
        p.setOpacity(max(0.0, min(1.0, (prog - 0.25) * 2.2)) if not self.fired else 1.0)
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(th.c("text2"))
        p.drawText(QRectF(0, 8 + ADD_BTN + 8, self.W, 36), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop |
                   Qt.TextFlag.TextWordWrap, text)
        p.end()


class Minimap(QWidget):
    """Overview strip: every card as a segment, the viewport as a highlighted window."""

    def __init__(self, canvas: "Canvas"):
        super().__init__(canvas)
        self.canvas = canvas
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Canvas overview. Click or drag to pan (or use Alt + mouse wheel)")

    def _scale(self) -> tuple[float, float]:
        cw = max(1.0, self.canvas.content_width())
        return self.width() / cw, cw

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sx, _ = self._scale()
        h = self.height()
        space = self.canvas.space
        for tab in space.tabs:
            geo = self.canvas.geo(tab.id)
            if geo is None:
                continue
            x, w = geo
            r = QRectF(x * sx, h * 0.3, max(2.0, w * sx - 1.5), h * 0.4)
            if tab.id == space.active_tab_id:
                c = th.c("accent")
            else:
                c = th.c("text3")
                if tab.sleeping:
                    c.setAlphaF(c.alphaF() * 0.5)
            path = QPainterPath()
            path.addRoundedRect(r, 2, 2)
            p.fillPath(path, c)
        vx = self.canvas.offset * sx
        vw = self.canvas.width() * sx
        view = QRectF(vx, 1, min(vw, self.width() - vx), h - 2)
        p.setPen(QPen(th.c("text2"), 1))
        p.setBrush(th.c("minimap"))
        p.drawRoundedRect(view, 4, 4)
        p.end()

    def _jump(self, x: float, animated: bool) -> None:
        sx, _ = self._scale()
        target = x / sx - self.canvas.width() / 2
        self.canvas.scroll_to(target, animated=animated)

    def mousePressEvent(self, e) -> None:
        self._jump(e.position().x(), True)

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._jump(e.position().x(), False)


class Canvas(QWidget):
    def __init__(self, ctx: "AppContext", space: Space, ui: "BrowserController", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.space = space
        self.ui = ui
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)   # see _background
        self._bg_key: tuple | None = None
        self._bg = QColor()
        self.cards: dict[str, WebCard] = {}
        # Card id → (x, width, top, height): x and width in px, top and height as fractions of the column.
        self._geo: dict[str, tuple[float, float, float, float]] = {}
        self._from: dict[str, tuple[float, float, float, float]] = {}
        self._to: dict[str, tuple[float, float, float, float]] = {}
        # The empty place in a column: (card it sits by, row in the column, "picker" | "drop").
        self._slot: tuple[str, int, str] | None = None
        self._slot_rect = QRect()
        self._slot_handoff: tuple[float, float, float, float] | None = None   # where a chosen card grows from
        self._stack_target: tuple[str, bool] | None = None   # dragging: (card to stack onto, above?)
        self.picker = None                                    # StackPicker while it is open
        self._offset = float(space.scroll)
        self._target_offset = self._offset
        self._pan_anim: QVariantAnimation | None = None
        # Wheel and touchpad scrolling: one layout per frame, easing towards _target_offset by time
        # (see _smooth_step), so slower PCs drop frames instead of falling behind the input.
        self._smooth = QTimer(self)
        self._smooth.setTimerType(Qt.TimerType.PreciseTimer)
        self._smooth.timeout.connect(self._smooth_step)
        self._smooth_last = 0.0
        self._smooth_jump = False
        self._layout_anim: QVariantAnimation | None = None
        self._in_view: set[str] = set()
        self._first_show = True
        self._layout_pending = False
        self._drag_tab: str | None = None
        self._drag_grab = 0.0          # pointer's distance from the dragged card's left edge
        self._drag_x = 0.0             # dragged card's left edge, in canvas content coordinates
        self._drop_space: str | None = None   # a space in the sidebar the card would move to
        self._empty_hover = False
        self._solo: str | None = None
        self.minimap = Minimap(self)
        # Pull past either end to add a card (see _wheel / edge_nudge).
        self._pull = 0.0                  # signed travel past the edge: < 0 left end, > 0 right end
        self._pull_fired = False
        self._pull_anim: QVariantAnimation | None = None
        self._pull_hint = ""
        self._pull_idle = QTimer(self)
        self._pull_idle.setSingleShot(True)
        self._pull_idle.setInterval(380)       # a pause this long between notches relaxes the pull
        self._pull_idle.timeout.connect(self._release_pull)
        self._armed_side = 0
        self._armed = QTimer(self)
        self._armed.setSingleShot(True)
        self._armed.setInterval(1800)
        self._armed.timeout.connect(self._disarm)
        self.pull_indicator = EdgePullIndicator(self)
        for tab in space.tabs:
            self._add_card(tab)
        st = ctx.state
        st.tabAdded.connect(self._on_tab_added)
        st.tabRemoved.connect(self._on_tab_removed)
        st.tabMoved.connect(self._on_tab_moved)
        st.activeTabChanged.connect(self._on_active_changed)
        st.selectionChanged.connect(self._on_selection_changed)
        ctx.settings.changed.connect(self._on_setting)
        self._on_selection_changed(space)
        self._sync_active()

    # ------------------------------------------------------------ geometry
    def _avail(self) -> float:
        return max(200.0, self.width() - 2 * MARGIN)

    def px_width(self, frac: float) -> float:
        frac = max(0.05, min(1.0, frac))
        return max(MIN_CARD_W, frac * (self._avail() + GAP) - GAP)

    def targets(self) -> dict[str, tuple[float, float, float, float]]:
        """Card id → (x, width, top, height). Cards stacked in a column share x and width and split its
        height; while the stack picker or a stacking drop is pending, SLOT is the empty place."""
        out = {}
        x = float(MARGIN)
        slot = self._slot
        for column in self.ctx.state.columns(self.space):
            w = self.px_width(column[0].width)
            rows = [t.id for t in column]
            if slot is not None and slot[0] in rows:
                rows.insert(max(0, min(slot[1], len(rows))), SLOT)
            n = len(rows)
            for i, rid in enumerate(rows):
                out[rid] = (x, w, i / n, 1 / n)
            x += w + GAP
        return out

    def content_width(self, targets: dict | None = None) -> float:
        t = targets if targets is not None else self._geo
        if not t:
            return float(self.width())
        right = max(g[0] + g[1] for g in t.values())
        return right + MARGIN

    def _rows_px(self, top: float, height: float) -> tuple[float, float]:
        """A card's top and height in px from its fractions of the column."""
        span = max(80, self.height() - TOP - BOTTOM) + GAP
        return TOP + top * span, max(1.0, height * span - GAP)

    def max_offset(self, targets: dict | None = None) -> float:
        return max(0.0, self.content_width(targets if targets is not None else self.targets()) - self.width())

    def geo(self, tab_id: str) -> tuple[float, float] | None:
        """A card's x and width in px (its column's)."""
        g = self._geo.get(tab_id)
        return (g[0], g[1]) if g else None

    @property
    def offset(self) -> float:
        return self._offset

    # -------------------------------------------------------------- layout
    def schedule_layout(self) -> None:
        if not self._layout_pending:
            self._layout_pending = True
            QTimer.singleShot(0, self._run_scheduled_layout)

    def _run_scheduled_layout(self) -> None:
        self._layout_pending = False
        self.request_layout(animated=True)

    def request_layout(self, animated: bool = True) -> None:
        targets = self.targets()
        if self._layout_anim is not None:
            self._layout_anim.stop()
            self._layout_anim = None
        if animated and motion().enabled and self.isVisible() and self._geo:
            self._from = {}
            for tid, (x, w, y, h) in targets.items():
                self._from[tid] = self._geo.get(tid) or self._entry_geo(tid, (x, w, y, h))
            self._to = targets
            anim = QVariantAnimation(self)
            anim.setDuration(motion().ms(LAYOUT_MS))
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(self._layout_frame)
            anim.finished.connect(self._layout_done)
            self._layout_anim = anim
            anim.start()
        else:
            self._geo = dict(targets)
            self._apply()
        self._clamp_offset(targets)

    def _entry_geo(self, tid: str, target: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """Where a card (or the empty slot) appears from: a card chosen in the stack picker grows out of
        the picker's place, other stacked cards and the slot grow down from the top of their row, and a
        new column grows out from its centre."""
        x, w, y, h = target
        tab = self.ctx.state.tab(tid)
        if tab is not None and tab.stack and self._slot_handoff is not None:
            g, self._slot_handoff = self._slot_handoff, None
            return g
        if tid == SLOT or (tab is not None and tab.stack):
            return (x, w, y, 0.0)
        return (x + w / 2, 0.0, y, h)

    def _layout_frame(self, t) -> None:
        t = float(t)
        geo = {}
        for tid, to in self._to.items():
            fr = self._from.get(tid, to)
            geo[tid] = tuple(a + (b - a) * t for a, b in zip(fr, to))
        self._geo = geo
        self._apply()

    def _layout_done(self) -> None:
        self._layout_anim = None
        self._geo = dict(self._to)
        self._apply()

    def set_solo(self, tab_id: str | None) -> None:
        """Immersive mode: one card fills the whole canvas (HTML5 fullscreen video, etc.)."""
        self._solo = tab_id
        for tid, card in self.cards.items():
            card.setVisible(tab_id is None or tid == tab_id)
        self._apply()

    def _apply(self) -> None:
        if self._solo is not None and self._solo in self.cards:
            self.cards[self._solo].setGeometry(self.rect())
            self.minimap.hide()
            self.pull_indicator.hide()
            self._update_visibility()
            return
        h = max(80, self.height() - TOP - BOTTOM)
        band = self._band()
        off = self._offset - band
        for tid, card in self.cards.items():
            g = self._geo.get(tid)
            if g is None:
                continue
            x, w, y, hh = g
            if tid == self._drag_tab:
                # The dragged card follows the pointer, lifted slightly above the others.
                card.setGeometry(int(round(self._drag_x - off)), TOP - DRAG_LIFT, max(1, int(round(w))), h)
                card.raise_()
                continue
            top, height = self._rows_px(y, hh)
            card.setGeometry(int(round(x - off)), int(round(top)), max(1, int(round(w))), int(round(height)))
        sg = self._geo.get(SLOT)
        if sg is not None:
            top, height = self._rows_px(sg[2], sg[3])
            self._slot_rect = QRect(int(round(sg[0] - off)), int(round(top)), max(1, int(round(sg[1]))),
                                    int(round(height)))
        else:
            self._slot_rect = QRect()
        if self.picker is not None and sg is not None:
            self.picker.setGeometry(self._slot_rect)
            self.picker.raise_()
        self._place_pull_indicator(h, off)
        self._update_visibility()
        mm_w = min(420, max(160, int(self.width() * 0.32)))
        self.minimap.setGeometry((self.width() - mm_w) // 2, self.height() - BOTTOM + 5, mm_w, 12)
        self.minimap.setVisible(bool(self.ctx.settings.get("canvas.show_minimap")) and
                                self.content_width() > self.width() + 2)
        self.minimap.update()
        self.update()

    def resizeEvent(self, e) -> None:
        if self._layout_anim is not None:
            self._layout_anim.stop()
            self._layout_anim = None
        old_w = e.oldSize().width()
        # keep the active card anchored when the window is resized
        anchor = self.space.active_tab_id
        anchor_x = None
        if anchor in self._geo and old_w > 0:
            anchor_x = self._geo[anchor][0] - self._offset
        self._geo = self.targets()
        if anchor_x is not None and anchor in self._geo:
            self._offset = self._target_offset = self._clamp(self._geo[anchor][0] - anchor_x, self._geo)
        self._clamp_offset(self._geo)
        self._apply()

    # ------------------------------------------------------------- panning
    def _clamp(self, value: float, targets: dict | None = None) -> float:
        return max(0.0, min(value, self.max_offset(targets)))

    def _clamp_offset(self, targets: dict) -> None:
        clamped = self._clamp(self._target_offset, targets)
        if abs(clamped - self._target_offset) > 0.5:
            self.scroll_to(clamped, animated=motion().enabled and self.isVisible())

    def _set_offset(self, value) -> None:
        self._offset = float(value)
        self.space.scroll = self._offset
        self._apply()

    def scroll_to(self, value: float, animated: bool = True, duration: int = 260) -> None:
        value = self._clamp(value, self.targets())
        self._target_offset = value
        self._smooth.stop()
        if self._pan_anim is not None:
            self._pan_anim.stop()
            self._pan_anim = None
        if not animated or not motion().enabled or abs(value - self._offset) < 1:
            self._set_offset(value)
            return
        anim = QVariantAnimation(self)
        anim.setDuration(motion().ms(duration))
        anim.setStartValue(self._offset)
        anim.setEndValue(value)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._set_offset)
        self._pan_anim = anim
        anim.start()

    def scroll_by(self, delta: float, animated: bool = True) -> None:
        """Wheel / touchpad scrolling. ``animated`` eases (mouse wheel notches); otherwise the canvas
        follows exactly (touchpad), but still moves at most once per frame."""
        moving = self._smooth.isActive() or self._pan_anim is not None
        base = self._target_offset if moving else self._offset
        if self._pan_anim is not None:
            self._pan_anim.stop()
            self._pan_anim = None
        self._target_offset = self._clamp(base + delta, self.targets())
        self._smooth_jump = not animated or not motion().enabled
        if not self._smooth.isActive():
            screen = self.screen()
            rate = screen.refreshRate() if screen is not None else 60.0
            # Twice per screen refresh: painting is held to the refresh rate anyway, and a tick
            # that just misses a frame no longer costs a whole frame.
            self._smooth.setInterval(max(4, int(500 / max(60.0, rate or 60.0))))
            self._smooth_last = time.perf_counter()
            self._smooth.start()

    def _smooth_step(self) -> None:
        now = time.perf_counter()
        dt, self._smooth_last = now - self._smooth_last, now
        diff = self._target_offset - self._offset
        if abs(diff) < 0.5:
            self._smooth.stop()
            if diff:
                self._set_offset(self._target_offset)
            return
        k = 1.0 if self._smooth_jump else 1.0 - math.exp(-dt / SMOOTH_TAU)
        self._set_offset(self._offset + diff * k)

    def ensure_visible(self, tab_id: str, align: str = "nearest", animated: bool = True) -> None:
        targets = self.targets()
        g = targets.get(tab_id)
        if g is None:
            return
        x, w = g[0], g[1]
        view_w = self.width()
        cur = self._target_offset
        if align == "left" or w >= view_w - 2 * MARGIN:
            new = x - MARGIN
        elif align == "center":
            new = x + w / 2 - view_w / 2
        else:
            if x - MARGIN < cur:
                new = x - MARGIN
            elif x + w + MARGIN > cur + view_w:
                new = x + w + MARGIN - view_w
            else:
                return
        self.scroll_to(new, animated=animated)

    @staticmethod
    def horizontal_delta(e) -> tuple[float, bool]:
        """The sideways part of a wheel event and whether it came from a touchpad (pixel deltas).
        Only scrolling that is mostly sideways counts, or the wheel with Shift held (Windows' usual
        horizontal scroll); up-and-down scrolling gives 0."""
        pd, ad = e.pixelDelta(), e.angleDelta()
        pixels = not pd.isNull()
        x, y = (pd.x(), pd.y()) if pixels else (ad.x(), ad.y())
        if abs(x) > abs(y):
            return float(x), pixels
        if not x and y and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return float(y), pixels
        return 0.0, pixels

    def wheelEvent(self, e) -> None:
        # Only sideways scrolling moves along the canvas. Up-and-down scrolling a page passes on when
        # it reaches its top or bottom must not slide to the next card (Alt + wheel still pans: see
        # pan_from_wheel).
        dx, pixels = self.horizontal_delta(e)
        if dx:
            self._wheel(-dx if pixels else -dx * 1.4, animated=not pixels)
        e.accept()

    def pan_from_wheel(self, e) -> None:
        """Alt + wheel anywhere over the canvas (routed by the window's event filter)."""
        pd = e.pixelDelta()
        ad = e.angleDelta()
        if not pd.isNull():
            self._wheel(-(pd.y() or pd.x()), animated=False)
        else:
            self._wheel(-(ad.y() or ad.x()) * 1.4, animated=True)

    # -------------------------------------------------- pull past the ends
    def _wheel(self, delta: float, animated: bool) -> None:
        if not delta:
            return
        if not self.space.tabs or self._solo is not None:
            self.scroll_by(delta, animated)
            return
        if self._pull:
            if (self._pull < 0) == (delta < 0):
                self._add_pull(delta)
            else:                                   # scrolling back relaxes the pull first
                rest = self._pull + delta
                if (rest < 0) == (self._pull < 0) and rest:
                    self._set_pull(rest)
                    self._pull_idle.start()
                else:
                    self._set_pull(0.0)
                    self._pull_fired = False
                    self.scroll_by(rest, animated)
            return
        at_left = self._target_offset <= 0.5
        at_right = self._target_offset >= self.max_offset() - 0.5
        if (delta < 0 and at_left) or (delta > 0 and at_right):
            self._add_pull(delta)
            return
        self.scroll_by(delta, animated)

    def _add_pull(self, delta: float) -> None:
        self._pull_idle.start()
        if self._pull_fired:
            return                                  # one card per push: release first
        self._stop_pull_anim()
        self._disarm(release=False)
        value = self._pull + delta
        value = max(-PULL_DIST, min(PULL_DIST, value))
        self._set_pull(value)
        if abs(value) >= PULL_DIST:
            self._fire_pull()

    def _stop_pull_anim(self) -> None:
        anim, self._pull_anim = self._pull_anim, None
        if anim is not None:
            try:
                anim.stop()
            except RuntimeError:          # already finished and deleted itself
                pass

    def _set_pull(self, value: float) -> None:
        self._pull = float(value)
        self._apply()

    def _band(self) -> float:
        if not self._pull:
            return 0.0
        prog = min(1.0, abs(self._pull) / PULL_DIST)
        shift = REVEAL * (1 - (1 - prog) ** 2)
        return shift if self._pull < 0 else -shift

    def _place_pull_indicator(self, h: int, off: float) -> None:
        ind = self.pull_indicator
        if not self._pull or not self._geo:
            ind.set_state(0.0, False, "")
            return
        prog = min(1.0, abs(self._pull) / PULL_DIST)
        if self._pull < 0:
            first = min(g[0] for g in self._geo.values()) - off
            cx = first / 2
        else:
            last = max(g[0] + g[1] for g in self._geo.values()) - off
            cx = last + (self.width() - last) / 2
        ind.move(int(round(cx - ind.W / 2)), int(TOP + h / 2 - ADD_BTN / 2 - 8))
        ind.set_state(prog, self._pull_fired, self._pull_hint)
        ind.raise_()

    def _fire_pull(self) -> None:
        side = -1 if self._pull < 0 else 1
        self._pull_fired = True
        self._pull_hint = ""
        self._apply()
        index = 0 if side < 0 else len(self.space.tabs)
        QTimer.singleShot(140, lambda: self.ui.open_lazy_toolbar("new", insert_at=index))
        QTimer.singleShot(320, self._release_pull)

    def _release_pull(self) -> None:
        self._pull_idle.stop()
        if not self._pull:
            self._pull_fired = False
            return
        self._stop_pull_anim()

        def frame(v):
            self._pull = float(v)
            self._apply()

        def done():
            self._pull_anim = None
            self._pull = 0.0
            self._pull_fired = False
            self._pull_hint = ""
            self._apply()
        self._pull_anim = motion().animate_value(self, self._pull, 0.0, frame, 320, QEasingCurve.Type.OutCubic,
                                                 on_finished=done)

    def edge_nudge(self, side: int) -> None:
        """Alt+← on the first card / Alt+→ on the last: the first press shows the "+",
        a second press within a moment adds the card."""
        if not self.space.tabs or self._solo is not None:
            return
        if self._armed_side == side and self._armed.isActive():
            self._armed.stop()
            self._armed_side = 0
            self._stop_pull_anim()
            self._pull_hint = ""
            self._pull = side * PULL_DIST
            self._fire_pull()
            return
        self._armed_side = side
        self._armed.start()
        self.scroll_to(0.0 if side < 0 else self.max_offset(), animated=True)
        key = "Alt+\u2190" if side < 0 else "Alt+\u2192"
        self._pull_hint = f"Press {key} again"
        self._stop_pull_anim()

        def frame(v):
            self._pull = float(v)
            self._apply()
        self._pull_anim = motion().animate_value(self, self._pull, side * PULL_DIST * 0.62, frame, 260,
                                                 QEasingCurve.Type.OutBack,
                                                 on_finished=lambda: setattr(self, "_pull_anim", None))

    def _disarm(self, release: bool = True) -> None:
        self._armed.stop()
        was = self._armed_side
        self._armed_side = 0
        self._pull_hint = ""
        if was and release and not self._pull_fired:
            self._release_pull()

    # ---------------------------------------------------------- visibility
    def _update_visibility(self) -> None:
        showing = self.isVisible() and self.window().isVisible() and not self.window().isMinimized()
        rect = self.rect()
        for tid, card in self.cards.items():
            in_view = showing and card.geometry().intersects(rect)
            if in_view != (tid in self._in_view):
                if in_view:
                    self._in_view.add(tid)
                else:
                    self._in_view.discard(tid)
                card.set_on_screen(in_view)
                self.ctx.lifecycle.set_in_view(tid, in_view, card.view.isVisible())
        if showing and self._first_show and self.cards:
            self._first_show = False
            # Lazily restored cards: load what the user can actually see (plus the focused card).
            for tid in list(self._in_view) + [self.space.active_tab_id]:
                tab = self.ctx.state.tab(tid)
                if tab is not None and tab.sleeping and not tab.loaded:
                    self.ctx.lifecycle.wake(tid)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self._apply)

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self.close_stack_picker(animated=False)
        for tid in list(self._in_view):
            card = self.cards.get(tid)
            self._in_view.discard(tid)
            if card is not None:
                card.set_on_screen(False)
            self.ctx.lifecycle.set_in_view(tid, False, False)

    def refresh_visibility(self) -> None:
        self._update_visibility()

    def visible_tab_ids(self) -> list[str]:
        return [t.id for t in self.space.tabs if t.id in self._in_view]

    # --------------------------------------------------------------- cards
    def _add_card(self, tab: Tab) -> WebCard | None:
        ctrl = self.ctx.engine.controller(tab.id)
        if ctrl is None:
            return None
        card = WebCard(self.ctx, tab, ctrl, self.ui, self)
        self.cards[tab.id] = card
        card.header.dragMoved.connect(lambda pos, tid=tab.id: self._on_drag(tid, pos))
        card.header.dragFinished.connect(self._on_drag_end)
        tab.changed.connect(lambda fields, tid=tab.id: self._on_tab_fields(tid, fields))
        card.show()
        card.lower()
        self.minimap.raise_()
        return card

    def _on_tab_fields(self, tab_id: str, fields: frozenset) -> None:
        if fields & {"width", "stack"}:
            self.schedule_layout()
        if fields & {"sleeping", "title"} and self.minimap.isVisible():
            self.minimap.update()

    def _on_tab_added(self, tab: Tab, _index: int, activate: bool) -> None:
        if tab.space_id != self.space.id or tab.id in self.cards:
            return
        card = self._add_card(tab)
        if card is None:
            return
        target = self.targets().get(tab.id, (float(MARGIN), 0.0, 0.0, 1.0))
        self._geo[tab.id] = self._entry_geo(tab.id, target)   # grow in (from the picker, if it came from there)
        first_card = len(self.space.tabs) == 1
        self.request_layout(animated=not first_card)
        if first_card:
            self.scroll_to(0.0, animated=False)
        elif activate:
            self.ensure_visible(tab.id)

    def _on_tab_removed(self, tab: Tab, space: Space) -> None:
        if space.id != self.space.id:
            return
        card = self.cards.pop(tab.id, None)
        self._geo.pop(tab.id, None)
        self._in_view.discard(tab.id)
        if card is not None:
            card.teardown()
        self.request_layout(animated=True)

    def _on_tab_moved(self, tab: Tab, _old: int, _new: int) -> None:
        if tab.space_id == self.space.id:
            self.request_layout(animated=True)

    def _sync_active(self) -> None:
        for tid, card in self.cards.items():
            card.set_active(tid == self.space.active_tab_id and len(self.cards) > 0)

    def _on_active_changed(self, space: Space, tab: Tab | None) -> None:
        if space.id != self.space.id:
            return
        self._sync_active()
        self.minimap.update()

    def _on_selection_changed(self, space: Space) -> None:
        if space.id != self.space.id:
            return
        multi = len(space.selected) > 1
        for tid, card in self.cards.items():
            card.set_selected(tid in space.selected, multi)

    def _on_setting(self, key: str, _v) -> None:
        if key == "canvas.show_minimap":
            self._apply()

    # ----------------------------------------------------------- reordering
    # Dragging a card: by its header, or with Alt held anywhere on it (routed here by the window).
    # The card follows the pointer, the others slide aside to show where it will land, and letting go
    # over a space in the sidebar moves the card to that space.
    def _on_drag(self, tab_id: str, global_pos: QPoint) -> None:
        st = self.ctx.state
        local = self.mapFromGlobal(global_pos)
        content_x = local.x() + self._offset
        g = self._geo.get(tab_id)
        if g is None:
            return
        if self._drag_tab != tab_id:                       # the drag just started
            self.close_stack_picker()
            self._drag_tab = tab_id
            self._drag_grab = content_x - g[0]
            tab = st.tab(tab_id)
            if tab is not None and tab.stack:
                st.unstack(tab_id)      # a dragged card leaves its stack; dropping it on a card stacks it again
        w = g[1]
        self._drag_x = content_x - self._drag_grab
        target = self._stack_target_at(local, tab_id)
        if target != self._stack_target:
            self._stack_target = target
            if target is None:
                self._slot = None
            else:
                column = [t.id for t in st.column_of(target[0])]
                self._slot = (target[0], column.index(target[0]) + (0 if target[1] else 1), "drop")
            self.request_layout(animated=True)
        if target is None:
            self._reorder_by_columns(tab_id, self._drag_x + w / 2)
        sidebar = self.ui.window.sidebar
        self._drop_space = sidebar.drop_target_at(global_pos, exclude=self.space.id)
        edge = 48
        if 0 <= local.y() <= self.height():
            if local.x() < edge:
                self.scroll_by(-24, animated=False)
            elif local.x() > self.width() - edge:
                self.scroll_by(24, animated=False)
        self._apply()

    def _stack_target_at(self, local: QPoint, dragged: str) -> tuple[str, bool] | None:
        """While dragging: the card the dragged one would stack onto, and whether above it. The lower half
        of a card stacks below it, its top fifth above it; the middle reorders columns as usual."""
        if self._stack_target is not None and self._slot_rect.contains(local):
            return self._stack_target                  # over the place that opened for it: keep it
        for tid, card in self.cards.items():
            if tid == dragged or not card.isVisible() or not card.geometry().contains(local):
                continue
            if not self.ctx.state.can_stack_onto(tid) or self.ctx.state.tab(dragged) is None \
                    or self.ctx.state.tab(dragged).pinned:
                return None
            r = card.geometry()
            rel = (local.y() - r.top()) / max(1, r.height())
            if rel >= 0.55:
                return (tid, False)
            if rel <= 0.2:
                return (tid, True)
            return None
        return None

    def _reorder_by_columns(self, tab_id: str, centre: float) -> None:
        """Dragging: move the card past whole columns, never into the middle of one."""
        st = self.ctx.state
        cols = st.columns(self.space)
        cur = next((i for i, c in enumerate(cols) if any(t.id == tab_id for t in c)), -1)
        if cur < 0:
            return
        targets = self.targets()
        new = cur
        for i, col in enumerate(cols):
            if i == cur or col[0].id not in targets:
                continue
            x, cw = targets[col[0].id][:2]
            mid = x + cw / 2
            if i < cur and centre < mid:
                new = min(new, i)
            elif i > cur and centre > mid:
                new = max(new, i)
        if new != cur:
            ref = cols[new][0] if new < cur else cols[new][-1]
            st.move_tab(tab_id, self.space.index_of(ref.id))

    def _on_drag_end(self) -> None:
        tab_id, self._drag_tab = self._drag_tab, None
        target, self._drop_space = self._drop_space, None
        stack, self._stack_target = self._stack_target, None
        self.ui.window.sidebar.clear_drop_target()
        if not tab_id:
            return
        if target:
            self._slot = None
            self.ui.move_tab_to_space(tab_id, target)
            return
        g = self._geo.get(tab_id)
        if g is not None:
            self._geo[tab_id] = (self._drag_x, g[1], 0.0, 1.0)   # settle into its place from where it was dropped
        self._slot = None
        if stack is not None and not self.ctx.state.stack_tab(tab_id, stack[0], above=stack[1]):
            self.ui.toast("That column is full (3 cards at most)", "stack")
        self.request_layout(animated=True)
        self.ensure_visible(tab_id)

    # ---------------------------------------------------------- stack picker
    def open_stack_picker(self, tab_id: str) -> bool:
        """Open the empty place below a card, with what can be stacked there (ui/stack_picker.py)."""
        st = self.ctx.state
        if self._drag_tab or self._solo is not None or not st.can_stack_onto(tab_id):
            return False
        from jbrowser.ui.stack_picker import StackPicker
        self.close_stack_picker(animated=False)
        column = [t.id for t in st.column_of(tab_id)]
        self._slot = (tab_id, column.index(tab_id) + 1, "picker")
        self.picker = StackPicker(self.ctx, self.ui, self, tab_id)
        self.request_layout(animated=True)
        self.ensure_visible(tab_id)
        self.picker.show()
        self.picker.raise_()
        self.picker.focus_input()
        return True

    def close_stack_picker(self, animated: bool = True) -> None:
        picker, self.picker = self.picker, None
        if picker is None:
            return
        picker.hide()
        picker.deleteLater()
        if self._slot is not None and self._slot[2] == "picker":
            self._slot = None
            self.request_layout(animated=animated)

    def finish_stack_picker(self, action) -> None:
        """The picker's choice: the slot closes and ``action`` puts the chosen card there, growing out of
        the slot's place."""
        self._slot_handoff = self._geo.get(SLOT)
        picker, self.picker = self.picker, None
        if picker is not None:
            picker.hide()
            picker.deleteLater()
        self._slot = None
        try:
            action()
        finally:
            self.request_layout(animated=True)
            QTimer.singleShot(0, lambda: setattr(self, "_slot_handoff", None))

    def cancel_drag(self) -> None:
        if self._drag_tab:
            self._drop_space = None
            self._on_drag_end()

    # ---------------------------------------------------------------- paint
    def _empty_rect(self) -> QRect:
        return QRect(self.width() // 2 - 170, self.height() // 2 - 90, 340, 180)

    def mousePressEvent(self, e) -> None:
        self.close_stack_picker()
        if not self.cards and self._empty_rect().contains(e.position().toPoint()):
            self.ui.open_lazy_toolbar("new")
        self.setFocus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        # The canvas background has focus (not a page): arrows navigate spaces and cards.
        key = e.key()
        if e.modifiers() == Qt.KeyboardModifier.NoModifier:
            if key == Qt.Key.Key_Up:
                self.ui.switch_space(-1)
                return
            if key == Qt.Key.Key_Down:
                self.ui.switch_space(1)
                return
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.ui.focus_adjacent(-1 if key == Qt.Key.Key_Left else 1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.ui.focus_active_card()
                return
        super().keyPressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if not self.cards:
            hover = self._empty_rect().contains(e.position().toPoint())
            if hover != self._empty_hover:
                self._empty_hover = hover
                self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
                self.update()

    def _background(self) -> QColor:
        """The window's backdrop layers (base colour, tint) with the canvas tint over them, as one
        colour. The canvas paints every one of its pixels with it (WA_OpaquePaintEvent), so Qt no longer
        repaints the window underneath on every frame of scrolling, which halves the work on large or
        high-DPI screens."""
        th = theme()
        if not th.translucent:
            return th.c("canvas_solid")
        layers = th.backdrop_layers() + [th.c("canvas")]
        key = tuple(c.rgba() for c in layers)
        if key != self._bg_key:
            img = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            for c in layers:
                p.fillRect(0, 0, 1, 1, c)
            p.end()
            self._bg_key, self._bg = key, img.pixelColor(0, 0)
        return QColor(self._bg)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._solo is not None:
            p.fillRect(self.rect(), Qt.GlobalColor.black)
            p.end()
            return
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), self._background())
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        view = QRectF(self.rect()).adjusted(-40, -40, 40, 40)
        base = th.c("shadow")
        dpr = self.devicePixelRatioF()
        for tid, card in self.cards.items():
            if not card.isVisible():
                continue
            g = QRectF(card.geometry())
            if g.intersects(view):
                _paint_shadow(p, g, base, tid == self._drag_tab, dpr)
        if self._slot is not None and self._slot[2] == "drop" and not self._slot_rect.isNull():
            # Where the dragged card will stack: a soft, outlined place in the column.
            r = QRectF(self._slot_rect).adjusted(1, 1, -1, -1)
            path = QPainterPath()
            path.addRoundedRect(r, 10, 10)
            p.fillPath(path, th.accent_alpha(0.12))
            pen = QPen(th.accent_alpha(0.7), 1.6, Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 4])
            p.setPen(pen)
            p.drawPath(path)
            draw_glyph(p, QRectF(r.center().x() - 14, r.center().y() - 26, 28, 28), "stack", th.c("accent"), 18)
            f = p.font()
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.setPen(th.c("text2"))
            p.drawText(QRectF(r.left(), r.center().y() + 4, r.width(), 22), Qt.AlignmentFlag.AlignCenter,
                       "Stack here")
        if not self.cards:
            r = QRectF(self._empty_rect())
            if self._empty_hover:
                path = QPainterPath()
                path.addRoundedRect(r, 18, 18)
                p.fillPath(path, th.c("hover"))
            paint_logo(p, QRectF(r.center().x() - 28, r.top() + 14, 56, 56))
            f = p.font()
            f.setPointSizeF(12.5)
            f.setWeight(QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(th.c("text"))
            title = f"{self.space.icon}  {self.space.name} is empty"
            p.drawText(QRectF(r.left(), r.top() + 80, r.width(), 28), Qt.AlignmentFlag.AlignCenter, title)
            f.setPointSizeF(9.5)
            f.setWeight(QFont.Weight.Normal)
            p.setFont(f)
            p.setPen(th.c("text2"))
            p.drawText(QRectF(r.left(), r.top() + 110, r.width(), 22), Qt.AlignmentFlag.AlignCenter,
                       "Press Ctrl+T or click here to open the Lazy Toolbar")
            if self.space.incognito:
                p.setPen(th.c("text3"))
                p.drawText(QRectF(r.left(), r.top() + 134, r.width(), 22), Qt.AlignmentFlag.AlignCenter,
                           "Incognito: nothing from this space is written to disk")
        p.end()



class SpaceStack(QWidget):
    """Holds one canvas per space and slides between them."""

    def __init__(self, ctx: "AppContext", ui: "BrowserController", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.ui = ui
        self.canvases: dict[str, Canvas] = {}
        self.current_id = ""
        self._anim: QVariantAnimation | None = None
        st = ctx.state
        for sp in st.spaces:
            self._add(sp)
        st.spaceAdded.connect(lambda sp, _i: self._add(sp))
        st.spaceRemoved.connect(self._remove)
        st.activeSpaceChanged.connect(self._on_active_space)
        if st.active_space:
            self._show_immediately(st.active_space.id)

    def _add(self, space: Space) -> None:
        if space.id in self.canvases:
            return
        c = Canvas(self.ctx, space, self.ui, self)
        c.setGeometry(self.rect())
        c.hide()
        self.canvases[space.id] = c

    def _remove(self, space: Space) -> None:
        c = self.canvases.pop(space.id, None)
        if c is not None:
            c.hide()
            c.deleteLater()

    def canvas(self, space_id: str | None = None) -> Canvas | None:
        return self.canvases.get(space_id or self.current_id)

    def current(self) -> Canvas | None:
        return self.canvases.get(self.current_id)

    def _show_immediately(self, space_id: str) -> None:
        for sid, c in self.canvases.items():
            if sid != space_id:
                c.hide()
        c = self.canvases.get(space_id)
        if c:
            c.setGeometry(self.rect())
            c.show()
        self.current_id = space_id
        self._raise_overlays()

    def _on_active_space(self, space: Space, previous: Space | None) -> None:
        new = self.canvases.get(space.id)
        old = self.canvases.get(self.current_id)
        if old is not None and old is not new and old.isVisible():
            # A last picture of the cards being left, for the Gallery's all-spaces view.
            for tid in old.visible_tab_ids():
                card = old.cards.get(tid)
                if card is not None and not card.tab.loading:   # a half-drawn page makes a blank picture
                    card.take_snapshot()
        if new is None or new is old:
            self._show_immediately(space.id)
            return
        spaces = self.ctx.state.spaces
        try:
            direction = 1 if (previous is None or spaces.index(space) > spaces.index(previous)) else -1
        except ValueError:
            direction = 1
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
            for sid, c in self.canvases.items():
                if sid != self.current_id:
                    c.hide()
        self.current_id = space.id
        h = self.height()
        if not motion().enabled or old is None or not self.isVisible():
            self._show_immediately(space.id)
            return
        new.setGeometry(0, direction * h, self.width(), h)
        new.show()
        new.raise_()
        self._raise_overlays()

        def frame(t):
            t = float(t)
            dy = int(round(direction * h * (1 - t)))
            new.move(0, dy)
            old.move(0, dy - direction * h)

        def done():
            old.hide()
            old.setGeometry(self.rect())
            new.setGeometry(self.rect())
            self._anim = None

        anim = QVariantAnimation(self)
        anim.setDuration(motion().ms(260))
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(frame)
        anim.finished.connect(done)
        self._anim = anim
        anim.start()

    def _raise_overlays(self) -> None:
        """Overlays that live in the stack (the Gallery) stay above the canvases."""
        for w in self.children():
            if getattr(w, "stays_on_top", False) and isinstance(w, QWidget) and w.isVisible():
                w.raise_()

    def resizeEvent(self, e) -> None:
        if self._anim is None:
            c = self.current()
            if c:
                c.setGeometry(self.rect())
        super().resizeEvent(e)
