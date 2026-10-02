"""The first-run welcome: a fade-in logo intro, three story slides, setup pages and a
guided tour of the real interface.

Everything is painted on one full-window layer that sits on the Acrylic backdrop (the
browser UI is hidden until the tour), with a single animation clock driving every effect:

* intro     three brand-coloured orbs swirl in and merge; the logo springs out of the
            bloom and floats, then the wordmark letters hop in with a colour wave
* story     three headlines rise word by word with a shimmering brand gradient
* setup     look, search, protection, spaces and finishing touches (changes apply live)
* tour      the browser assembles itself and a spotlight glides between its key parts

The click sound plays on every step forward (not on the first slide, where the intro sound
is still ringing out).
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QElapsedTimer, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QGradient, QImage, QLinearGradient,
                         QPainter, QPainterPath, QPen, QRadialGradient)
from PyQt6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QComboBox, QGraphicsOpacityEffect,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget)

from jbrowser.services.search import ENGINES
from jbrowser.ui.icons import draw_glyph, paint_logo
from jbrowser.ui.sounds import Sounds
from jbrowser.ui.theme import DARK, LIGHT, theme
from jbrowser.ui.widgets import IconButton, TintPicker, ToggleSwitch

if TYPE_CHECKING:
    from jbrowser.ui.window import MainWindow

# Raise this to show the welcome again after an update that it introduces (2: colours and the Gallery).
ONBOARDING_VERSION = 3          # 3: JBrowser 2.0 (stacking, reading mode, the shield in the address bar)
BRAND = ("#5b8cff", "#8a5cff", "#ff5c9d")

# Intro timeline, matched to the intro sound (silence until 0.8 s, main hits at 1.75 s and
# 2.55 s, tail until ~3.9 s): orbs gather from T_FORM, pulse on the first hit and merge into
# the logo at T_LOGO.
T_FORM, T_LOGO, T_WORD, T_END = 0.80, 2.55, 2.95, 4.35

STEPS = ["story0", "story1", "story2", "story3", "look", "search", "shield", "spaces", "touches", "ready"]
LAST_STORY = "story3"
STORY = {
    "story0": ("Welcome to the internet - again.", {"again."},
               "JBrowser rethinks the browser from the ground up: calmer, faster and entirely yours."),
    "story1": ("Your tabs, finally with room to breathe.", {"room", "to", "breathe."},
               "Cards sit side by side on an endless canvas. Slide through them, split them, resize them, "
               "and see your whole day at a glance."),
    "story2": ("Private by design.", {"design."},
               "Trackers, fingerprinting and dangerous sites are stopped before they reach you. "
               "No accounts. No telemetry. Nothing to sell."),
    "story3": ("See everything at once.", {"everything", "at", "once."},
               "The Gallery lays out every card as a live picture, in one space or across all of them. "
               "Click one and you're back in it. Drag cards to rearrange them."),
}
HEADERS = {
    "look": ("Make it yours.", {"yours."}, "Pick how JBrowser looks. Everything here can be changed later in Settings."),
    "search": ("Search your way.", {"way."}, "Choose where your searches go when you type words instead of an address."),
    "shield": ("Choose your shield.", {"shield."}, "Both levels block trackers, fingerprinting and dangerous sites."),
    "spaces": ("A space for every part of your life.", {"life."},
               "Each space keeps its own logins, cookies and cards. Name yours; you can add more later."),
    "touches": ("Finishing touches.", {"touches."}, "A few small choices that make JBrowser feel like home."),
    "ready": ("You're all set.", {"set."}, "Take a one-minute tour of the essentials, or dive straight in."),
}


# ------------------------------------------------------------------ easing helpers
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def seg(t: float, a: float, b: float) -> float:
    return clamp01((t - a) / (b - a)) if b > a else float(t >= a)


def out_cubic(x: float) -> float:
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def out_quint(x: float) -> float:
    x = clamp01(x)
    return 1 - (1 - x) ** 5


def in_out_cubic(x: float) -> float:
    x = clamp01(x)
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def out_back(x: float, s: float = 1.7) -> float:
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_rect(a: QRectF, b: QRectF, t: float) -> QRectF:
    return QRectF(lerp(a.x(), b.x(), t), lerp(a.y(), b.y(), t), lerp(a.width(), b.width(), t),
                  lerp(a.height(), b.height(), t))


def with_alpha(c: QColor | str, a: float) -> QColor:
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, c.alphaF() * a)))
    return c


def display_font(px: float, weight: QFont.Weight = QFont.Weight.Medium) -> QFont:
    fams = set(QFontDatabase.families())
    fam = next((f for f in ("Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI") if f in fams), "Segoe UI")
    f = QFont(fam)
    f.setPixelSize(max(8, int(px)))
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def brand_gradient(x0: float, x1: float, shift: float = 0.0) -> QLinearGradient:
    w = max(1.0, x1 - x0)
    g = QLinearGradient(x0 + shift * w, 0, x1 + shift * w, 0)
    g.setSpread(QGradient.Spread.ReflectSpread)
    g.setColorAt(0.0, QColor(BRAND[0]))
    g.setColorAt(0.5, QColor(BRAND[1]))
    g.setColorAt(1.0, QColor(BRAND[2]))
    return g


# ------------------------------------------------------------------ animated text
class Words:
    """A centred, wrapped phrase whose words rise into place one after another."""

    def __init__(self, text: str, accent: set[str] | None = None):
        self.text = text
        self.words = text.split()
        self.accent = accent or set()

    def layout(self, font: QFont, width: float) -> tuple[list[tuple[int, float, float, float]], float, float]:
        fm = QFontMetricsF(font)
        space = fm.horizontalAdvance(" ")
        line_h = fm.height() * 1.08
        lines: list[list[tuple[int, float]]] = [[]]
        cur = 0.0
        for i, w in enumerate(self.words):
            ww = fm.horizontalAdvance(w)
            if lines[-1] and cur + space + ww > width:
                lines.append([])
                cur = 0.0
            if lines[-1]:
                cur += space
            lines[-1].append((i, ww))
            cur += ww
        out = []
        for li, line in enumerate(lines):
            total = sum(ww for _i, ww in line) + space * (len(line) - 1)
            x = -total / 2
            for i, ww in line:
                out.append((i, x, li * line_h, ww))
                x += ww + space
        return out, line_h * len(lines), fm.ascent()

    def paint(self, p: QPainter, cx: float, top: float, width: float, font: QFont, color: QColor, t: float,
              clock: float, exit: float = 0.0, stagger: float = 0.075, dur: float = 0.8) -> float:
        """Draw at time ``t`` since entry; returns the block height."""
        placed, height, ascent = self.layout(font, width)
        p.setFont(font)
        rise = font.pixelSize() * 0.55
        ex = out_cubic(exit)
        for i, x, y, ww in placed:
            e = out_quint(seg(t, i * stagger, i * stagger + dur))
            alpha = e * (1 - ex)
            if alpha <= 0.002:
                continue
            dx = cx + x - ex * 70
            dy = top + y + ascent + (1 - e) * rise - ex * 10
            word = self.words[i]
            if word in self.accent:
                brush = QBrush(brand_gradient(dx, dx + ww * 1.4, 0.25 * math.sin(clock * 0.8 + i)))
            else:
                brush = QBrush(color)
            if e < 1:                                  # motion blur: two faint trailing copies
                for off, a in ((10 * (1 - e), 0.28), (-5 * (1 - e), 0.16)):
                    p.setOpacity(alpha * a)
                    p.setPen(QPen(brush, 1))
                    p.drawText(QPointF(dx, dy + off), word)
            p.setOpacity(alpha)
            p.setPen(QPen(brush, 1))
            p.drawText(QPointF(dx, dy), word)
        p.setOpacity(1.0)
        return height


def paint_paragraph(p: QPainter, rect: QRectF, text: str, font: QFont, color: QColor, alpha: float,
                    rise: float) -> None:
    if alpha <= 0.002:
        return
    p.setOpacity(alpha)
    p.setFont(font)
    p.setPen(color)
    p.drawText(rect.translated(0, rise), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop |
               Qt.TextFlag.TextWordWrap, text)
    p.setOpacity(1.0)


def paint_glass(p: QPainter, rect: QRectF, radius: float, alpha: float = 1.0, strong: bool = False) -> None:
    """A frosted panel: translucent fill, soft shadow, hairline border and a top highlight."""
    th = theme()
    if alpha <= 0.002:
        return
    p.save()
    p.setOpacity(alpha)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    for spread, a in ((22, 0.05), (12, 0.08), (5, 0.10)):      # soft shadow, outside the panel only
        sp = QPainterPath()
        sp.addRoundedRect(rect.adjusted(-spread, -spread + 8, spread, spread + 10), radius + spread, radius + spread)
        p.fillPath(sp.subtracted(path), QColor(0, 0, 0, int(255 * a)))
    if th.dark:
        fill = QColor(32, 32, 42, 205 if strong else 150)
        edge = QColor(255, 255, 255, 34)
        hi = QColor(255, 255, 255, 22)
    else:
        fill = QColor(255, 255, 255, 225 if strong else 165)
        edge = QColor(0, 0, 0, 26)
        hi = QColor(255, 255, 255, 120)
    if not th.translucent:
        fill.setAlpha(255)
    p.fillPath(path, fill)
    g = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 60))
    g.setColorAt(0, hi)
    g.setColorAt(1, QColor(hi.red(), hi.green(), hi.blue(), 0))
    p.fillPath(path, QBrush(g))
    p.setPen(QPen(edge, 1))
    p.drawPath(path)
    p.restore()


# ------------------------------------------------------------------ setup widgets
class ChoiceTile(QAbstractButton):
    """A selectable card with a title, a short description and an optional painted preview."""

    def __init__(self, title: str, desc: str = "", preview: Callable[[QPainter, QRectF], None] | None = None,
                 badge: str = "", height: int = 150, parent: QWidget | None = None):
        super().__init__(parent)
        self.title, self.desc, self.preview, self.badge = title, desc, preview, badge
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(height)
        self._hover = False
        self._pop = 1.0
        self._pop_timer = QElapsedTimer()
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, on: bool) -> None:
        if on:
            self._pop_timer.start()
            self._pop = 0.0
            QTimer.singleShot(0, self._animate_pop)
        self.update()

    def _animate_pop(self) -> None:
        if not self._pop_timer.isValid():
            return
        self._pop = clamp01(self._pop_timer.elapsed() / 380)
        self.update()
        if self._pop < 1:
            QTimer.singleShot(16, self._animate_pop)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(180, self.minimumHeight())

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bump = 1.0 + 0.035 * math.sin(math.pi * self._pop) if self.isChecked() else 1.0
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        c = r.center()
        r = QRectF(c.x() - r.width() * bump / 2, c.y() - r.height() * bump / 2, r.width() * bump, r.height() * bump)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        base = QColor(255, 255, 255, 18) if th.dark else QColor(0, 0, 0, 10)
        if self._hover:
            base = QColor(255, 255, 255, 30) if th.dark else QColor(0, 0, 0, 18)
        p.fillPath(path, base)
        if self.isChecked():
            p.fillPath(path, th.accent_alpha(0.14))
            p.setPen(QPen(th.c("accent"), 2))
        else:
            p.setPen(QPen(th.c("divider"), 1))
        p.drawPath(path)
        y = r.top() + 12
        if self.preview is not None:
            pr = QRectF(r.left() + 12, y, r.width() - 24, r.height() * 0.5)
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(pr, 9, 9)
            p.setClipPath(clip)
            self.preview(p, pr)
            p.restore()
            y = pr.bottom() + 10
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(th.c("text"))
        p.drawText(QRectF(r.left() + 14, y, r.width() - 28, 22), Qt.AlignmentFlag.AlignLeft |
                   Qt.AlignmentFlag.AlignVCenter, self.title)
        if self.badge:
            bw = QFontMetricsF(f).horizontalAdvance(self.title)
            bf = QFont(self.font())
            bf.setPointSizeF(7.5)
            p.setFont(bf)
            tw = p.fontMetrics().horizontalAdvance(self.badge) + 12
            br = QRectF(r.left() + 14 + bw + 8, y + 3, tw, 17)
            bp = QPainterPath()
            bp.addRoundedRect(br, 8.5, 8.5)
            p.fillPath(bp, th.accent_alpha(0.22))
            p.setPen(th.c("accent"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self.badge)
        if self.desc:
            df = QFont(self.font())
            df.setPointSizeF(8.8)
            p.setFont(df)
            p.setPen(th.c("text2"))
            p.drawText(QRectF(r.left() + 14, y + 24, r.width() - 28, r.bottom() - y - 30),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self.desc)
        if self.isChecked():
            cr = QRectF(r.right() - 30, r.top() + 10, 20, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(th.c("accent"))
            s = out_back(self._pop, 2.2)
            p.drawEllipse(QRectF(cr.center().x() - 10 * s, cr.center().y() - 10 * s, 20 * s, 20 * s))
            draw_glyph(p, cr, "check", th.accent_text(), 10 * max(0.01, s))
        p.end()


def _mini_window(p: QPainter, r: QRectF, tokens: dict, accent: QColor) -> None:
    from jbrowser.ui.theme import parse_color
    p.fillRect(r, parse_color(tokens["window"]))
    side = QRectF(r.left(), r.top(), r.width() * 0.24, r.height())
    p.fillRect(side, parse_color(tokens["sidebar_solid"]))
    for i in range(3):
        row = QRectF(side.left() + 6, side.top() + 10 + i * 12, side.width() - 12, 7)
        p.fillRect(row, with_alpha(parse_color(tokens["text"]), 0.18 if i else 0.30))
    bar = QRectF(side.right() + 8, r.top() + 7, r.width() - side.width() - 16, 8)
    pp = QPainterPath()
    pp.addRoundedRect(bar, 4, 4)
    p.fillPath(pp, parse_color(tokens["card_solid"]))
    cw = (r.width() - side.width() - 22) / 2
    for i in range(2):
        cr = QRectF(side.right() + 8 + i * (cw + 6), bar.bottom() + 7, cw, r.height() - bar.height() - 22)
        cp = QPainterPath()
        cp.addRoundedRect(cr, 4, 4)
        p.fillPath(cp, parse_color(tokens["card_solid"]))
        if i == 0:
            p.setPen(QPen(accent, 1.2))
            p.drawPath(cp)
        p.fillRect(QRectF(cr.left() + 5, cr.top() + 6, cr.width() * 0.6, 4), with_alpha(parse_color(tokens["text"]), 0.25))


def preview_theme(mode: str) -> Callable[[QPainter, QRectF], None]:
    def paint(p: QPainter, r: QRectF) -> None:
        acc = theme().c("accent")
        if mode == "system":
            p.save()
            left = QPainterPath()
            left.moveTo(r.topLeft())
            left.lineTo(QPointF(r.left() + r.width() * 0.62, r.top()))
            left.lineTo(QPointF(r.left() + r.width() * 0.38, r.bottom()))
            left.lineTo(r.bottomLeft())
            left.closeSubpath()
            _mini_window(p, r, LIGHT, acc)
            p.setClipPath(left, Qt.ClipOperation.IntersectClip)
            _mini_window(p, r, DARK, acc)
            p.restore()
        else:
            _mini_window(p, r, DARK if mode == "dark" else LIGHT, acc)
    return paint


def preview_material(kind: str) -> Callable[[QPainter, QRectF], None]:
    def paint(p: QPainter, r: QRectF) -> None:
        dark = theme().dark
        # a pretend desktop behind the window
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#2d5bd7"))
        g.setColorAt(0.5, QColor("#7a3fd1"))
        g.setColorAt(1, QColor("#e2507f"))
        p.fillRect(r, QBrush(g))
        for i, (fx, fy, rad) in enumerate(((0.25, 0.3, 0.35), (0.75, 0.7, 0.3), (0.55, 0.2, 0.2))):
            rg = QRadialGradient(QPointF(r.left() + r.width() * fx, r.top() + r.height() * fy), r.width() * rad)
            rg.setColorAt(0, QColor(255, 255, 255, 110 if i != 1 else 70))
            rg.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(r, QBrush(rg))
        base = QColor(24, 24, 30) if dark else QColor(246, 246, 248)
        if kind == "acrylic":
            base.setAlpha(150)
            p.fillRect(r, base)
            noise = random.Random(7)
            p.setPen(Qt.PenStyle.NoPen)
            for _ in range(140):
                x = r.left() + noise.random() * r.width()
                y = r.top() + noise.random() * r.height()
                p.setBrush(QColor(255, 255, 255, 14))
                p.drawEllipse(QPointF(x, y), 1.0, 1.0)
        elif kind == "mica":
            base.setAlpha(215)
            p.fillRect(r, base)
        else:
            base.setAlpha(255)
            p.fillRect(r, base)
        p.fillRect(QRectF(r.left() + 10, r.top() + 10, r.width() * 0.5, 7), QColor(255, 255, 255, 60) if dark
                   else QColor(0, 0, 0, 40))
    return paint


class SetupPage(QWidget):
    """A page of setup controls shown inside a frosted card."""

    def __init__(self, key: str, parent: QWidget):
        super().__init__(parent)
        self.key = key
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 24, 26, 24)
        self.lay.setSpacing(12)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.hide()

    def section(self, text: str) -> QLabel:
        lab = QLabel(text, self)
        f = lab.font()
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.Medium)
        lab.setFont(f)
        lab.setProperty("muted", True)
        self.lay.addWidget(lab)
        return lab

    def row_of(self, widgets: list[QWidget], stretch: bool = True) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        for w in widgets:
            row.addWidget(w, 1 if stretch else 0)
        self.lay.addLayout(row)
        return row


class SwitchRow(QWidget):
    def __init__(self, title: str, desc: str, checked: bool, on_change: Callable[[bool], None],
                 parent: QWidget | None = None, extra: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = QLabel(title, self)
        t.setProperty("cardtitle", True)
        d = QLabel(desc, self)
        d.setProperty("carddesc", True)
        d.setWordWrap(True)
        text.addWidget(t)
        text.addWidget(d)
        if extra is not None:
            text.addWidget(extra)
        lay.addLayout(text, 1)
        self.switch = ToggleSwitch(checked, self)
        self.switch.toggled.connect(lambda v: on_change(bool(v)))
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)


EMOJI_CHOICES = ["🏠", "💼", "✨", "🎓", "🎮", "🎨", "💰", "🛒", "✈️", "📚", "🧪", "🎵", "❤️", "🌱", "⚽", "🛠️"]


class TourBubble(QWidget):
    """The glass card that explains the highlighted part of the interface."""

    def __init__(self, parent: "Onboarding"):
        super().__init__(parent)
        self.setFixedWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(8)
        self.counter = QLabel(self)
        self.counter.setProperty("hint", True)
        self.title = QLabel(self)
        f = self.title.font()
        f.setPointSizeF(13)
        f.setWeight(QFont.Weight.Medium)
        self.title.setFont(f)
        self.body = QLabel(self)
        self.body.setWordWrap(True)
        self.body.setProperty("carddesc", True)
        lay.addWidget(self.counter)
        lay.addWidget(self.title)
        lay.addWidget(self.body)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.skip = QPushButton("Skip tour", self)
        self.skip.setFlat(True)
        self.back = QPushButton("Back", self)
        self.next = QPushButton("Next", self)
        self.next.setProperty("primary", True)
        for b in (self.skip, self.back, self.next):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.skip)
        row.addStretch(1)
        row.addWidget(self.back)
        row.addWidget(self.next)
        lay.addSpacing(4)
        lay.addLayout(row)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.hide()


# ------------------------------------------------------------------ the overlay
class Onboarding(QWidget):
    finished = pyqtSignal()

    def __init__(self, window: "MainWindow", replay: bool = False):
        host = window.centralWidget()
        super().__init__(host)
        self.win = window
        self.ctx = window.ctx
        self.ui = window.ui
        self.s = self.ctx.settings
        self.replay = replay
        self.sounds = Sounds(self.s, self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(host.rect())
        host.installEventFilter(self)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.phase = "intro"
        self.phase_t0 = 0.0
        self.step = -1
        self.step_t0 = 0.0
        self.prev_step = -1
        self.prev_t0 = 0.0
        self.tour_index = -1
        self._hole_from = QRectF()
        self._hole_to = QRectF()
        self._hole_t0 = 0.0
        self._bubble_from = QPointF()
        self._bubble_to = QPointF()
        self._assemble_t0 = 0.0
        self._fade_t0 = -1.0
        self._aurora = QImage()
        self._aurora_t = -1.0
        self._stars = [(random.random(), random.random(), 0.3 + random.random() * 0.7, random.random() * 6.28)
                       for _ in range(70)]
        self._trackers = [(random.random() * 6.28, random.random()) for _ in range(12)]
        self._sidebar_was_hidden = False
        self._build_chrome()
        self.pages: dict[str, SetupPage] = {}
        self._tops: dict[str, float] = {}
        self._build_pages()
        self.bubble = TourBubble(self)
        self.bubble.next.clicked.connect(self.tour_next)
        self.bubble.back.clicked.connect(self.tour_back)
        self.bubble.skip.clicked.connect(self.finish)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._hide_browser(True)
        self.show()
        self.raise_()
        self.setFocus()
        self.phase = "intro"
        self.phase_t0 = self.now()
        self.sounds.play("intro")
        self.timer.start()
        self._layout_chrome()

    def now(self) -> float:
        return self.clock.elapsed() / 1000.0

    def _hide_browser(self, hide: bool) -> None:
        w = self.win
        if hide:
            self._sidebar_was_hidden = w.sidebar.hidden_mode
            w.sidebar.hide()
            w.right.hide()
        else:
            w.right.show()

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
            self._layout_chrome()
            self._place_pages()
            if self.phase == "tour":
                self._retarget_tour(immediate=True)
        return False

    # ------------------------------------------------------------- chrome
    def _build_chrome(self) -> None:
        self.drag = QWidget(self)
        self.drag.setProperty("dragRegion", True)
        self.min_btn = IconButton("min", "Minimize", self, size=40, glyph_px=9, width=46)
        self.max_btn = IconButton("max", "Maximize", self, size=40, glyph_px=9, width=46)
        self.close_btn = IconButton("close", "Close", self, size=40, glyph_px=9, width=46, variant="close")
        self.min_btn.clicked.connect(lambda: self.win.transition(self.win.showMinimized))
        self.max_btn.clicked.connect(self.ui.toggle_maximize)
        self.close_btn.clicked.connect(self.win.close)
        self.mute_btn = IconButton("volume", "Sound effects on (click to mute)", self, size=34, glyph_px=14)
        self.mute_btn.clicked.connect(self._toggle_sound)
        self._sync_mute()
        self.skip_btn = QPushButton("Skip setup", self)
        self.skip_btn.setFlat(True)
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_btn.clicked.connect(self.skip)
        self.back_btn = QPushButton("Back", self)
        self.next_btn = QPushButton("Next", self)
        self.next_btn.setProperty("primary", True)
        for b in (self.back_btn, self.next_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumWidth(110)
            b.setMinimumHeight(38)
        self.next_btn.setStyleSheet("QPushButton{border-radius:19px;padding:8px 26px;font-size:10.5pt;}")
        self.back_btn.setStyleSheet("QPushButton{border-radius:19px;padding:8px 22px;font-size:10.5pt;}")
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn.clicked.connect(self.go_next)
        self.nav_effect = QGraphicsOpacityEffect(self)
        self.nav_effect.setOpacity(0.0)
        self.nav_box = QWidget(self)
        nl = QHBoxLayout(self.nav_box)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(10)
        nl.addWidget(self.back_btn)
        nl.addWidget(self.next_btn)
        self.nav_box.setGraphicsEffect(self.nav_effect)
        self.nav_box.hide()
        self.skip_btn.hide()

    def _layout_chrome(self) -> None:
        w, h = self.width(), self.height()
        self.close_btn.move(w - 46, 0)
        self.max_btn.move(w - 92, 0)
        self.min_btn.move(w - 138, 0)
        self.drag.setGeometry(0, 0, max(0, w - 140), 40)
        self.mute_btn.move(14, 6)
        self.nav_box.adjustSize()
        self.nav_box.move(w - self.nav_box.width() - 40, h - self.nav_box.height() - 34)
        self.skip_btn.adjustSize()
        self.skip_btn.move(34, h - self.skip_btn.height() - 38)
        for b in (self.min_btn, self.max_btn, self.close_btn, self.mute_btn):
            b.raise_()
        self.max_btn.set_glyph("restore" if self.win.isMaximized() else "max")

    def _toggle_sound(self) -> None:
        on = self.s.toggle("appearance.sounds")
        if not on:
            self.sounds.stop()
        self._sync_mute()

    def _sync_mute(self) -> None:
        on = bool(self.s.get("appearance.sounds"))
        self.mute_btn.set_glyph("volume" if on else "mute")
        self.mute_btn.setToolTip("Sound effects on (click to mute)" if on else "Sound effects off (click to unmute)")

    # ------------------------------------------------------------- setup pages
    def _build_pages(self) -> None:
        s = self.s
        # Look ------------------------------------------------------------------
        pg = SetupPage("look", self)
        pg.section("Theme")
        group = QButtonGroup(pg)
        tiles = []
        for mode, title in (("system", "Match Windows"), ("dark", "Dark"), ("light", "Light")):
            t = ChoiceTile(title, "", preview_theme(mode), height=150, parent=pg)
            t.setChecked(s.get("appearance.theme") == mode)
            t.clicked.connect(lambda _c=False, m=mode: s.set("appearance.theme", m))
            group.addButton(t)
            tiles.append(t)
        pg.row_of(tiles)
        pg.section("Window material")
        group2 = QButtonGroup(pg)
        tiles = []
        for kind, title, desc in (("acrylic", "Acrylic", "Frosted glass that softly blurs your desktop."),
                                  ("mica", "Mica", "A calm tint taken from your wallpaper."),
                                  ("solid", "Solid", "No transparency. Lightest on battery.")):
            t = ChoiceTile(title, desc, preview_material(kind), height=176, parent=pg)
            t.setChecked(s.get("appearance.material") == kind)
            t.clicked.connect(lambda _c=False, k=kind: s.set("appearance.material", k))
            group2.addButton(t)
            tiles.append(t)
        pg.row_of(tiles)
        pg.section("Colour")
        tint = TintPicker(s.get("appearance.tint") or "none", pg, swatch=32, gap=12)
        tint.changed.connect(lambda key: s.set("appearance.tint", key))
        tint_row = QHBoxLayout()
        tint_row.setContentsMargins(0, 0, 0, 0)
        tint_row.addWidget(tint)
        tint_row.addStretch(1)
        pg.lay.addLayout(tint_row)
        tint_hint = QLabel("A gentle tint for the window: soft over Acrylic and Mica, a little stronger with Solid. "
                           "Incognito spaces always stay black.", pg)
        tint_hint.setProperty("hint", True)
        tint_hint.setWordWrap(True)
        pg.lay.addWidget(tint_hint)
        self.pages["look"] = pg
        # Search ----------------------------------------------------------------
        pg = SetupPage("search", self)
        pg.section("Search engine")
        group = QButtonGroup(pg)
        grid = QGridLayout()
        grid.setSpacing(12)
        blurbs = {"google": "The world's most used search.", "duckduckgo": "Private search, no profile.",
                  "bing": "Microsoft's search engine.", "brave": "Independent index, private.",
                  "startpage": "Google results, privately.", "ecosia": "Searches that plant trees.",
                  "kagi": "Premium, ad-free search."}
        for i, (key, (name, _url)) in enumerate(ENGINES.items()):
            t = ChoiceTile(name, blurbs.get(key, ""), None, height=84, parent=pg)
            t.setChecked(s.get("search.engine") == key)
            t.clicked.connect(lambda _c=False, k=key: s.set("search.engine", k))
            group.addButton(t)
            grid.addWidget(t, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        pg.lay.addLayout(grid)
        pg.lay.addSpacing(6)
        pg.lay.addWidget(SwitchRow("Show suggestions while I type",
                                   "Popular searches appear as you type. What you type is sent to Google for this, "
                                   "and never from incognito spaces.", bool(s.get("search.suggestions")),
                                   lambda v: s.set("search.suggestions", v), pg))
        self.pages["search"] = pg
        # Shield ----------------------------------------------------------------
        pg = SetupPage("shield", self)
        group = QButtonGroup(pg)
        strict_now = bool(s.get("privacy.https_upgrade")) and bool(s.get("privacy.block_autoplay"))
        bal = ChoiceTile("Balanced", "Blocks trackers, ads, cryptominers, fingerprinting and dangerous sites, and "
                                     "strips tracking codes from links. Websites work as they should.",
                         None, badge="Recommended", height=150, parent=pg)
        strict = ChoiceTile("Strict", "Everything in Balanced, plus: always try encrypted (HTTPS) connections "
                                      "first and stop videos from playing on their own.",
                            None, height=150, parent=pg)
        bal.setChecked(not strict_now)
        strict.setChecked(strict_now)
        group.addButton(bal)
        group.addButton(strict)
        bal.clicked.connect(lambda: self._protection(False))
        strict.clicked.connect(lambda: self._protection(True))
        pg.row_of([bal, strict])
        pg.lay.addSpacing(4)
        pg.lay.addWidget(SwitchRow("Encrypted DNS with Quad9",
                                   "Hides the sites you look up from your network and refuses known dangerous "
                                   "domains. Turn off to use your network's normal DNS.",
                                   s.get("network.dns_mode") != "system",
                                   lambda v: s.set("network.dns_mode", "quad9" if v else "system"), pg))
        self.pages["shield"] = pg
        # Spaces ----------------------------------------------------------------
        pg = SetupPage("spaces", self)
        for sp in [sp for sp in self.ctx.state.spaces if not sp.incognito][:4]:
            rowbox = QWidget(pg)
            rl = QHBoxLayout(rowbox)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(12)
            emoji = QPushButton(sp.icon, rowbox)
            emoji.setFixedSize(52, 44)
            ef = emoji.font()
            ef.setFamily("Segoe UI Emoji")
            ef.setPointSizeF(16)
            emoji.setFont(ef)
            emoji.setCursor(Qt.CursorShape.PointingHandCursor)
            emoji.setToolTip("Choose an icon")
            emoji.clicked.connect(lambda _c=False, b=emoji, sid=sp.id: self._pick_emoji(b, sid))
            name = QLineEdit(sp.name, rowbox)
            name.setMinimumHeight(40)
            name.setMaxLength(32)
            nf = name.font()
            nf.setPointSizeF(11)
            name.setFont(nf)
            name.textChanged.connect(lambda text, sid=sp.id: self.ctx.state.update_space(sid, name=text.strip() or "Space"))
            dot = QLabel(rowbox)
            dot.setFixedSize(14, 14)
            dot.setStyleSheet(f"background:{sp.color};border-radius:7px;")
            rl.addWidget(emoji)
            rl.addWidget(name, 1)
            rl.addWidget(dot)
            pg.lay.addWidget(rowbox)
        hint = QLabel("Tip: switch spaces with Alt+↑ and Alt+↓, and add new ones with Ctrl+N.", pg)
        hint.setProperty("hint", True)
        pg.lay.addWidget(hint)
        self.pages["spaces"] = pg
        # Finishing touches -----------------------------------------------------------
        pg = SetupPage("touches", self)
        pg.lay.addWidget(SwitchRow("Fluid animations", "Smooth motion everywhere. Turn off for instant changes.",
                                   bool(s.get("appearance.animations")), lambda v: s.set("appearance.animations", v),
                                   pg))
        pg.lay.addWidget(SwitchRow("Reopen my cards at start", "Pick up exactly where you left off.",
                                   bool(s.get("startup.restore_session")),
                                   lambda v: s.set("startup.restore_session", v), pg))
        home_mode = QComboBox(pg)
        home_mode.addItem("Opens the Lazy Toolbar", "lazy")
        home_mode.addItem("Opens a page I choose (set it in Settings)", "url")
        home_mode.setCurrentIndex(home_mode.findData(s.get("toolbar.home_mode") or "lazy"))
        home_mode.currentIndexChanged.connect(lambda _i: s.set("toolbar.home_mode", home_mode.currentData()))
        home_box = QWidget(pg)
        hb = QHBoxLayout(home_box)
        hb.setContentsMargins(0, 4, 0, 0)
        hb.addWidget(home_mode)
        hb.addStretch(1)
        pg.lay.addWidget(SwitchRow("Home button", "Adds a Home button to the ribbon, next to Reload.",
                                   bool(s.get("toolbar.home_button")), lambda v: s.set("toolbar.home_button", v),
                                   pg, extra=home_box))
        pg.lay.addWidget(SwitchRow("Sound effects", "Gentle sounds on this welcome screen.",
                                   bool(s.get("appearance.sounds")),
                                   lambda v: (s.set("appearance.sounds", v), self._sync_mute()), pg))
        self.pages["touches"] = pg
        # Ready -------------------------------------------------------------------------------
        pg = SetupPage("ready", self)
        pg.lay.setContentsMargins(26, 28, 26, 28)
        row_box = QHBoxLayout()
        row_box.setSpacing(14)
        tour = QPushButton("Take the tour", pg)
        tour.setProperty("primary", True)
        go = QPushButton("Start browsing", pg)
        for b in (tour, go):
            b.setMinimumHeight(46)
            b.setMinimumWidth(190)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{border-radius:23px;padding:10px 28px;font-size:11pt;}")
        tour.clicked.connect(lambda: self.begin_assemble(tour=True))
        go.clicked.connect(lambda: self.begin_assemble(tour=False))
        row_box.addStretch(1)
        row_box.addWidget(tour)
        row_box.addWidget(go)
        row_box.addStretch(1)
        pg.lay.addLayout(row_box)
        self.ready_tour_btn = tour
        self.pages["ready"] = pg

    def _protection(self, strict: bool) -> None:
        s = self.s
        for key in ("privacy.block_trackers", "privacy.threat_protection", "privacy.fingerprint_protection",
                    "privacy.strip_tracking", "privacy.block_third_party_cookies"):
            s.set(key, True)
        s.set("privacy.https_upgrade", strict)
        s.set("privacy.block_autoplay", strict)

    def _pick_emoji(self, button: QPushButton, space_id: str) -> None:
        m = QMenu(self)
        for e in EMOJI_CHOICES:
            a = m.addAction(e)
            a.triggered.connect(lambda _c=False, em=e: (button.setText(em),
                                                        self.ctx.state.update_space(space_id, icon=em)))
        m.exec(button.mapToGlobal(QPoint(0, button.height())))

    # ------------------------------------------------------------- navigation
    def key_of(self, step: int) -> str:
        return STEPS[step] if 0 <= step < len(STEPS) else ""

    def go_to(self, step: int, forward: bool = True, sound: bool = True) -> None:
        step = max(0, min(len(STEPS) - 1, step))
        if step == self.step:
            return
        if forward and sound:
            self.sounds.play("click")
        self.prev_step, self.prev_t0 = self.step, self.now()
        self.step, self.step_t0 = step, self.now()
        self.phase = "steps"
        key = self.key_of(step)
        self.back_btn.setVisible(step > 0)
        self.next_btn.setText("Set up JBrowser" if key == LAST_STORY else "Next")
        self.nav_box.setVisible(key != "ready")
        self.skip_btn.setVisible(key != "ready")
        self._layout_chrome()
        prev = self.pages.get(self.key_of(self.prev_step))
        cur = self.pages.get(key)
        if cur is not None:
            cur.show()
            cur.raise_()
        if prev is not None and prev is not cur:
            prev.raise_()
        self._place_pages()
        self.setFocus()

    def go_next(self) -> None:
        if self.phase == "intro":
            self.end_intro()
        elif self.step < len(STEPS) - 1:
            self.go_to(self.step + 1)

    def go_back(self) -> None:
        if self.phase == "steps" and self.step > 0:
            self.go_to(self.step - 1, forward=False)

    def end_intro(self) -> None:
        if self.phase != "intro":
            return
        self.sounds.stop("intro")
        self.nav_box.show()
        self._intro_done_at = self.now()
        self.go_to(0, sound=False)          # the intro sound carries into the first slide

    def skip(self) -> None:
        self.begin_assemble(tour=False)

    def keyPressEvent(self, e) -> None:
        key = e.key()
        focus = QApplication.focusWidget()
        typing = isinstance(focus, QLineEdit)
        if self.phase == "tour":
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self.tour_next()
            elif key == Qt.Key.Key_Left:
                self.tour_back()
            elif key == Qt.Key.Key_Escape:
                self.finish()
            return
        if key == Qt.Key.Key_Escape:
            self.skip()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or (key == Qt.Key.Key_Right and not typing):
            if self.key_of(self.step) == "ready":
                self.begin_assemble(tour=True)
            else:
                self.go_next()
        elif key == Qt.Key.Key_Left and not typing:
            self.go_back()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        if self.phase == "intro" and self.now() - self.phase_t0 > 0.6:
            self.end_intro()
        e.accept()

    # ------------------------------------------------------------- page geometry
    def _content_width(self) -> float:
        return min(780.0, self.width() - 96.0)

    def _header_top(self, key: str = "") -> float:
        return self._tops.get(key, max(70.0, self.height() * 0.11))

    def _place_pages(self) -> None:
        w = self._content_width()
        if not hasattr(self, "_tops"):
            self._tops = {}
        for key, pg in self.pages.items():
            pg.setFixedWidth(int(w))
            pg.adjustSize()
            hh = self._header_height(key)
            block = hh + 22 + pg.height()
            top = max(56.0, (self.height() - 120.0 - block) / 2 + 10)
            self._tops[key] = top
            x = (self.width() - w) / 2
            pg.move(int(x), int(top + hh + 22))

    def _header_height(self, key: str) -> float:
        tf = display_font(self._title_px(True))
        words = Words(HEADERS.get(key, ("", set(), ""))[0])
        _placed, hh, _a = words.layout(tf, self._content_width())
        sub = QFontMetricsF(self._sub_font()).boundingRect(QRectF(0, 0, self._content_width(), 400),
                                                           Qt.TextFlag.TextWordWrap.value,
                                                           HEADERS.get(key, ("", set(), ""))[2])
        return hh + 12 + sub.height()

    def _title_px(self, setup: bool) -> float:
        h = self.height()
        return max(26.0, min(40.0, h * 0.045)) if setup else max(32.0, min(60.0, h * 0.066))

    def _sub_font(self) -> QFont:
        f = display_font(max(14.0, min(18.0, self.height() * 0.019)), QFont.Weight.Normal)
        return f

    # ------------------------------------------------------------- assemble + tour
    def begin_assemble(self, tour: bool) -> None:
        if self.phase in ("assemble", "tour", "closing"):
            return
        self.sounds.play("click")
        self.sounds.stop("intro")
        self.phase = "assemble"
        self._assemble_t0 = self.now()
        self._want_tour = tour
        for pg in self.pages.values():
            pg.hide()
        self.nav_box.hide()
        self.skip_btn.hide()
        self.mute_btn.hide()
        for b in (self.min_btn, self.max_btn, self.close_btn):
            b.hide()
        self.drag.hide()
        w = self.win
        w.right.show()
        sb = w.sidebar
        if tour and sb.hidden_mode:
            sb.set_collapsed(False)              # shown for the tour, restored afterwards
        if not sb.hidden_mode:
            sb._set_w(0.0)
            sb.show()
            sb.set_collapsed(False)
        self.s.set("onboarding.version", ONBOARDING_VERSION)

    TOUR = [
        ("section", "Spaces", "Each space is its own world with separate logins, cookies and cards. "
                              "Switch with a click, or with Alt+↑ and Alt+↓."),
        ("favourites", "Favourites", "Right-click any card and choose Add to favourites to pin a site up here, "
                                     "above your spaces. It works in every space."),
        ("pill", "The Lazy Toolbar", "Click the address bar or press Ctrl+T for a new card. Ctrl+K searches your "
                                     "cards, history, bookmarks and commands."),
        ("canvas", "Your canvas", "Cards sit side by side. Drag a card by its title bar (or hold Alt and drag "
                                  "anywhere on it) to move it. Hold Alt and scroll to slide, and keep scrolling past "
                                  "either end to add a card there."),
        ("gallery", "The Gallery", "See every card at a glance, in this space or all of them (Ctrl+Shift+G). Click "
                                   "a card to jump to it, or drag it to another space."),
        ("list", "Cards in this space", "Pinned cards stay on top, and the New card row is always there. Drag a card "
                                        "to reorder it, or onto a space to move it. Right-click to pin it or add it to "
                                        "favourites."),
        ("stack", "Stack cards", "Put up to three cards on top of each other in one column: drag a card onto "
                                 "the lower part of another, or press this button. Right-click it for layouts."),
        ("reading", "Reading mode", "On an article, this shows just the text and pictures, without the clutter "
                                    "(F9). JBrowser suggests it once when you're reading."),
        ("archive", "The Archive", "Closed a card by mistake? It waits here for 48 hours. Ctrl+Shift+T brings "
                                   "back the most recent one."),
        ("shield", "Protection", "Trackers, fingerprinting and dangerous sites are blocked. Click the shield in the "
                                 "address bar to see what was stopped on a page."),
        ("logo", "Settings", "The logo opens Settings. Press Ctrl+/ whenever you want to see every shortcut."),
    ]

    def _target_widget(self, name: str) -> QWidget | None:
        w = self.win
        sb = w.sidebar
        return {"section": sb.section, "favourites": sb.favourites if sb.favourites.isVisible() else sb.spaces_label,
                "pill": w.titlebar.pill, "canvas": w.stack, "gallery": w.titlebar.gallery_btn,
                "list": sb.list, "archive": sb.archive_btn, "stack": w.titlebar.stack_btn,
                "reading": w.titlebar.reading_btn, "shield": w.titlebar.pill, "logo": sb.header.logo}.get(name)

    def _target_rect(self, name: str) -> QRectF:
        wid = self._target_widget(name)
        if wid is None or not wid.isVisible():
            return QRectF(self.width() / 2 - 60, self.height() / 2 - 40, 120, 80)
        tl = self.mapFromGlobal(wid.mapToGlobal(QPoint(0, 0)))     # not an ancestor: go via global
        r = QRectF(tl.x(), tl.y(), wid.width(), wid.height())
        if name == "shield":                                       # the shield inside the address bar
            r = wid._shield_rect().translated(tl.x(), tl.y())
        if name == "list":
            r.setHeight(min(r.height(), 180))
        if name == "canvas":
            r = r.adjusted(14, 12, -14, -26)
        pad = 8 if name not in ("canvas",) else 0
        return r.adjusted(-pad, -pad, pad, pad).intersected(QRectF(self.rect()).adjusted(3, 3, -3, -3))

    def start_tour(self) -> None:
        self.phase = "tour"
        self.tour_index = -1
        full = QRectF(self.rect()).adjusted(-40, -40, 40, 40)
        self._hole_to = full
        self.bubble.show()
        self.bubble.raise_()
        self.tour_go(0, sound=False)

    def tour_go(self, index: int, sound: bool = True) -> None:
        index = max(0, min(len(self.TOUR) - 1, index))
        if sound:
            self.sounds.play("click")
        self.tour_index = index
        name, title, body = self.TOUR[index]
        cur = self._current_hole()
        self._hole_from = cur
        self._hole_to = self._target_rect(name)
        self._hole_t0 = self.now()
        b = self.bubble
        b.counter.setText(f"{index + 1} of {len(self.TOUR)}")
        b.title.setText(title)
        b.body.setText(body)
        b.back.setVisible(index > 0)
        b.next.setText("Start browsing" if index == len(self.TOUR) - 1 else "Next")
        b.adjustSize()
        self._bubble_from = QPointF(b.pos()) if b.isVisible() and index > 0 else self._bubble_anchor(self._hole_to)
        self._bubble_to = self._bubble_anchor(self._hole_to)
        self.setFocus()

    def _retarget_tour(self, immediate: bool = False) -> None:
        if self.tour_index < 0:
            return
        name = self.TOUR[self.tour_index][0]
        self._hole_to = self._target_rect(name)
        self._bubble_to = self._bubble_anchor(self._hole_to)
        if immediate:
            self._hole_from = self._hole_to
            self._bubble_from = self._bubble_to

    def _bubble_anchor(self, hole: QRectF) -> QPointF:
        b = self.bubble
        bw, bh = b.width(), max(b.sizeHint().height(), b.height())
        W, H = self.width(), self.height()
        gap = 18
        candidates = [
            QPointF(hole.right() + gap, hole.top()),                       # right
            QPointF(hole.left(), hole.bottom() + gap),                     # below
            QPointF(hole.left() - bw - gap, hole.top()),                   # left
            QPointF(hole.left(), hole.top() - bh - gap),                   # above
        ]
        if hole.width() > W * 0.5 and hole.height() > H * 0.5:           # big targets: inside, bottom-right
            candidates.insert(0, QPointF(hole.right() - bw - 28, hole.bottom() - bh - 28))
        for c in candidates:
            if c.x() >= 12 and c.y() >= 12 and c.x() + bw <= W - 12 and c.y() + bh <= H - 12:
                return c
        return QPointF(max(12.0, min(W - bw - 12.0, hole.center().x() - bw / 2)),
                       max(12.0, min(H - bh - 12.0, hole.bottom() + gap)))

    def _current_hole(self) -> QRectF:
        if self._hole_from.isNull():
            return QRectF(self._hole_to)
        e = out_cubic(seg(self.now(), self._hole_t0, self._hole_t0 + 0.55))
        return lerp_rect(self._hole_from, self._hole_to, e)

    def tour_next(self) -> None:
        if self.tour_index >= len(self.TOUR) - 1:
            self.sounds.play("click")
            self.finish()
        else:
            self.tour_go(self.tour_index + 1)

    def tour_back(self) -> None:
        if self.tour_index > 0:
            self.tour_go(self.tour_index - 1, sound=False)

    def finish(self) -> None:
        if self.phase == "closing":
            return
        if self.phase not in ("assemble", "tour"):
            self.begin_assemble(tour=False)
        self.s.set("onboarding.version", ONBOARDING_VERSION)
        self.phase = "closing"
        self._fade_t0 = self.now()
        self.bubble.hide()

    def _close_now(self) -> None:
        self.timer.stop()
        sb = self.win.sidebar
        if self._sidebar_was_hidden and not sb.hidden_mode:
            sb.set_collapsed(True)
        self.parentWidget().removeEventFilter(self)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ------------------------------------------------------------- tick
    def _tick(self) -> None:
        now = self.now()
        if self.phase == "intro" and now - self.phase_t0 >= T_END:
            self.end_intro()
        if self.phase == "assemble" and now - self._assemble_t0 >= 0.85:
            if getattr(self, "_want_tour", False):
                self.start_tour()
            else:
                self.phase = "closing"
                self._fade_t0 = now - 0.45        # the assemble fade already did most of the work
        if self.phase == "closing" and now - self._fade_t0 >= 0.5:
            self._close_now()
            return
        # page transitions (opacity + slide)
        if self.phase == "steps":
            cur_key = self.key_of(self.step)
            prev_key = self.key_of(self.prev_step)
            base_x = (self.width() - self._content_width()) / 2
            for key, pg in self.pages.items():
                if key == cur_key:
                    e = out_cubic(seg(now, self.step_t0 + 0.18, self.step_t0 + 0.75))
                    pg.effect.setOpacity(e)
                    direction = 1 if self.step >= self.prev_step else -1
                    pg.move(int(base_x + (1 - e) * 60 * direction), pg.y())
                    if not pg.isVisible():
                        pg.show()
                elif key == prev_key:
                    x = out_cubic(seg(now, self.prev_t0, self.prev_t0 + 0.3))
                    pg.effect.setOpacity(1 - x)
                    direction = -1 if self.step >= self.prev_step else 1
                    pg.move(int(base_x + x * 60 * direction), pg.y())
                    if x >= 1:
                        pg.hide()
                elif pg.isVisible():
                    pg.hide()
            self.nav_effect.setOpacity(out_cubic(seg(now, getattr(self, "_intro_done_at", 0.0),
                                                     getattr(self, "_intro_done_at", 0.0) + 0.6)))
        if self.phase == "tour":
            e = out_cubic(seg(now, self._hole_t0, self._hole_t0 + 0.55))
            pos = QPointF(lerp(self._bubble_from.x(), self._bubble_to.x(), e),
                          lerp(self._bubble_from.y(), self._bubble_to.y(), e))
            self.bubble.move(int(pos.x()), int(pos.y()))
            self.bubble.effect.setOpacity(out_cubic(seg(now, self._hole_t0 + 0.12, self._hole_t0 + 0.5)))
        self.update()

    # ------------------------------------------------------------- painting
    def _aurora_image(self, t: float) -> QImage:
        """The slowly drifting colour field, rendered small and scaled up (it is all blur)."""
        if self._aurora_t >= 0 and t - self._aurora_t < 1 / 30 and not self._aurora.isNull():
            return self._aurora
        w = max(16, self.width() // 10)
        h = max(16, self.height() // 10)
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = theme().dark
        blobs = (
            (0.28 + 0.10 * math.sin(t * 0.21), 0.34 + 0.10 * math.cos(t * 0.17), 0.62, BRAND[0]),
            (0.72 + 0.09 * math.cos(t * 0.19 + 1.3), 0.30 + 0.11 * math.sin(t * 0.23 + 0.4), 0.55, BRAND[1]),
            (0.52 + 0.14 * math.sin(t * 0.15 + 2.1), 0.78 + 0.07 * math.cos(t * 0.21 + 1.0), 0.60, BRAND[2]),
        )
        for fx, fy, rad, col in blobs:
            g = QRadialGradient(QPointF(w * fx, h * fy), max(w, h) * rad)
            c = QColor(col)
            c.setAlphaF(0.34 if dark else 0.22)
            g.setColorAt(0.0, c)
            c2 = QColor(col)
            c2.setAlphaF(0.0)
            g.setColorAt(1.0, c2)
            p.fillRect(QRectF(0, 0, w, h), QBrush(g))
        p.end()
        self._aurora = img
        self._aurora_t = t
        return img

    def _paint_backdrop(self, p: QPainter, strength: float, t: float) -> None:
        th = theme()
        if strength <= 0.001:
            return
        p.save()
        p.setOpacity(strength)
        if not th.translucent:
            p.fillRect(self.rect(), th.c("window"))
        tint = QColor(8, 8, 16, 120) if th.dark else QColor(250, 250, 255, 110)
        p.fillRect(self.rect(), tint)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(self.rect()), self._aurora_image(t))
        p.restore()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        now = self.now()
        if self.phase == "intro":
            t = now - self.phase_t0
            self._paint_backdrop(p, out_cubic(seg(t, 0.0, 0.8)), now)
            self._paint_intro(p, t, now)
        elif self.phase == "steps":
            self._paint_backdrop(p, 1.0, now)
            self._paint_steps(p, now)
        elif self.phase == "assemble":
            k = out_cubic(seg(now, self._assemble_t0, self._assemble_t0 + 0.8))
            self._paint_backdrop(p, 1 - k, now)
            if getattr(self, "_want_tour", False):
                p.fillRect(self.rect(), QColor(0, 0, 0, int(118 * k)))
        elif self.phase == "tour":
            self._paint_tour(p, now, 1.0)
        elif self.phase == "closing":
            k = out_cubic(seg(now, self._fade_t0, self._fade_t0 + 0.5))
            if self.tour_index >= 0:
                self._paint_tour(p, now, 1 - k)
            else:
                self._paint_backdrop(p, max(0.0, 1 - k) * 0.1, now)
        self._paint_dots(p, now)
        p.end()

    # intro ----------------------------------------------------------------------------------------
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() * 0.44)

    def _logo_size(self) -> float:
        return max(84.0, min(150.0, self.height() * 0.16))

    def _paint_intro(self, p: QPainter, t: float, clock: float) -> None:
        th = theme()
        c = self._center()
        W = self.width()
        size = self._logo_size()
        # 1. three brand-coloured orbs drift in on a lazy spiral, pulse on the sound's first hit,
        #    then merge where the logo will appear
        if T_FORM - 0.3 <= t < T_LOGO + 0.15:
            self._paint_orbs(p, t, c, size)
        # 2. the merge: a soft bloom and a shower of sparkles
        if t >= T_LOGO - 0.05:
            self._paint_burst(p, t, c, size)
        # 3. the logo springs out of the bloom and then floats gently
        self._paint_logo_mark(p, t, clock, float_amp=3.0)
        # 4. wordmark: letters hop in one after another with a travelling colour wave
        if t >= T_WORD:
            font = display_font(max(26.0, size * 0.36), QFont.Weight.Medium)
            fm = QFontMetricsF(font)
            text = "JBrowser"
            total = fm.horizontalAdvance(text) + 2 * (len(text) - 1)
            x = c.x() - total / 2
            y = c.y() + size * 0.62 + fm.ascent() + 8
            p.setFont(font)
            for i, ch in enumerate(text):
                k = seg(t, T_WORD + i * 0.055, T_WORD + i * 0.055 + 0.62)
                if k <= 0:
                    x += fm.horizontalAdvance(ch) + 2
                    continue
                hop = math.sin(math.pi * clamp01(k * 1.25)) * 16 * (1 - k)      # a little jump
                sc = out_back(k, 2.4)
                wave = clamp01(1 - abs((t - T_WORD - 0.35) * 2.2 - i * 0.28))   # colour sweeps across
                cw = fm.horizontalAdvance(ch)
                p.save()
                p.translate(x + cw / 2, y - fm.ascent() * 0.35 - hop + (1 - out_cubic(k)) * 14)
                p.scale(max(0.01, sc), max(0.01, sc))
                p.setOpacity(out_cubic(k))
                if i == 0 or wave > 0.02:
                    brush = QBrush(brand_gradient(-cw, cw * 2, 0.3 * math.sin(clock * 1.3 + i)))
                    if i != 0:
                        p.setOpacity(out_cubic(k) * wave)
                        p.setPen(QPen(brush, 1))
                        p.drawText(QPointF(-cw / 2, fm.ascent() * 0.35), ch)
                        p.setOpacity(out_cubic(k) * (1 - wave))
                        brush = QBrush(th.c("text"))
                else:
                    brush = QBrush(th.c("text"))
                p.setPen(QPen(brush, 1))
                p.drawText(QPointF(-cw / 2, fm.ascent() * 0.35), ch)
                p.restore()
                x += cw + 2
            hint_e = out_cubic(seg(t, 3.55, 4.1))
            if hint_e > 0:
                hf = display_font(13, QFont.Weight.Normal)
                hf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0 + 3.0 * (1 - hint_e))
                p.setFont(hf)
                p.setOpacity(hint_e * 0.75)
                p.setPen(th.c("text2"))
                p.drawText(QRectF(0, y + 30 + (1 - hint_e) * 8, W, 24), Qt.AlignmentFlag.AlignHCenter, "Welcome")
                p.setOpacity(1.0)

    def _orb_pos(self, i: int, t: float, c: QPointF, size: float) -> tuple[QPointF, float]:
        """Where orb ``i`` is at time ``t``: a shrinking, speeding-up spiral into the centre."""
        k = in_out_cubic(seg(t, T_FORM - 0.3, T_LOGO))
        radius = size * (2.3 - 2.3 * k)
        ang = i * 2.0944 + 1.1 + (t - T_FORM) * (1.6 + 3.2 * k)
        return QPointF(c.x() + math.cos(ang) * radius, c.y() + math.sin(ang) * radius * 0.82), k

    def _paint_orbs(self, p: QPainter, t: float, c: QPointF, size: float) -> None:
        appear = out_cubic(seg(t, T_FORM - 0.3, T_FORM + 0.5))
        vanish = 1 - out_cubic(seg(t, T_LOGO - 0.08, T_LOGO + 0.15))
        pulse = 1 + 0.45 * math.exp(-((t - 1.75) / 0.12) ** 2)          # the sound's first hit
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            col = QColor(BRAND[i])
            n = 18
            for j in range(n - 1, -1, -1):                               # comet trail, oldest first
                tt = t - j * 0.018
                if tt < T_FORM - 0.3:
                    continue
                pos, k = self._orb_pos(i, tt, c, size)
                r = size * (0.085 + 0.04 * (1 - k)) * (1 - j * 0.042) * (pulse if j == 0 else 1)
                a = appear * vanish * ((1 - j / n) ** 1.8) * (1.0 if j == 0 else 0.45)
                g = QRadialGradient(pos, r * 2.6)
                core = QColor(255, 255, 255) if j == 0 else col                # only the head has a hot core
                g.setColorAt(0.0, with_alpha(core, 0.9 * a))
                g.setColorAt(0.25, with_alpha(col, 0.9 * a))
                g.setColorAt(1.0, with_alpha(col, 0.0))
                p.setBrush(QBrush(g))
                p.drawEllipse(pos, r * 2.6, r * 2.6)
        p.restore()

    def _paint_burst(self, p: QPainter, t: float, c: QPointF, size: float) -> None:
        k = seg(t, T_LOGO - 0.05, T_LOGO + 0.9)
        if k >= 1:
            return
        p.save()
        bloom = QRadialGradient(c, size * (0.6 + 1.6 * out_cubic(k)))
        bloom.setColorAt(0, with_alpha(QColor(255, 255, 255), 0.55 * (1 - k) ** 2))
        bloom.setColorAt(0.4, with_alpha(QColor(BRAND[1]), 0.35 * (1 - k)))
        bloom.setColorAt(1, with_alpha(QColor(BRAND[2]), 0.0))
        rad = size * 2.2
        p.fillRect(QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2), QBrush(bloom))
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(18):                                              # sparkles fly out and fade
            ang = j * 0.349 + 0.2 * math.sin(j * 7.1)
            speed = size * (1.1 + 0.9 * ((j * 37) % 7) / 7)
            d = speed * out_cubic(k)
            pos = QPointF(c.x() + math.cos(ang) * d, c.y() + math.sin(ang) * d * 0.85 + 30 * k * k)
            p.setBrush(with_alpha(QColor(BRAND[j % 3]) if j % 4 else QColor(255, 255, 255), 0.9 * (1 - k)))
            r = 2.6 * (1 - k * 0.6)
            p.drawEllipse(pos, r, r)
        p.restore()

    def _paint_logo_mark(self, p: QPainter, t: float, clock: float, center: QPointF | None = None,
                         size: float | None = None, alpha: float = 1.0, float_amp: float = 0.0) -> None:
        c = center or self._center()
        size = size or self._logo_size()
        k = seg(t, T_LOGO - 0.08, T_LOGO + 0.75)
        fade = out_cubic(seg(t, T_LOGO - 0.08, T_LOGO + 0.3))
        a = fade * alpha
        if a <= 0.002:
            return
        s = 0.35 + 0.65 * out_back(k, 2.1)                 # springs past full size and settles
        tilt = -14.0 * (1 - out_cubic(k))                  # unwinds from a small twist
        if float_amp:
            c = QPointF(c.x(), c.y() + math.sin(clock * 1.6) * float_amp * out_cubic(seg(t, T_LOGO + 0.6, T_LOGO + 1.4)))
        g = QRadialGradient(c, size * 1.8)
        g.setColorAt(0, with_alpha(QColor(BRAND[1]), 0.30 * a))
        g.setColorAt(0.5, with_alpha(QColor(BRAND[0]), 0.12 * a))
        g.setColorAt(1, with_alpha(QColor(BRAND[2]), 0.0))
        p.fillRect(QRectF(c.x() - size * 1.8, c.y() - size * 1.8, size * 3.6, size * 3.6), QBrush(g))
        d = size * max(0.05, s)
        p.save()
        p.setOpacity(a)
        p.translate(c)
        p.rotate(tilt)
        paint_logo(p, QRectF(-d / 2, -d / 2, d, d))
        # a sheen that sweeps across once, after the logo lands
        sweep = seg(t, T_LOGO + 0.45, T_LOGO + 1.3)
        if 0 < sweep < 1:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(-d / 2, -d / 2, d, d), d * 0.26, d * 0.26)
            p.setClipPath(clip)
            sx = -d + sweep * d * 2
            sg = QLinearGradient(sx - d * 0.3, 0, sx + d * 0.3, 0)
            sg.setColorAt(0, QColor(255, 255, 255, 0))
            sg.setColorAt(0.5, QColor(255, 255, 255, 120))
            sg.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(-d / 2, -d / 2, d, d), QBrush(sg))
        p.restore()

    # story + setup ------------------------------------------------------------------------------
    def _paint_steps(self, p: QPainter, now: float) -> None:
        cur = self.key_of(self.step)
        prev = self.key_of(self.prev_step)
        t_cur = now - self.step_t0
        if prev and prev != cur:
            ex = seg(now, self.prev_t0, self.prev_t0 + 0.32)
            if ex < 1:
                self._paint_step(p, prev, 10.0, now, exit=ex)
        # logo mark: flies up from the intro to sit above the story slides
        leaving = prev.startswith("story") and not cur.startswith("story")
        if cur.startswith("story") or leaving:
            intro_end = getattr(self, "_intro_done_at", now - 10)
            k = in_out_cubic(seg(now, intro_end, intro_end + 0.75))
            big = self._logo_size()
            small = 46.0
            cen = QPointF(self.width() / 2, lerp(self._center().y(), self.height() * 0.1 + small / 2, k))
            fade = 1.0 - out_cubic(seg(now, self.step_t0, self.step_t0 + 0.35)) if leaving else 1.0
            if fade > 0.002:
                self._paint_logo_mark(p, T_LOGO + 5, now, cen, lerp(big, small, k), fade)
        self._paint_step(p, cur, t_cur, now, exit=0.0)

    def _paint_step(self, p: QPainter, key: str, t: float, now: float, exit: float) -> None:
        th = theme()
        W, H = self.width(), self.height()
        if key.startswith("story"):
            head, accent, sub = STORY[key]
            fade_in = 0.2 if key != "story0" else 0.45
            self._paint_visual(p, key, t, now, (1 - out_cubic(exit)) * out_cubic(seg(t, 0.0, 0.8)))
            font = display_font(self._title_px(False), QFont.Weight.Medium)
            top = H * 0.56
            width = min(W - 120.0, 900.0)
            hh = Words(head, accent).paint(p, W / 2, top, width, font, th.c("text"), t - fade_in, now, exit)
            sf = self._sub_font()
            e = out_cubic(seg(t, fade_in + 0.45, fade_in + 1.2)) * (1 - out_cubic(exit))
            paint_paragraph(p, QRectF((W - min(W - 120.0, 680.0)) / 2, top + hh + 18, min(W - 120.0, 680.0), 120),
                            sub, sf, th.c("text2"), e, (1 - e) * 14 - exit * 6)
            return
        if key in HEADERS:
            head, accent, sub = HEADERS[key]
            font = display_font(self._title_px(True), QFont.Weight.Medium)
            top = self._header_top(key)
            width = self._content_width()
            hh = Words(head, accent).paint(p, W / 2, top, width, font, th.c("text"), t, now, exit)
            e = out_cubic(seg(t, 0.25, 0.9)) * (1 - out_cubic(exit))
            paint_paragraph(p, QRectF((W - width) / 2, top + hh + 12, width, 80), sub, self._sub_font(),
                            th.c("text2"), e, (1 - e) * 10)
            pg = self.pages.get(key)
            if pg is not None and pg.isVisible() and key != "ready":
                a = pg.effect.opacity()
                paint_glass(p, QRectF(pg.geometry()), 20, a)

    def _paint_visual(self, p: QPainter, key: str, t: float, now: float, alpha: float) -> None:
        if alpha <= 0.002:
            return
        W, H = self.width(), self.height()
        area = QRectF(W * 0.18, H * 0.2, W * 0.64, H * 0.3)
        th = theme()
        p.save()
        p.setOpacity(alpha)
        if key == "story0":
            # motes of light drifting upward
            for i, (fx, fy, sp, ph) in enumerate(self._stars):
                y = (fy - (now * 0.02 * sp)) % 1.0
                x = fx + 0.01 * math.sin(now * 0.5 + ph)
                tw = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 1.7 + ph))
                col = QColor(BRAND[i % 3]) if i % 4 == 0 else (QColor(255, 255, 255) if th.dark else QColor(60, 70, 110))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(col, 0.55 * tw))
                p.drawEllipse(QPointF(x * W, y * H), 1.2 + sp, 1.2 + sp)
        elif key == "story1":
            # a miniature canvas: cards glide past, one of them resizing like Alt+1…9
            n = 7
            base_w = min(220.0, area.width() / 4.6)
            gap = 18
            card_h = min(area.height() - 16, base_w * 0.78)
            widths = [base_w * (1.0 + (0.5 * (0.5 + 0.5 * math.sin(now * 0.9)) if i == 3 else 0.0)) for i in range(n)]
            total = sum(widths) + gap * n
            off = (now * 34) % total
            x = W / 2 - total / 2 - off
            for i in range(n * 2):
                idx = i % n
                cw = widths[idx]
                cr = QRectF(x, area.center().y() - card_h / 2, cw, card_h)
                x += cw + gap
                dist = abs(cr.center().x() - W / 2) / (W * 0.36)
                if dist >= 1.0:
                    continue
                depth = (1.0 - dist) ** 1.4
                i = idx
                path = QPainterPath()
                path.addRoundedRect(cr, 12, 12)
                p.setOpacity(alpha * depth)
                fill = QColor(255, 255, 255, 34) if th.dark else QColor(255, 255, 255, 190)
                p.fillPath(path, fill)
                if i == 3:
                    p.setPen(QPen(with_alpha(th.c("accent"), 0.9), 1.6))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 40) if th.dark else QColor(0, 0, 0, 30), 1))
                p.drawPath(path)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(QColor(BRAND[i % 3]), 0.8 * max(0.35, depth)))
                p.drawEllipse(QPointF(cr.left() + 16, cr.top() + 16), 5, 5)
                line = QColor(255, 255, 255, 40) if th.dark else QColor(0, 0, 0, 30)
                for j in range(4):
                    lw = cr.width() * (0.7 - 0.12 * j)
                    p.fillRect(QRectF(cr.left() + 14, cr.top() + 34 + j * 14, lw, 6), line)
        elif key == "story2":
            # a shield draws itself; trackers fly in and bounce off
            c = QPointF(W / 2, area.center().y())
            s = min(area.height() * 0.9, 190.0)
            shield = QPainterPath()
            shield.moveTo(c.x(), c.y() - s * 0.5)
            shield.cubicTo(c.x() + s * 0.2, c.y() - s * 0.4, c.x() + s * 0.34, c.y() - s * 0.42, c.x() + s * 0.4,
                           c.y() - s * 0.36)
            shield.cubicTo(c.x() + s * 0.42, c.y() + s * 0.05, c.x() + s * 0.3, c.y() + s * 0.34, c.x(), c.y() + s * 0.5)
            shield.cubicTo(c.x() - s * 0.3, c.y() + s * 0.34, c.x() - s * 0.42, c.y() + s * 0.05, c.x() - s * 0.4,
                           c.y() - s * 0.36)
            shield.cubicTo(c.x() - s * 0.34, c.y() - s * 0.42, c.x() - s * 0.2, c.y() - s * 0.4, c.x(), c.y() - s * 0.5)
            draw = out_cubic(seg(t, 0.1, 1.3))
            g = QLinearGradient(c.x(), c.y() - s / 2, c.x(), c.y() + s / 2)
            g.setColorAt(0, with_alpha(QColor(BRAND[0]), 0.30 * draw))
            g.setColorAt(1, with_alpha(QColor(BRAND[1]), 0.12 * draw))
            p.fillPath(shield, QBrush(g))
            pen = QPen(QBrush(brand_gradient(c.x() - s / 2, c.x() + s / 2, 0.3 * math.sin(now))), 3.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            length = shield.length()
            pen.setDashPattern([max(0.01, length * draw / 3.0), 1e4])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(shield)
            check = seg(t, 1.1, 1.6)
            if check > 0:
                cp = QPainterPath()
                cp.moveTo(c.x() - s * 0.14, c.y())
                cp.lineTo(c.x() - s * 0.03, c.y() + s * 0.11)
                cp.lineTo(c.x() + s * 0.17, c.y() - s * 0.12)
                cpen = QPen(th.c("text"), 3.2)
                cpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                cpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                cpen.setDashPattern([max(0.01, cp.length() * out_cubic(check) / 3.2), 1e4])
                p.setPen(cpen)
                p.drawPath(cp)
            # trackers
            for i, (ang, ph) in enumerate(self._trackers):
                cyc = ((now * 0.35) + ph) % 1.0
                far = s * 1.6
                near = s * 0.55
                if cyc < 0.7:
                    k = cyc / 0.7
                    dist = lerp(far, near, k * k)
                    a = min(1.0, k * 3)
                else:
                    k = (cyc - 0.7) / 0.3
                    dist = near + k * s * 0.5
                    a = 1 - k
                x = c.x() + math.cos(ang) * dist
                y = c.y() + math.sin(ang) * dist * 0.62
                col = QColor("#ff6b6b") if i % 3 else QColor("#ffb74d")
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(col, 0.85 * a * draw))
                p.drawEllipse(QPointF(x, y), 4.2, 4.2)
                if cyc >= 0.7:
                    p.setPen(QPen(with_alpha(col, 0.5 * (1 - k) * draw), 1.2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(x, y), 4 + 10 * k, 4 + 10 * k)
        elif key == "story3":
            self._paint_gallery_visual(p, area, t, now, alpha)
        p.restore()

    def _paint_gallery_visual(self, p: QPainter, area: QRectF, t: float, now: float, alpha: float) -> None:
        """A miniature Gallery: cards pop into a grid one by one, a focus ring hops between them,
        and every few seconds one card lifts as if it were being opened."""
        from jbrowser.ui.theme import TINTS
        th = theme()
        cols, rows = 4, 2
        gap = 16.0
        cw = min(170.0, (area.width() - gap * (cols - 1)) / cols)
        ch = min((area.height() - gap) / rows, cw * 0.72)
        gw = cols * cw + (cols - 1) * gap
        gh = rows * ch + (rows - 1) * gap
        x0 = area.center().x() - gw / 2
        y0 = area.center().y() - gh / 2
        palette = [QColor(c) for _n, c in TINTS.values()]
        focus = int(now / 0.9) % (cols * rows)
        lift_phase = (now % 3.6) / 3.6
        for i in range(cols * rows):
            c, r = i % cols, i // cols
            pop = seg(t, 0.15 + i * 0.07, 0.65 + i * 0.07)
            if pop <= 0:
                continue
            e = out_back(pop)
            rect = QRectF(x0 + c * (cw + gap), y0 + r * (ch + gap), cw, ch)
            focused = i == focus and pop >= 1
            lift = 0.0
            if focused and 0.55 < lift_phase < 0.85:
                lift = math.sin((lift_phase - 0.55) / 0.3 * math.pi)
            scale = (0.7 + 0.3 * e) * (1 + 0.08 * lift)
            p.save()
            p.setOpacity(alpha * min(1.0, pop * 1.6))
            cen = rect.center()
            p.translate(cen.x(), cen.y() - 6 * lift)
            p.scale(scale, scale)
            p.translate(-cen.x(), -cen.y())
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            fill = QColor(255, 255, 255, 30) if th.dark else QColor(255, 255, 255, 200)
            p.fillPath(path, fill)
            thumb = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.64)
            tp = QPainterPath()
            tp.addRoundedRect(thumb, 10, 10)
            g = QLinearGradient(thumb.topLeft(), thumb.bottomRight())
            col = palette[i % len(palette)]
            g.setColorAt(0, with_alpha(col, 0.55))
            g.setColorAt(1, with_alpha(col, 0.18))
            p.fillPath(tp, QBrush(g))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(QColor(BRAND[i % 3]), 0.9))
            p.drawEllipse(QPointF(rect.left() + 13, thumb.bottom() + (rect.bottom() - thumb.bottom()) / 2), 4.5, 4.5)
            line = QColor(255, 255, 255, 60) if th.dark else QColor(0, 0, 0, 40)
            p.fillRect(QRectF(rect.left() + 24, thumb.bottom() + 10, rect.width() * 0.55, 5), line)
            if focused:
                ring = QPainterPath()
                ring.addRoundedRect(rect.adjusted(-4, -4, 4, 4), 13, 13)
                pen = QPen(QBrush(brand_gradient(rect.left(), rect.right(), 0.2 * math.sin(now * 2))), 2.4)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(ring)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 38) if th.dark else QColor(0, 0, 0, 26), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            p.restore()

    def _paint_dots(self, p: QPainter, now: float) -> None:
        if self.phase != "steps" or self.key_of(self.step) == "ready":
            return
        n = len(STEPS) - 1
        a = self.nav_effect.opacity()
        if a <= 0.01:
            return
        th = theme()
        spacing = 16
        cur = min(self.step, n - 1)
        k = out_cubic(seg(now, self.step_t0, self.step_t0 + 0.45))
        prev = max(0, min(self.prev_step, n - 1)) if self.prev_step >= 0 else cur
        pos = lerp(prev, cur, k)
        total = (n - 1) * spacing + 26
        x0 = (self.width() - total) / 2
        y = self.height() - 56
        p.save()
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            x = x0 + i * spacing + (18 if i > pos else 0)
            p.setBrush(with_alpha(th.c("text"), 0.28))
            p.drawEllipse(QPointF(x + 3, y), 3, 3)
        px = x0 + pos * spacing
        pill = QRectF(px, y - 3.5, 24, 7)
        path = QPainterPath()
        path.addRoundedRect(pill, 3.5, 3.5)
        p.fillPath(path, QBrush(brand_gradient(pill.left(), pill.right())))
        p.restore()

    # tour -------------------------------------------------------------------------------------------
    def _paint_tour(self, p: QPainter, now: float, alpha: float) -> None:
        th = theme()
        hole = self._current_hole()
        p.save()
        p.setOpacity(alpha)
        full = QPainterPath()
        full.addRect(QRectF(self.rect()))
        cut = QPainterPath()
        cut.addRoundedRect(hole, 12, 12)
        scrim = full.subtracted(cut)
        p.fillPath(scrim, QColor(0, 0, 0, 118) if th.dark else QColor(20, 20, 40, 92))
        pulse = 0.5 + 0.5 * math.sin(now * 3.2)
        for w, a in ((7, 0.12 + 0.10 * pulse), (2, 0.9)):
            p.setPen(QPen(with_alpha(th.c("accent"), a), w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(hole, 12, 12)
        if self.bubble.isVisible():
            paint_glass(p, QRectF(self.bubble.geometry()), 16, self.bubble.effect.opacity(), strong=True)
        p.restore()
