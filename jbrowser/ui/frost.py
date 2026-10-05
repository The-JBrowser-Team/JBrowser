"""Frosted: JBrowser's own translucent look.

Every JBrowser window is fully opaque. Under its content JBrowser paints a frosted picture of the desktop
wallpaper: reduced to its colours, softly blurred and tinted dark or light. Windows' own materials (Mica,
Acrylic) are not used at all, so nothing Windows draws (or fails to draw) can show through a JBrowser window.

The picture is fitted to the window, not to the screen, so moving a window never repaints it. It is built once
per window size and look (tiny wallpaper → saturated and tinted → smoothly enlarged → a whisper of grain against
banding) and then painted with plain 1:1 copies, which is as cheap as filling with one colour.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import random
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from jbrowser.platform import win

log = logging.getLogger(__name__)

SRC_W = 64              # the wallpaper's colours, not its details
SMOOTH_W = 1024         # the enlarged, smooth picture every window size is cut from
SATURATION = 1.35       # keep the wallpaper's colours alive under the tint
GRAIN = 0.028           # opacity of the grain that keeps the soft gradients from banding
CACHE_SIZES = 4         # window pictures kept (main window, Settings, ... and both looks while switching)
CACHE_LOOKS = 2         # smooth pictures kept (the current look, and the last one while trying colour tints)


def _saturate_and_tint(img: QImage, tint: QColor, wash: QColor | None) -> QImage:
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    ta = tint.alphaF()
    tr, tg, tb = tint.red(), tint.green(), tint.blue()
    wa = wash.alphaF() if wash is not None else 0.0
    wr, wg, wb = (wash.red(), wash.green(), wash.blue()) if wash is not None else (0, 0, 0)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixel(x, y)
            r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            r, g, b = (min(255.0, max(0.0, lum + (v - lum) * SATURATION)) for v in (r, g, b))
            r, g, b = r + (tr - r) * ta, g + (tg - g) * ta, b + (tb - b) * ta
            if wa:
                r, g, b = r + (wr - r) * wa, g + (wg - g) * wa, b + (wb - b) * wa
            out.setPixel(x, y, 0xFF000000 | (int(r) << 16) | (int(g) << 8) | int(b))
    return out


def _enlarge(img: QImage, width: int) -> QImage:
    """Smooth enlargement in steps of two: each bilinear step softens the last, so no seams show."""
    smooth = Qt.TransformationMode.SmoothTransformation
    while img.width() < width:
        img = img.scaled(img.width() * 2, img.height() * 2, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    return img


def _reduce(img: QImage, width: int) -> QImage:
    """Smooth reduction in steps of two (a single big step would alias)."""
    smooth = Qt.TransformationMode.SmoothTransformation
    img = img.convertToFormat(QImage.Format.Format_RGB32)
    while img.width() > width * 2:
        img = img.scaled(max(width, img.width() // 2), max(1, img.height() // 2),
                         Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    return img.scaledToWidth(width, smooth)


class Frost(QObject):
    """The frosted picture behind JBrowser's windows. ``changed`` fires when the wallpaper changes."""

    changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.cache_dir: Path | None = None
        self._src: QImage | None = None           # the wallpaper at SRC_W pixels wide
        self._src_key: tuple | None = None
        self._smooth: OrderedDict[tuple, QImage] = OrderedDict()
        self._pixmaps: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._grain: QPixmap | None = None
        self._pending: dict[tuple, tuple] = {}     # per window and layer: the latest size it asked for
        self._seen: set[tuple] = set()              # (window, layer) pairs that already have had a picture
        self._build_timer = QTimer(self)
        self._build_timer.setSingleShot(True)
        self._build_timer.setInterval(140)         # a window being resized gets its exact picture when it rests
        self._build_timer.timeout.connect(self._build_pending)

    # ---------------------------------------------------------------- the wallpaper
    @staticmethod
    def _wallpaper() -> tuple[str, tuple]:
        path = os.environ.get("JBROWSER_WALLPAPER") or win.wallpaper_path()
        try:
            st = os.stat(path) if path else None
        except OSError:
            st = None
        if st is None:
            colour = win.desktop_color()
            return "", ("colour", colour.name() if colour is not None else "")
        return path, (os.path.normcase(path), int(st.st_mtime), st.st_size)

    def _source(self) -> QImage:
        path, key = self._wallpaper()
        if key == self._src_key and self._src is not None:
            return self._src
        img = None
        cached = None
        if path and self.cache_dir is not None:
            name = hashlib.sha1(repr(key).encode()).hexdigest()[:16]
            cached = self.cache_dir / f"frost-{name}.png"
            if cached.exists():
                img = QImage(str(cached))
                if img.isNull():
                    img = None
        if img is None and path:
            full = QImage(path)
            if not full.isNull():
                img = _reduce(full, SRC_W)
                if cached is not None:
                    try:
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        for old in cached.parent.glob("frost-*.png"):
                            old.unlink(missing_ok=True)
                        img.save(str(cached))
                    except OSError:
                        pass
        if img is None:
            # No picture (a solid colour, a slideshow between files, an unreadable format): a quiet gradient
            # of the desktop colour, or JBrowser's own colours.
            colour = win.desktop_color() or QColor("#3b4cc0")
            img = QImage(4, 3, QImage.Format.Format_RGB32)
            for x in range(4):
                for y in range(3):
                    c = QColor(colour).lighter(100 + 12 * x - 8 * y) if colour.value() > 40 else \
                        QColor("#3b4cc0" if x < 2 else "#8a3fd1")
                    img.setPixelColor(x, y, c)
        self._src, self._src_key = img.convertToFormat(QImage.Format.Format_RGB32), key
        self._smooth.clear()
        self._pixmaps.clear()
        log.info("Frosted look from %s", "the wallpaper" if path else "the desktop colour")
        return self._src

    def check(self) -> None:
        """Windows changed a setting (or JBrowser was activated): pick up a new wallpaper."""
        _path, key = self._wallpaper()
        if key != self._src_key:
            self._source()
            self.changed.emit()

    # ---------------------------------------------------------------- pictures
    def _grain_pixmap(self) -> QPixmap:
        if self._grain is None:
            rnd = random.Random(20261005)
            data = bytes(rnd.getrandbits(8) for _ in range(128 * 128))
            img = QImage(data, 128, 128, 128, QImage.Format.Format_Grayscale8).copy()
            self._grain = QPixmap.fromImage(img)
        return self._grain

    def _smooth_for(self, look: tuple) -> QImage:
        img = self._smooth.get(look)
        if img is None:
            tint, wash = QColor.fromRgba(look[0]), (QColor.fromRgba(look[1]) if look[1] else None)
            img = _enlarge(_saturate_and_tint(self._source(), tint, wash), SMOOTH_W)
            self._smooth[look] = img
            while len(self._smooth) > CACHE_LOOKS:
                self._smooth.popitem(last=False)
        else:
            self._smooth.move_to_end(look)
        return img

    def _build(self, key: tuple) -> QPixmap:
        w, h, dpr, look, overlay = key
        pw, ph = max(1, math.ceil(w * dpr)), max(1, math.ceil(h * dpr))
        smooth = self._smooth_for(look)
        big = smooth.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        img = big.copy((big.width() - pw) // 2, (big.height() - ph) // 2, pw, ph)
        p = QPainter(img)
        p.setOpacity(GRAIN)
        p.drawTiledPixmap(0, 0, pw, ph, self._grain_pixmap())
        p.setOpacity(1.0)
        if overlay:
            p.fillRect(0, 0, pw, ph, QColor.fromRgba(overlay))
        p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        return pm

    def _remember(self, key: tuple, pm: QPixmap) -> None:
        self._pixmaps[key] = pm
        self._pixmaps.move_to_end(key)
        while len(self._pixmaps) > CACHE_SIZES:
            self._pixmaps.popitem(last=False)

    def _build_pending(self) -> None:
        pending, self._pending = self._pending, {}
        for key in pending.values():
            if key not in self._pixmaps:
                self._remember(key, self._build(key))
        if pending:
            self.changed.emit()

    def pixmap(self, size: QSize, dpr: float, look: tuple, overlay: int = 0, owner: int = 0) -> tuple[QPixmap, bool]:
        """The picture for a window of ``size``: (pixmap, exact). While a window is being resized it gets the
        closest picture already made (stretched) and only its final size is built, a moment later."""
        key = (size.width(), size.height(), round(dpr, 3), look, overlay)
        pm = self._pixmaps.get(key)
        if pm is not None:
            self._pixmaps.move_to_end(key)
            return pm, True
        near = [(k, v) for k, v in self._pixmaps.items() if k[2:] == key[2:]]
        if not near or (owner, overlay) not in self._seen:
            self._seen.add((owner, overlay))    # a window's first picture is made right away
            pm = self._build(key)
            self._remember(key, pm)
            return pm, True
        self._pending[(owner, overlay)] = key
        self._build_timer.start()
        return near[-1][1], False

    def paint(self, p: QPainter, widget: QWidget, rect, look: tuple, overlay: int = 0) -> None:
        """Paint the part of the window's picture under ``rect`` (widget coordinates)."""
        window = widget.window()
        size = window.size()
        dpr = window.devicePixelRatioF()
        pm, exact = self.pixmap(size, dpr, look, overlay, id(window))
        r = QRectF(rect)
        off = widget.mapTo(window, QPoint(0, 0))
        if exact:
            # Whole device pixels on both sides: at fractional scales (150 %) a rectangle's edges would otherwise
            # round differently in the window and in the picture, and a small repaint would not match the rest.
            dev = QRectF((r.x() + off.x()) * dpr, (r.y() + off.y()) * dpr, r.width() * dpr,
                         r.height() * dpr).toAlignedRect()
            target = QRectF(dev.x() / dpr - off.x(), dev.y() / dpr - off.y(), dev.width() / dpr, dev.height() / dpr)
            p.drawPixmap(target, pm, QRectF(dev))
        else:
            src = r.translated(off.x(), off.y())
            sx = pm.width() / max(1.0, size.width())
            sy = pm.height() / max(1.0, size.height())
            p.drawPixmap(r, pm, QRectF(src.x() * sx, src.y() * sy, src.width() * sx, src.height() * sy))


_frost: Frost | None = None


def frost() -> Frost:
    global _frost
    if _frost is None:
        _frost = Frost()
    return _frost
