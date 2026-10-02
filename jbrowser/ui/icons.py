"""Vector icons rendered from the Windows 11 "Segoe Fluent Icons" font (MDL2 fallback),
plus the procedurally drawn JBrowser logo. No image assets are required at runtime."""
from __future__ import annotations

import os
import tempfile

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QIcon, QIconEngine, QImage, QLinearGradient,
                         QPainter, QPainterPath, QPen, QPixmap)

GLYPHS = {
    "back": "", "forward": "", "refresh": "", "stop": "", "cancel": "",
    "close": "", "min": "", "max": "", "restore": "", "add": "",
    "settings": "", "download": "", "history": "", "star": "", "star_fill": "",
    "search": "", "more": "", "lock": "", "unlock": "", "shield": "",
    "moon": "", "volume": "", "mute": "", "menu": "", "sidebar": "",
    "openpane": "", "closepane": "", "key": "", "code": "", "zoom_in": "",
    "zoom_out": "", "globe": "", "world": "", "page": "", "delete": "",
    "edit": "", "copy": "", "folder": "", "folder_open": "", "open_file": "",
    "pause": "", "play": "", "check": "", "sync": "", "pin": "",
    "keyboard": "", "help": "", "filter": "", "grid": "", "taskview": "",
    "fullscreen": "", "exit_fullscreen": "", "sun": "", "eye": "",
    "incognito": "", "network": "", "vpn": "", "info": "", "warning": "",
    "error": "", "print": "", "save": "", "share": "", "camera": "",
    "mic": "", "mappin": "", "ringer": "", "paste": "", "font": "",
    "mouse": "", "tv": "", "lightning": "", "people": "", "work": "",
    "link": "", "newwindow": "", "bug": "", "columns": "", "picture": "",
    "clear": "", "connect": "", "chev_down": "", "chev_up": "",
    "chev_left": "", "chev_right": "", "selectall": "", "home": "",
    "lightbulb": "", "dock_left": "", "dock_right": "", "tiles": "",
    "speed": "", "tag": "", "cloud": "", "bookmarks": "", "list": "",
    "clock": "", "timer": "", "power": "", "switch": "", "fingerprint": "",
    "permissions": "", "emoji": "", "crop": "", "repair": "",
    "developer": "", "blocked": "", "people2": "", "heart": "",
    "archive": "", "unpin": "",
}
# Newer glyphs, written as code points (Segoe Fluent Icons).
GLYPHS.update({"colour": "", "gallery": "", "drag": "", "layers": "", "expand": "",
               "collapse": ""})

GLYPHS.update({"stack": "", "reading": ""})   # DockBottom, ReadingMode

_font_family: str | None = None


def icon_font_family() -> str:
    global _font_family
    if _font_family is None:
        fams = set(QFontDatabase.families())
        _font_family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), "Segoe UI Symbol")
    return _font_family


def glyph(name: str) -> str:
    return GLYPHS.get(name, name if len(name) == 1 else "")


class GlyphIconEngine(QIconEngine):
    """Paints a font glyph; colour resolves from the live theme unless fixed."""

    def __init__(self, char: str, color: QColor | str | None = None, scale: float = 0.62):
        super().__init__()
        self.char = char
        self.color = color
        self.scale = scale

    def _resolve(self, mode: QIcon.Mode) -> QColor:
        from jbrowser.ui.theme import _theme
        if isinstance(self.color, QColor):
            c = QColor(self.color)
        elif isinstance(self.color, str) and _theme is not None:
            c = _theme.c(self.color)
        elif _theme is not None:
            c = _theme.c("text")
        else:
            c = QColor("#ffffff")
        if mode == QIcon.Mode.Disabled:
            c.setAlphaF(c.alphaF() * 0.35)
        return c

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(icon_font_family())
        font.setPixelSize(max(1, int(round(min(rect.width(), rect.height()) * self.scale))))
        painter.setFont(font)
        painter.setPen(self._resolve(mode))
        painter.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, self.char)
        painter.restore()

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State, scale: float) -> QPixmap:
        scale = max(1.0, scale)
        pm = QPixmap(QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
        pm.setDevicePixelRatio(scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return self.scaledPixmap(size, mode, state, 1.0)

    def clone(self) -> "GlyphIconEngine":
        return GlyphIconEngine(self.char, self.color, self.scale)


def icon(name: str, color: QColor | str | None = None, scale: float = 0.62) -> QIcon:
    return QIcon(GlyphIconEngine(glyph(name), color, scale))


def draw_glyph(painter: QPainter, rect: QRectF | QRect, name: str, color: QColor, px: float | None = None) -> None:
    painter.save()
    font = QFont(icon_font_family())
    r = QRectF(rect)
    font.setPixelSize(max(1, int(round(px if px else min(r.width(), r.height()) * 0.62))))
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(r, Qt.AlignmentFlag.AlignCenter, glyph(name))
    painter.restore()


def draw_emoji(painter: QPainter, rect: QRectF | QRect, text: str, px: float | None = None) -> None:
    painter.save()
    r = QRectF(rect)
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(max(1, int(round(px if px else min(r.width(), r.height()) * 0.7))))
    painter.setFont(font)
    painter.setPen(QPen(QColor("#ffffff")))  # colour glyphs ignore it, but a pen must be set
    painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()


def glyph_png(name: str, color: QColor, size: int = 16) -> str:
    """Render a glyph to a PNG (plus @2x) for use inside Qt style sheets."""
    folder = os.path.join(tempfile.gettempdir(), "jbrowser-ui")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"{name}-{color.name(QColor.NameFormat.HexArgb)[1:]}-{size}")
    for suffix, factor in (("", 1), ("@2x", 2)):
        path = f"{base}{suffix}.png"
        if not os.path.exists(path):
            img = QImage(size * factor, size * factor, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            draw_glyph(p, QRectF(0, 0, size * factor, size * factor), name, color, px=size * factor * 0.75)
            p.end()
            img.save(path)
    return (base + ".png").replace("\\", "/")


# ------------------------------------------------------------------------------ logo
def paint_logo(p: QPainter, rect: QRectF) -> None:
    """JBrowser mark: a gradient squircle with three offset 'cards' on a horizontal canvas."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(rect)
    radius = r.width() * 0.26
    grad = QLinearGradient(r.topLeft(), r.bottomRight())
    grad.setColorAt(0.0, QColor("#5b8cff"))
    grad.setColorAt(0.55, QColor("#8a5cff"))
    grad.setColorAt(1.0, QColor("#ff5c9d"))
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.fillPath(path, QBrush(grad))
    # glossy top highlight
    hi = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
    hi.setColorAt(0, QColor(255, 255, 255, 70))
    hi.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(hi))
    # three cards on a canvas
    w, h = r.width(), r.height()
    card_h = h * 0.46
    top = r.top() + h * 0.27
    specs = [(0.14, 0.22, 110), (0.40, 0.30, 255), (0.74, 0.14, 110)]
    for x_frac, w_frac, alpha in specs:
        cr = QRectF(r.left() + w * x_frac, top, w * w_frac, card_h)
        cp = QPainterPath()
        cp.addRoundedRect(cr, w * 0.035, w * 0.035)
        p.fillPath(cp, QColor(255, 255, 255, alpha))
    # "J" glyph on the centre card
    font = QFont("Segoe UI Variable Display")
    font.setBold(True)
    font.setPixelSize(max(1, int(card_h * 0.72)))
    p.setFont(font)
    p.setPen(QPen(QColor("#6a5cff")))
    p.drawText(QRectF(r.left() + w * 0.40, top, w * 0.30, card_h), Qt.AlignmentFlag.AlignCenter, "J")
    # canvas baseline
    p.setPen(QPen(QColor(255, 255, 255, 150), max(1.0, w * 0.025), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    y = top + card_h + h * 0.09
    p.drawLine(QPointF(r.left() + w * 0.2, y), QPointF(r.right() - w * 0.2, y))
    p.restore()


def logo_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_logo(p, QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92))
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s))
    return ic
