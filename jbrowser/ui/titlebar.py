"""Custom title bar: grouped navigation, the address pill, tools and window controls."""
from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QToolTip, QWidget

from jbrowser.core.urls import is_local_host, strip_www
from jbrowser.models.tab import Tab
from jbrowser.ui.icons import draw_emoji, draw_glyph
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

TITLE_H = 44
BTN = 32
PILL_MIN, PILL_MAX = 300, 680     # the address bar is centred and never wider than this


def suspicious_idn(url: QUrl) -> bool:
    """True when a host mixes Latin letters with look-alike characters from other scripts."""
    host = url.host()
    if not host or host.isascii():
        return False
    scripts = set()
    for ch in host:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            scripts.add(name.split(" ")[0] if name else "?")
    return len(scripts - {"DIGIT"}) > 1


def security_state(ctx: "AppContext", tab: Tab | None) -> tuple[str, str, str]:
    """Returns (glyph, colour token, short label) for the tab's connection."""
    if tab is None or not tab.url:
        return "search", "text3", ""
    url = QUrl(tab.url)
    if tab.title == "Dangerous site blocked":
        return "shield", "danger", "Dangerous"
    if url.scheme() == "https":
        return ("warning", "warning", "Check address") if suspicious_idn(url) else ("lock", "text2", "")
    if url.scheme() == "http":
        if is_local_host(url.host()) or ctx.privacy.dev_target(url.host()):
            return "connect", "text2", ""
        return "warning", "warning", "Not secure"
    return "page", "text2", ""


class AddressPill(QWidget):
    clicked = pyqtSignal()
    spaceClicked = pyqtSignal(QPoint)
    starClicked = pyqtSignal()
    securityClicked = pyqtSignal(QPoint)
    shieldClicked = pyqtSignal(QPoint)

    def __init__(self, ctx: "AppContext", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.setFixedHeight(32)
        self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setMouseTracking(True)
        self._hover = False
        self._hover_zone = ""
        self.tab: Tab | None = None
        self._blocked = 0                 # trackers blocked on this page (the shield's count)
        self._protected = True            # False: protections are off for this site (warning colour)

    def set_tab(self, tab: Tab | None) -> None:
        self.tab = tab
        self.update()

    def set_shield(self, blocked: int, protected: bool) -> None:
        if (blocked, protected) != (self._blocked, self._protected):
            self._blocked, self._protected = blocked, protected
            self.update()

    def _chip_font(self) -> QFont:
        f = QFont(self.font())
        f.setWeight(QFont.Weight.Medium)
        return f

    def _space_rect(self) -> QRectF:
        sp = self.ctx.state.active_space
        fm = QFontMetrics(self._chip_font())
        w = 42 + (fm.horizontalAdvance(sp.name) if sp else 0)
        return QRectF(4, 3, min(w, 170), self.height() - 6)

    def _security_rect(self) -> QRectF:
        glyph, _tok, label = security_state(self.ctx, self.tab)
        w = 26 + (QFontMetrics(self.font()).horizontalAdvance(label) + 6 if label else 0)
        return QRectF(self._space_rect().right() + 6, 4, w, self.height() - 8)

    def _star_rect(self) -> QRectF:
        return QRectF(self.width() - 34, 3, 30, self.height() - 6)

    def _shield_rect(self) -> QRectF:
        """Privacy protections, just left of the star (moved here from the ribbon in 2.0)."""
        star = self._star_rect()
        if self.tab is None or not self.tab.url:
            return QRectF(star)           # no star on an empty card: the shield takes its place
        return QRectF(star.left() - 30, star.top(), 30, star.height())

    def _zone(self, pos) -> str:
        if self._space_rect().contains(pos):
            return "space"
        has_url = self.tab is not None and bool(self.tab.url)
        if has_url and self._security_rect().contains(pos):
            return "security"
        if self._shield_rect().contains(pos):
            return "shield"
        if self._star_rect().contains(pos) and has_url:
            return "star"
        return "url"

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            zone = self._zone(QPointF(e.pos()))
            text = {"space": "Switch space", "security": "Site information and permissions",
                    "star": "Remove bookmark" if self.tab and self.ctx.bookmarks.find_url(self.tab.url) else
                    "Bookmark this page (Ctrl+D)",
                    "shield": self._shield_tip()}.get(zone, "")
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _shield_tip(self) -> str:
        if not self._protected:
            return "Privacy protections are off for this site. Click to change"
        if self._blocked:
            return f"Privacy protections: {self._blocked} tracker{'s' if self._blocked != 1 else ''} blocked " \
                   "on this page"
        return "Privacy protections"

    def mouseMoveEvent(self, e) -> None:
        zone = self._zone(e.position())
        if zone != self._hover_zone:
            self._hover_zone = zone
            self.setCursor(Qt.CursorShape.PointingHandCursor if zone != "url" else Qt.CursorShape.IBeamCursor)
            self.update()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self._hover_zone = ""
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        zone = self._zone(e.position())
        if zone == "space":
            self.spaceClicked.emit(self.mapToGlobal(QPoint(int(self._space_rect().left()), self.height())))
        elif zone == "security":
            self.securityClicked.emit(self.mapToGlobal(QPoint(int(self._security_rect().left()), self.height() + 4)))
        elif zone == "shield":
            self.shieldClicked.emit(self.mapToGlobal(QPoint(int(self._shield_rect().left()), self.height() + 4)))
        elif zone == "star":
            self.starClicked.emit()
        else:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, th.c("hover") if self._hover else th.c("input"))
        p.setPen(QPen(th.c("input_border"), 1))
        p.drawPath(path)
        sp = self.ctx.state.active_space
        sr = self._space_rect()
        if sp:
            chip = QPainterPath()
            chip.addRoundedRect(sr, sr.height() / 2, sr.height() / 2)
            c = QColor(sp.color)
            c.setAlphaF(0.30 if self._hover_zone == "space" else 0.20)
            p.fillPath(chip, c)
            draw_emoji(p, QRectF(sr.left() + 5, sr.top(), 22, sr.height()), sp.icon, 12)
            p.setFont(self._chip_font())
            p.setPen(th.c("text"))
            p.drawText(QRectF(sr.left() + 30, sr.top(), sr.width() - 36, sr.height()), Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(sp.name, Qt.TextElideMode.ElideRight, int(sr.width() - 36)))
        p.setFont(self.font())
        self._paint_shield(p)
        tab = self.tab
        if tab is None or not tab.url:
            x = sr.right() + 10
            draw_glyph(p, QRectF(x, 0, 18, self.height()), "search", th.c("text3"), 12)
            p.setPen(th.c("text3"))
            p.drawText(QRectF(x + 24, 0, self.width() - x - 60, self.height()), Qt.AlignmentFlag.AlignVCenter,
                       "Search or enter an address")
            p.end()
            return
        glyph, token, label = security_state(self.ctx, tab)
        secr = self._security_rect()
        if self._hover_zone == "security":
            hp = QPainterPath()
            hp.addRoundedRect(secr, secr.height() / 2, secr.height() / 2)
            p.fillPath(hp, th.c("pressed"))
        draw_glyph(p, QRectF(secr.left() + 4, 0, 18, self.height()), glyph, th.c(token), 12)
        if label:
            p.setPen(th.c(token))
            p.drawText(QRectF(secr.left() + 26, 0, secr.width() - 26, self.height()), Qt.AlignmentFlag.AlignVCenter,
                       label)
        x = secr.right() + 6
        url = QUrl(tab.url)
        if suspicious_idn(url):
            host = url.host(QUrl.ComponentFormattingOption.FullyEncoded)   # show the raw xn-- form
        else:
            host = strip_www(url.host())
        rest = url.toString(QUrl.UrlFormattingOption.RemoveScheme | QUrl.UrlFormattingOption.RemoveAuthority)
        if not host:
            host, rest = url.toDisplayString(), ""
        if url.port() != -1:
            host += f":{url.port()}"
        avail = self.width() - x - 72
        fm = p.fontMetrics()
        host_w = min(fm.horizontalAdvance(host), avail)
        p.setPen(th.c("text"))
        p.drawText(QRectF(x, 0, host_w, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(host, Qt.TextElideMode.ElideMiddle, int(avail)))
        if rest and rest != "/" and avail - host_w > 30:
            p.setPen(th.c("text3"))
            p.drawText(QRectF(x + host_w, 0, avail - host_w, self.height()), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(rest, Qt.TextElideMode.ElideRight, int(avail - host_w)))
        starred = self.ctx.bookmarks.find_url(tab.url) is not None
        draw_glyph(p, self._star_rect(), "star_fill" if starred else "star",
                   th.c("accent") if starred else (th.c("text") if self._hover_zone == "star" else th.c("text3")), 13)
        p.end()

    def _paint_shield(self, p: QPainter) -> None:
        th = theme()
        r = self._shield_rect()
        if self._hover_zone == "shield":
            hp = QPainterPath()
            hp.addRoundedRect(r.adjusted(2, 1, -2, -1), 7, 7)
            p.fillPath(hp, th.c("pressed"))
        color = th.c("warning") if not self._protected else (
            th.c("text") if self._hover_zone == "shield" else th.c("text3"))
        draw_glyph(p, r, "shield", color, 13)
        if self._blocked and self._protected:
            p.save()
            f = QFont(self.font())
            f.setPixelSize(8)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            text = str(self._blocked) if self._blocked < 100 else "99+"
            w = max(12, QFontMetrics(f).horizontalAdvance(text) + 6)
            br = QRectF(r.center().x() + 1, r.top() + 1, w, 11)
            bp = QPainterPath()
            bp.addRoundedRect(br, 5.5, 5.5)
            p.fillPath(bp, th.c("accent"))
            p.setPen(th.accent_text())
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, text)
            p.restore()


class UpdateChip(QAbstractButton):
    """Accent pill on the ribbon that appears when a new JBrowser version is available."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("A new version of JBrowser is available")
        self._hover = False
        f = QFont(self.font())
        f.setWeight(QFont.Weight.Medium)
        self.setFont(f)
        self.setFixedSize(QFontMetrics(f).horizontalAdvance("Update") + 44, BTN - 4)
        self.hide()

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
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, th.accent_alpha(0.32 if self._hover else 0.22))
        p.setPen(QPen(th.accent_alpha(0.6), 1))
        p.drawPath(path)
        draw_glyph(p, QRectF(r.left() + 8, r.top(), 16, r.height()), "download", th.c("accent"), 11)
        p.setPen(th.c("text"))
        p.drawText(QRectF(r.left() + 28, r.top(), r.width() - 34, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   "Update")
        p.end()


class GalleryButton(QAbstractButton):
    """Labelled "Gallery" pill on the ribbon; highlighted while the Gallery is open."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Gallery: see every card at a glance (Ctrl+Shift+G)")
        self.setAccessibleName("Gallery")
        self._hover = False
        self.setFixedSize(QFontMetrics(self.font()).horizontalAdvance("Gallery") + 42, BTN)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def nextCheckState(self) -> None:
        pass                               # the Gallery itself reports whether it is open

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.isChecked():
            p.fillPath(path, th.c("accent"))
            fg = th.accent_text()
        else:
            if self._hover or self.isDown():
                p.fillPath(path, th.c("pressed" if self.isDown() else "hover"))
            fg = th.c("text")
        draw_glyph(p, QRectF(r.left() + 8, r.top(), 16, r.height()), "gallery", fg, 12)
        p.setPen(fg)
        p.drawText(QRectF(r.left() + 28, r.top(), r.width() - 32, r.height()), Qt.AlignmentFlag.AlignVCenter, "Gallery")
        p.end()


class WidthButton(QAbstractButton):
    """Ribbon button showing the selected card's width; click to pick 20% to full width (Alt+2 … Alt+0)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Card width")
        self._hover = False
        self._label = ""
        f = QFont(self.font())
        f.setWeight(QFont.Weight.Medium)
        self._font = f
        # Always as wide as "100%", so the address bar doesn't move when the width changes.
        self.setFixedSize(BTN + QFontMetrics(f).horizontalAdvance("100%") + 2, BTN)

    def set_width(self, frac: float | None) -> None:
        label = "" if frac is None else f"{round(frac * 100)}%"
        if label != self._label:
            self._label = label
            self.update()
        self.setEnabled(frac is not None)
        self.setToolTip("Card width: 20% to full width (Alt+2 … Alt+0)" if frac is not None else
                        "Card width: open a card first")

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
        if self.isEnabled() and (self._hover or self.isDown()):
            bg = QPainterPath()
            bg.addRoundedRect(r, 7, 7)
            p.fillPath(bg, th.c("pressed" if self.isDown() else "hover"))
        fg = th.c("text3") if not self.isEnabled() else th.c("text") if self._hover else th.c("text2")
        # Two bars with a double-headed arrow between them: "as wide as".
        cx, cy = r.left() + 14, r.center().y()
        pen = QPen(fg, 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(cx - 7, cy - 5), QPointF(cx - 7, cy + 5))
        p.drawLine(QPointF(cx + 7, cy - 5), QPointF(cx + 7, cy + 5))
        p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        for side in (-1, 1):
            tip = cx + 4 * side
            p.drawLine(QPointF(tip, cy), QPointF(tip - 2.6 * side, cy - 2.6))
            p.drawLine(QPointF(tip, cy), QPointF(tip - 2.6 * side, cy + 2.6))
        if self._label:
            p.setFont(self._font)
            p.setPen(fg)
            p.drawText(QRectF(r.left() + 25, r.top(), r.width() - 27, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.end()


class DownloadsButton(QAbstractButton):
    """Ribbon Downloads button. While files download it widens to show the percentage over a progress bar."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Downloads")
        self._hover = False
        self._fraction: float | None = None    # None: nothing downloading · <0: size unknown
        self._dot: str | None = None            # colour token of the corner dot (warning / accent)
        self._phase = 0.0                       # moving segment when the size is unknown
        self._spin = QTimer(self)
        self._spin.setInterval(33)
        self._spin.timeout.connect(self._step)
        f = QFont(self.font())
        f.setWeight(QFont.Weight.DemiBold)
        f.setPointSizeF(max(7.0, f.pointSizeF() - 0.5))
        self._font = f
        self._wide = BTN + QFontMetrics(f).horizontalAdvance("100%") + 6
        self.setFixedSize(BTN, BTN)

    def set_state(self, fraction: float | None, dot: str | None) -> bool:
        """Returns True when the button changed width (the ribbon then re-centres the address bar)."""
        self._fraction, self._dot = fraction, dot
        wanted = self._wide if fraction is not None else BTN
        resized = wanted != self.width()
        if resized:
            self.setFixedSize(wanted, BTN)
        if fraction is not None and fraction < 0 and self.isVisible():
            self._spin.start()
        else:
            self._spin.stop()
        self.update()
        return resized

    def _step(self) -> None:
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    def hideEvent(self, e) -> None:
        self._spin.stop()
        super().hideEvent(e)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self._fraction is not None and self._fraction < 0:
            self._spin.start()

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
        if self._hover or self.isDown():
            bg = QPainterPath()
            bg.addRoundedRect(r, 7, 7)
            p.fillPath(bg, th.c("pressed" if self.isDown() else "hover"))
        fg = th.c("text") if self._hover else th.c("text2")
        frac = self._fraction
        if frac is None:
            draw_glyph(p, QRectF(self.rect()), "download", fg, 14)
        else:
            draw_glyph(p, QRectF(r.left() + 2, 0, BTN - 6, self.height() - 3), "download", th.c("accent"), 13)
            p.setFont(self._font)
            p.setPen(th.c("text"))
            label = f"{int(frac * 100)}%" if frac >= 0 else "…"
            p.drawText(QRectF(r.left() + BTN - 6, 0, r.width() - BTN + 4, self.height() - 3),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            track = QRectF(r.left() + 6, r.bottom() - 4, r.width() - 12, 3)
            tp = QPainterPath()
            tp.addRoundedRect(track, 1.5, 1.5)
            p.fillPath(tp, th.c("divider"))
            if frac >= 0:
                fill = QRectF(track.left(), track.top(), max(3.0, track.width() * min(1.0, frac)), track.height())
            else:                                   # unknown size: a segment slides along the track
                seg = track.width() * 0.3
                fill = QRectF(track.left() + (track.width() - seg) * self._phase, track.top(), seg, track.height())
            fp = QPainterPath()
            fp.addRoundedRect(fill, 1.5, 1.5)
            p.fillPath(fp, th.c("accent"))
        if self._dot:
            d = QPainterPath()
            d.addEllipse(QRectF(self.width() - 11, 4, 7, 7))
            p.fillPath(d, th.c(self._dot))
        p.end()


def _group(parent: QWidget, *buttons: QWidget) -> QWidget:
    """A tight cluster of related buttons (like Chrome's toolbar sections)."""
    box = QWidget(parent)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for b in buttons:
        b.setParent(box)
        lay.addWidget(b)
    box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return box


class TitleBar(QWidget):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.ui = ui
        self.setFixedHeight(TITLE_H)
        self.setProperty("dragRegion", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(0)
        self.back = IconButton("back", "Back (Ctrl+[)", self, size=BTN, glyph_px=13)
        self.forward = IconButton("forward", "Forward (Ctrl+])", self, size=BTN, glyph_px=13)
        self.reload = IconButton("refresh", "Reload (F5)", self, size=BTN, glyph_px=13)
        self.home = IconButton("home", "Home (Alt+Home)", self, size=BTN, glyph_px=13)
        self.home.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.home.customContextMenuRequested.connect(lambda pos: ui.show_home_menu(self.home.mapToGlobal(pos)))
        self.nav_group = _group(self, self.back, self.forward, self.reload, self.home)
        lay.addWidget(self.nav_group)
        lay.addStretch(1)
        # The address pill is not in the layout: it is centred on the ribbon in _place_pill().
        self.pill = AddressPill(ctx, self)
        # Stacking and layouts share one button: click to stack a card below, right-click for layouts.
        self.stack_btn = IconButton("stack", "Stack a card below this one (Alt+Shift+S)\n"
                                    "Right-click for layouts and split views", self, size=BTN, glyph_px=14)
        self.stack_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reading_btn = IconButton("reading", "Reading mode (F9)", self, size=BTN, glyph_px=14, checkable=True)
        self.width_btn = WidthButton(self)
        self.downloads = DownloadsButton(self)
        self.downloads.setToolTip("Downloads (Ctrl+J)")
        self.menu_btn = IconButton("more", "Menu", self, size=BTN, glyph_px=14)
        self.update_chip = UpdateChip(self)
        self.update_chip.clicked.connect(ui.show_update_dialog)
        self.gallery_btn = GalleryButton(self)
        self.gallery_btn.clicked.connect(lambda: ui.toggle_gallery())
        self.tool_group = _group(self, self.update_chip, self.gallery_btn, self.width_btn, self.stack_btn,
                                 self.reading_btn, self.downloads, self.menu_btn)
        lay.addWidget(self.tool_group)
        lay.addSpacing(12)
        self.min_btn = IconButton("min", "Minimize", self, size=TITLE_H, glyph_px=9, width=46)
        self.max_btn = IconButton("max", "Maximize", self, size=TITLE_H, glyph_px=9, width=46)
        self.close_btn = IconButton("close", "Close", self, size=TITLE_H, glyph_px=9, width=46, variant="close")
        self.window_group = _group(self, self.min_btn, self.max_btn, self.close_btn)
        lay.addWidget(self.window_group)

        self.back.clicked.connect(lambda: ui.nav("back"))
        self.forward.clicked.connect(lambda: ui.nav("forward"))
        self.reload.clicked.connect(lambda: ui.nav("reload_or_stop"))
        self.home.clicked.connect(ui.go_home)
        self.pill.clicked.connect(lambda: ui.open_lazy_toolbar("edit"))
        self.pill.spaceClicked.connect(ui.show_spaces_menu)
        self.pill.starClicked.connect(ui.toggle_bookmark)
        self.pill.securityClicked.connect(lambda pos: ui.show_site_info(None, pos))
        self.pill.shieldClicked.connect(lambda pos: ui.show_shield_menu(None, pos))
        self.stack_btn.clicked.connect(lambda: ui.open_stack_picker())
        self.stack_btn.customContextMenuRequested.connect(lambda _pos: ui.show_layout_menu(
            self.stack_btn.mapToGlobal(QPoint(0, self.stack_btn.height()))))
        self.reading_btn.clicked.connect(lambda: ui.toggle_reading())
        self.width_btn.clicked.connect(lambda: ui.show_width_menu(self.width_btn.mapToGlobal(
            QPoint(0, self.width_btn.height()))))
        self.downloads.clicked.connect(lambda: ctx.commands.run("downloads.show"))
        self.menu_btn.clicked.connect(lambda: ui.show_main_menu(self.menu_btn.mapToGlobal(
            QPoint(self.menu_btn.width(), self.menu_btn.height()))))
        self.min_btn.clicked.connect(ui.minimize)
        self.max_btn.clicked.connect(ui.toggle_maximize)
        self.close_btn.clicked.connect(lambda: self.window().close())

        st = ctx.state
        st.activeTabChanged.connect(lambda *_: self.refresh())
        st.activeSpaceChanged.connect(lambda *_: self.refresh())
        st.spaceUpdated.connect(lambda *_: self.refresh())
        for sig in (st.tabAdded, st.tabRemoved, st.tabMoved):
            sig.connect(lambda *_: self._refresh_stack())
        ctx.pipeline.flushed.connect(self._on_flush)
        ctx.bookmarks.changed.connect(self.pill.update)
        dl = ctx.downloads
        for sig in (dl.activeCountChanged, dl.updated, dl.added, dl.removed):
            sig.connect(lambda *_: self._on_downloads())
        ctx.settings.changed.connect(self._on_setting)
        ctx.updater.stateChanged.connect(self._on_update_state)
        self._apply_home()
        self._apply_tools()
        self.refresh()
        self._on_downloads()

    def _on_update_state(self, state: str) -> None:
        info = self.ctx.updater.latest
        show = state in ("available", "downloading", "ready") and info is not None
        if show != self.update_chip.isVisible():
            self.update_chip.setVisible(show)
            if info is not None:
                self.update_chip.setToolTip(f"JBrowser {info.version} is available. Click to see what's new")
            self.tool_group.adjustSize()
            self._place_pill()

    def _on_setting(self, key: str, _value) -> None:
        if key.startswith("privacy."):
            self.refresh()
        elif key.startswith("toolbar.home"):
            self._apply_home()
        elif key == "toolbar.downloads_button":
            self._on_downloads()
        elif key in ("toolbar.width_button", "toolbar.reading_button"):
            self._apply_tools()

    def _apply_tools(self) -> None:
        """The optional ribbon buttons: card width (shown by default) and reading mode (hidden by default;
        every card's header has its own)."""
        s = self.ctx.settings
        self.width_btn.setVisible(bool(s.get("toolbar.width_button")))
        self.reading_btn.setVisible(bool(s.get("toolbar.reading_button")))
        self.tool_group.adjustSize()
        QTimer.singleShot(0, self._place_pill)

    def _apply_home(self) -> None:
        s = self.ctx.settings
        self.home.setVisible(bool(s.get("toolbar.home_button")))
        url = s.get("toolbar.home_url") or ""
        self.home.setToolTip("Home: open the Lazy Toolbar (Alt+Home)" if s.get("toolbar.home_mode") != "url" or not url
                             else f"Home: {url} (Alt+Home)")
        self.nav_group.adjustSize()
        QTimer.singleShot(0, self._place_pill)

    # ------------------------------------------------------------- layout
    def _place_pill(self) -> None:
        w = self.width()
        left = 8 + self.nav_group.sizeHint().width() + 12
        right = w - self.window_group.sizeHint().width() - 12 - self.tool_group.sizeHint().width() - 12
        pw = int(max(PILL_MIN, min(PILL_MAX, w * 0.46)))
        pw = max(160, min(pw, right - left))
        x = int(round((w - pw) / 2))
        x = max(left, min(x, right - pw))
        self.pill.setGeometry(x, (TITLE_H - self.pill.height()) // 2, pw, self.pill.height())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._place_pill()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._place_pill()

    def contextMenuEvent(self, e) -> None:
        self.ui.show_ribbon_menu(e.globalPos())

    def _on_flush(self, summary: dict) -> None:
        tab = self.ctx.state.active_tab
        if tab is not None and tab.id in summary:
            self.refresh()
            if summary[tab.id] & {"stack", "pinned"}:
                self._refresh_stack()

    def refresh(self) -> None:
        tab = self.ctx.state.active_tab
        self.pill.set_tab(tab)
        self.back.setEnabled(bool(tab and tab.can_back))
        self.forward.setEnabled(bool(tab and tab.can_forward))
        self.reload.setEnabled(tab is not None)
        loading = bool(tab and tab.loading)
        self.reload.set_glyph("stop" if loading else "refresh")
        self.reload.setToolTip("Stop (Esc)" if loading else "Reload (F5)")
        protected = bool(self.ctx.settings.get("privacy.block_trackers"))
        if tab is not None and QUrl(tab.url).host() and self.ctx.privacy.is_allowlisted(QUrl(tab.url).host()):
            protected = False
        self.pill.set_shield(tab.blocked if tab else 0, protected)
        reading = bool(tab and tab.reading)
        readable = bool(tab and tab.readable)
        self.reading_btn.setChecked(reading)
        self.reading_btn.setEnabled(bool(tab and tab.url.startswith(("http://", "https://")) and not tab.sleeping))
        # Off by default; the glyph turns to the accent colour when the page is an article.
        self.reading_btn.set_active_color("accent" if readable and not reading else None)
        self.reading_btn.setToolTip("Leave reading mode (F9)" if reading else
                                    "Reading mode (F9): this page looks like an article" if readable else
                                    "Reading mode (F9): works best on articles and other pages with lots of text")
        self.width_btn.set_width(tab.width if tab is not None else None)
        self._refresh_stack()

    def _refresh_stack(self) -> None:
        # Always clickable: when stacking isn't possible, the click explains why (BrowserController).
        tab = self.ctx.state.active_tab
        if tab is not None and tab.pinned:
            tip = "Pinned cards can't be stacked"
        elif tab is not None and not self.ui.can_stack():
            tip = "This column is full (3 cards at most)"
        else:
            tip = "Stack a card below this one (Alt+Shift+S)"
        self.stack_btn.setToolTip(tip + "\nRight-click for layouts and split views")

    def _on_downloads(self) -> None:
        dl = self.ctx.downloads
        active = dl.active_items()
        mode = self.ctx.settings.get("toolbar.downloads_button")
        show = mode == "always" or bool(active or dl.session_items() or dl.waiting_items())
        if active:
            sized = [i for i in active if i.record.total > 0]
            fraction = dl.overall_progress() if sized else -1.0
        else:
            fraction = None
        dot = "warning" if dl.waiting_items() else ("accent" if dl.unseen else None)
        resized = self.downloads.set_state(fraction, dot)
        n = len(active)
        tip = "Downloads (Ctrl+J)"
        if n:
            tip = f"Downloading {n} file{'s' if n != 1 else ''}" + (
                f": {int(fraction * 100)}% done" if fraction is not None and fraction >= 0 else "") + " (Ctrl+J)"
        if dl.waiting_items():
            tip += "\nA download needs your decision: keep or delete it"
        self.downloads.setToolTip(tip)
        if show == self.downloads.isHidden() or resized:
            self.downloads.setVisible(show)
            self.tool_group.adjustSize()
            self._place_pill()

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.set_glyph("restore" if maximized else "max")
        self.max_btn.setToolTip("Restore" if maximized else "Maximize")

    def sizeHint(self) -> QSize:
        return QSize(800, TITLE_H)
