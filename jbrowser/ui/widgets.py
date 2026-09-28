"""Reusable, custom-painted widgets that follow the theme and the global motion policy."""
from __future__ import annotations

import math

from PyQt6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer,
                          pyqtProperty, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

from jbrowser.core.motion import motion
from jbrowser.models.infobar import InfoBarSpec
from jbrowser.ui.icons import draw_glyph
from jbrowser.ui.theme import theme


class IconButton(QAbstractButton):
    """Flat, rounded icon button with hover/pressed states, optional badge and progress ring."""

    def __init__(self, glyph_name: str, tooltip: str = "", parent: QWidget | None = None, size: int = 32,
                 glyph_px: float | None = None, checkable: bool = False, variant: str = "normal",
                 width: int | None = None):
        super().__init__(parent)
        self._glyph = glyph_name
        self._glyph_px = glyph_px
        self._hover = False
        self._force_hover = False
        self._force_pressed = False
        self._badge: str | None = None
        self._badge_token = "accent"
        self._progress: float | None = None
        self._variant = variant          # normal | close (red hover) | accent | subtle
        self._active_color: str | None = None
        self.setCheckable(checkable)
        self.setFixedSize(width or size, size)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)

    def set_glyph(self, name: str) -> None:
        if name != self._glyph:
            self._glyph = name
            self.update()

    def set_badge(self, text: str | None, token: str = "accent") -> None:
        if text != self._badge or token != self._badge_token:
            self._badge = text
            self._badge_token = token
            self.update()

    def set_progress(self, value: float | None) -> None:
        self._progress = value
        self.update()

    def set_active_color(self, token: str | None) -> None:
        self._active_color = token
        self.update()

    def set_force_hover(self, v: bool) -> None:
        self._force_hover = v
        self.update()

    def set_force_pressed(self, v: bool) -> None:
        self._force_pressed = v
        self.update()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        hover = (self._hover or self._force_hover) and self.isEnabled()
        pressed = (self.isDown() or self._force_pressed) and self.isEnabled()
        fg = th.c("text") if hover else th.c("text2")
        bg = None
        if self._variant == "close" and (hover or pressed):
            bg = QColor("#c42b1c") if not pressed else QColor("#b0271a")
            fg = QColor("#ffffff")
        elif pressed:
            bg = th.c("pressed")
        elif hover:
            bg = th.c("hover")
        if self.isChecked():
            bg = th.accent_alpha(0.22) if not hover else th.accent_alpha(0.30)
            fg = th.c("accent")
        if self._variant == "accent":
            fg = th.c("accent")
        if self._active_color:
            fg = th.c(self._active_color)
        if not self.isEnabled():
            fg = th.c("text3")
        if bg is not None:
            radius = 4 if self._variant == "close" else 7
            path = QPainterPath()
            rr = QRectF(self.rect()) if self._variant == "close" else r
            path.addRoundedRect(rr, radius, radius)
            p.fillPath(path, bg)
        px = self._glyph_px or min(self.width(), self.height()) * 0.42
        draw_glyph(p, QRectF(self.rect()), self._glyph, fg, px)
        if self._progress is not None:
            ring = QRectF(self.rect()).adjusted(4, 4, -4, -4)
            p.setPen(QPen(th.c("divider"), 2))
            p.drawEllipse(ring)
            p.setPen(QPen(th.c("accent"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring, 90 * 16, -int(360 * 16 * max(0.02, min(1.0, self._progress))))
        if self._badge is not None:
            f = QFont(self.font())
            f.setPixelSize(9)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            fm = QFontMetrics(f)
            text = self._badge
            w = max(14, fm.horizontalAdvance(text) + 8) if text else 8
            h = 14 if text else 8
            br = QRectF(self.width() - w - 1, 1, w, h)
            path = QPainterPath()
            path.addRoundedRect(br, h / 2, h / 2)
            p.fillPath(path, th.c(self._badge_token))
            if text:
                p.setPen(th.accent_text() if self._badge_token == "accent" else QColor("#ffffff"))
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class ToggleSwitch(QAbstractButton):
    """Windows 11 style toggle switch with an animated knob."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self._hover = False
        self.setFixedSize(40, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._animate)

    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, v: float) -> None:
        self._pos = float(v)
        self.update()

    knob = pyqtProperty(float, _get_pos, _set_pos)

    def _animate(self, checked: bool) -> None:
        motion().animate_property(self, b"knob", self._pos, 1.0 if checked else 0.0, 160)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        track = QPainterPath()
        track.addRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.isChecked():
            p.fillPath(track, th.c("accent") if self._hover is False else th.accent.lighter(110))
            knob_color = th.accent_text()
        else:
            p.fillPath(track, th.c("input"))
            p.setPen(QPen(th.c("text2"), 1))
            p.drawPath(track)
            knob_color = th.c("text2")
        d = r.height() - 8 + (2 if self._hover else 0)
        x = r.left() + 4 + (r.width() - 8 - d) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob_color)
        p.drawEllipse(QRectF(x, r.center().y() - d / 2, d, d))
        p.end()


class Spinner(QWidget):
    """Indeterminate progress arc. Only animates while visible."""

    def __init__(self, size: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 9) % 360
        self.update()

    def showEvent(self, e) -> None:
        self._timer.start()

    def hideEvent(self, e) -> None:
        self._timer.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(theme().c("accent"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span = 100 + 60 * math.sin(math.radians(self._angle * 2))
        p.drawArc(r, int(-self._angle * 16), int(span * 16))
        p.end()


class ProgressLine(QWidget):
    """Thin loading bar that eases towards the target value."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(2)
        self._value = 0.0
        self._target = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_progress(self, value: int, loading: bool) -> None:
        target = max(0.0, min(1.0, value / 100.0)) if loading else (1.0 if self._value > 0 else 0.0)
        if not loading and self._value <= 0:
            self._value = self._target = 0.0
            self.update()
            return
        self._target = target
        if not motion().enabled:
            self._value = target
            self._finish_if_done(loading)
            self.update()
            return
        self._loading = loading
        if not self._timer.isActive():
            self._timer.start()

    def _finish_if_done(self, loading: bool) -> None:
        if not loading and self._value >= 1.0:
            QTimer.singleShot(motion().ms(220), self._reset)

    def _reset(self) -> None:
        self._value = self._target = 0.0
        self.update()

    def _step(self) -> None:
        self._value += (self._target - self._value) * 0.18
        if abs(self._target - self._value) < 0.004:
            self._value = self._target
            self._timer.stop()
            self._finish_if_done(getattr(self, "_loading", False))
        self.update()

    def paintEvent(self, _e) -> None:
        if self._value <= 0:
            return
        p = QPainter(self)
        w = int(self.width() * self._value)
        p.fillRect(QRect(0, 0, w, self.height()), theme().c("accent"))
        p.end()


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None, mode=Qt.TextElideMode.ElideRight):
        super().__init__(text, parent)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()) if not self.property("color") else
                 QColor(self.property("color")))
        fm = self.fontMetrics()
        text = fm.elidedText(self.text(), self._mode, self.width())
        p.drawText(self.rect(), int(self.alignment() | Qt.AlignmentFlag.AlignVCenter), text)
        p.end()


class InfoBarWidget(QFrame):
    """Renders an :class:`InfoBarSpec` inside a card (permission prompts, save password, ...)."""

    closed = pyqtSignal(str)

    def __init__(self, spec: InfoBarSpec, parent: QWidget | None = None):
        super().__init__(parent)
        self.spec = spec
        self._acted = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.setSpacing(8)
        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)
        lay.addWidget(self._icon)
        text = QLabel(spec.text)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(text, 1)
        for act in spec.actions:
            b = QPushButton(act.label)
            b.setProperty("primary", act.primary)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, a=act: self._run(a.callback))
            lay.addWidget(b)
        close = IconButton("close", "Dismiss", size=28, glyph_px=10)
        close.clicked.connect(self.dismiss)
        lay.addWidget(close)
        if spec.timeout_ms:
            QTimer.singleShot(spec.timeout_ms, self.dismiss)

    def _run(self, cb) -> None:
        self._acted = True
        try:
            cb()
        finally:
            self.closed.emit(self.spec.key)

    def dismiss(self) -> None:
        if self._acted:
            return
        self._acted = True
        if self.spec.on_dismiss:
            self.spec.on_dismiss()
        self.closed.emit(self.spec.key)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        token = {"warning": "warning", "danger": "danger", "success": "success"}.get(self.spec.kind)
        base = th.c(token) if token else th.c("accent")
        bg = QColor(base)
        bg.setAlphaF(0.16)
        p.fillRect(self.rect(), th.surface("card"))
        p.fillRect(self.rect(), bg)
        p.fillRect(QRect(0, 0, 3, self.height()), base)
        draw_glyph(p, QRectF(self._icon.geometry()), self.spec.icon, base, 15)
        p.end()


class Toast(QWidget):
    def __init__(self, text: str, glyph_name: str, parent: QWidget):
        super().__init__(parent)
        self._text = text
        self._glyph = glyph_name
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        self.setFont(f)
        fm = QFontMetrics(f)
        self.resize(min(parent.width() - 40, fm.horizontalAdvance(text) + 58), 40)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, th.c("panel"))
        p.setPen(QPen(th.c("panel_border"), 1))
        p.drawPath(path)
        draw_glyph(p, QRectF(12, 0, 22, self.height()), self._glyph, th.c("accent"), 15)
        p.setPen(th.c("text"))
        fm = self.fontMetrics()
        p.drawText(QRectF(40, 0, self.width() - 52, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width() - 52))
        p.end()


class ToastManager(QObject):
    """Stacks transient notifications at the bottom-centre of a host widget."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._toasts: list[Toast] = []
        host.installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:
        if obj is self._host and ev.type() == QEvent.Type.Resize:
            self._layout()
        return False

    def show(self, text: str, glyph_name: str = "info", duration_ms: int = 2600) -> None:
        t = Toast(text, glyph_name, self._host)
        self._toasts.append(t)
        if len(self._toasts) > 4:
            self._remove(self._toasts[0])
        self._layout()
        t.show()
        t.raise_()
        motion().animate_property(t._fx, b"opacity", 0.0, 1.0, 160)
        QTimer.singleShot(duration_ms, lambda tt=t: self._fade(tt))

    def _fade(self, t: Toast) -> None:
        if t not in self._toasts:
            return
        anim = motion().animate_property(t._fx, b"opacity", 1.0, 0.0, 220, on_finished=lambda tt=t: self._remove(tt))
        if anim is None and t in self._toasts:
            self._remove(t)

    def _remove(self, t: Toast) -> None:
        if t in self._toasts:
            self._toasts.remove(t)
            t.deleteLater()
            self._layout()

    def _layout(self) -> None:
        y = self._host.height() - 28
        for t in reversed(self._toasts):
            y -= t.height()
            t.move((self._host.width() - t.width()) // 2, y)
            y -= 8


class Overlay(QWidget):
    """Base class for full-window modal overlays (Lazy Toolbar, cheat sheet) with a scrim."""

    closed = pyqtSignal()

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self.hide()
        host.installEventFilter(self)
        self._closing = False

    def eventFilter(self, obj, ev) -> bool:
        if obj is self._host and ev.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self._host.rect())
        return False

    def panel_rect(self) -> QRect:
        raise NotImplementedError

    def open_overlay(self) -> None:
        self._closing = False
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        fx = QGraphicsOpacityEffect(self)
        fx.setOpacity(0.0)
        self.setGraphicsEffect(fx)
        anim = motion().animate_property(fx, b"opacity", 0.0, 1.0, 150, QEasingCurve.Type.OutCubic,
                                         on_finished=lambda: self.setGraphicsEffect(None))
        if anim is None:
            self.setGraphicsEffect(None)

    def close_overlay(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True

        def done():
            self.setGraphicsEffect(None)
            self.hide()
            self._closing = False
            self.closed.emit()

        fx = QGraphicsOpacityEffect(self)
        fx.setOpacity(1.0)
        self.setGraphicsEffect(fx)
        motion().animate_property(fx, b"opacity", 1.0, 0.0, 120, QEasingCurve.Type.InCubic, on_finished=done)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme().c("scrim"))
        pr = QRectF(self.panel_rect())
        if pr.isValid():
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            shadow = theme().c("shadow")
            for i in range(10, 0, -2):
                c = QColor(shadow)
                c.setAlphaF(shadow.alphaF() * 0.09 * (10 - i) / 10)
                path = QPainterPath()
                path.addRoundedRect(pr.adjusted(-i, -i + 4, i, i + 4), 16 + i, 16 + i)
                p.fillPath(path, c)
        p.end()

    def mousePressEvent(self, e) -> None:
        if not self.panel_rect().contains(e.position().toPoint()):
            self.close_overlay()
        e.accept()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close_overlay()
            return
        super().keyPressEvent(e)


def hline(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {theme().tokens['divider']};")
    return f


def muted_label(text: str, parent: QWidget | None = None, wrap: bool = True) -> QLabel:
    lab = QLabel(text, parent)
    lab.setProperty("muted", True)
    lab.setWordWrap(wrap)
    return lab


def vbox(*widgets, margins=(0, 0, 0, 0), spacing=8) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def hbox(*widgets, margins=(0, 0, 0, 0), spacing=8) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def rounded_rect_path(r: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    return path


def point_in(widget: QWidget, global_pos: QPoint) -> bool:
    return widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(global_pos))


def menu_action(menu, text: str, callback=None, glyph: str | None = None, *, checkable: bool = False,
                checked: bool = False, shortcut: str | None = None, enabled: bool = True):
    """Add an action to a QMenu with an optional Fluent glyph and callback."""
    from PyQt6.QtGui import QAction, QKeySequence
    from jbrowser.ui.icons import icon as make_icon

    act = QAction(text.replace("&", "&&"), menu)     # no accidental mnemonics
    if glyph and not checkable:                     # an icon would hide the check mark
        act.setIcon(make_icon(glyph))
    if checkable:
        act.setCheckable(True)
        act.setChecked(checked)
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
        act.setShortcutVisibleInContextMenu(True)
    act.setEnabled(enabled)
    if callback is not None:
        act.triggered.connect(lambda _checked=False, cb=callback: cb())
    menu.addAction(act)
    return act


def submenu(menu, text: str, glyph: str | None = None):
    from jbrowser.ui.icons import icon as make_icon

    sub = menu.addMenu(text.replace("&", "&&"))
    if glyph:
        sub.setIcon(make_icon(glyph))
    return sub
