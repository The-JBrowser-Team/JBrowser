"""Custom title bar: grouped navigation, the address pill, tools and window controls."""
from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QWidget

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

    def set_tab(self, tab: Tab | None) -> None:
        self.tab = tab
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

    def _zone(self, pos) -> str:
        if self._space_rect().contains(pos):
            return "space"
        if self.tab is not None and self.tab.url and self._security_rect().contains(pos):
            return "security"
        if self._star_rect().contains(pos) and self.tab is not None and self.tab.url:
            return "star"
        return "url"

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
        avail = self.width() - x - 42
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
        self.layout_btn = IconButton("columns", "Card layout and split views", self, size=BTN, glyph_px=14)
        self.shield = IconButton("shield", "Privacy protections", self, size=BTN, glyph_px=14)
        self.downloads = IconButton("download", "Downloads (Ctrl+J)", self, size=BTN, glyph_px=14)
        self.menu_btn = IconButton("more", "Menu", self, size=BTN, glyph_px=14)
        self.update_chip = UpdateChip(self)
        self.update_chip.clicked.connect(ui.show_update_dialog)
        self.gallery_btn = GalleryButton(self)
        self.gallery_btn.clicked.connect(lambda: ui.toggle_gallery())
        self.tool_group = _group(self, self.update_chip, self.gallery_btn, self.layout_btn, self.shield,
                                 self.downloads, self.menu_btn)
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
        self.layout_btn.clicked.connect(lambda: ui.show_layout_menu(self.layout_btn.mapToGlobal(
            QPoint(0, self.layout_btn.height()))))
        self.shield.clicked.connect(lambda: ui.show_shield_menu(None, self.shield.mapToGlobal(
            QPoint(0, self.shield.height()))))
        self.downloads.clicked.connect(lambda: ctx.commands.run("downloads.show"))
        self.menu_btn.clicked.connect(lambda: ui.show_main_menu(self.menu_btn.mapToGlobal(
            QPoint(self.menu_btn.width(), self.menu_btn.height()))))
        self.min_btn.clicked.connect(lambda: self.window().showMinimized())
        self.max_btn.clicked.connect(ui.toggle_maximize)
        self.close_btn.clicked.connect(lambda: self.window().close())

        st = ctx.state
        st.activeTabChanged.connect(lambda *_: self.refresh())
        st.activeSpaceChanged.connect(lambda *_: self.refresh())
        st.spaceUpdated.connect(lambda *_: self.refresh())
        ctx.pipeline.flushed.connect(self._on_flush)
        ctx.bookmarks.changed.connect(self.pill.update)
        ctx.downloads.activeCountChanged.connect(lambda *_: self._on_downloads())
        ctx.downloads.updated.connect(lambda *_: self._on_downloads())
        ctx.settings.changed.connect(self._on_setting)
        ctx.updater.stateChanged.connect(self._on_update_state)
        self._apply_home()
        self.refresh()

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

    def refresh(self) -> None:
        tab = self.ctx.state.active_tab
        self.pill.set_tab(tab)
        self.back.setEnabled(bool(tab and tab.can_back))
        self.forward.setEnabled(bool(tab and tab.can_forward))
        self.reload.setEnabled(tab is not None)
        loading = bool(tab and tab.loading)
        self.reload.set_glyph("stop" if loading else "refresh")
        self.reload.setToolTip("Stop (Esc)" if loading else "Reload (F5)")
        blocked = tab.blocked if tab else 0
        self.shield.set_badge(str(blocked) if blocked else None)
        protected = bool(self.ctx.settings.get("privacy.block_trackers"))
        if tab is not None and QUrl(tab.url).host() and self.ctx.privacy.is_allowlisted(QUrl(tab.url).host()):
            protected = False
        self.shield.set_active_color(None if protected else "warning")

    def _on_downloads(self) -> None:
        active = self.ctx.downloads.active_items()
        self.downloads.set_progress(self.ctx.downloads.overall_progress() if active else None)
        self.downloads.set_badge(str(len(active)) if len(active) > 1 else None)

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.set_glyph("restore" if maximized else "max")
        self.max_btn.setToolTip("Restore" if maximized else "Maximize")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme().c("titlebar"))
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(800, TITLE_H)
