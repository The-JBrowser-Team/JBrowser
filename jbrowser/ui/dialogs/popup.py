"""Script-opened popup windows (window.open with features — OAuth / payment flows).

They share the opener's profile so sign-ins flow back to the originating space, and keep
the window.opener relationship intact because the page is created by the engine request.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRect, Qt, QTimer, QUrl
from PyQt6.QtGui import QPainter
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jbrowser.core.urls import pretty_url
from jbrowser.engine.signin import is_rejection_url
from jbrowser.models.space import Space
from jbrowser.services.privacy import PageInterceptor
from jbrowser.ui.backdrop import Backdrop
from jbrowser.ui.icons import app_icon, draw_glyph
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController


class PopupPage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile, popup: "PopupWindow"):
        super().__init__(profile, popup)
        self._popup = popup

    def createWindow(self, window_type):
        return self._popup.ctx.hooks.create_popup(self.profile(), self._popup.space)

    def acceptNavigationRequest(self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main: bool) -> bool:
        # "Sign in with Google" popups: present Firefox before the sign-in page loads (engine/signin.py).
        if not self._popup.ctx.profiles.signin.before_navigation(self, url, is_main):
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main)


class PopupWindow(QWidget):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", profile: QWebEngineProfile, space: Space):
        super().__init__(None, Qt.WindowType.Window)
        self.ctx = ctx
        self.ui = ui
        self.space = space
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.backdrop = Backdrop(self, "frame")      # light/dark title bar in step with the theme
        self.setWindowIcon(app_icon())
        self.setWindowTitle("JBrowser popup")
        self.resize(560, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget(self)
        bar.setFixedHeight(38)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 0, 4, 0)
        self._lock = QLabel(bar)
        self._lock.setFixedSize(18, 18)
        self.address = QLabel(bar)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        promote = IconButton("newwindow", "Open as a card in this space", bar, size=30, glyph_px=12)
        promote.clicked.connect(self._promote)
        bl.addWidget(self._lock)
        bl.addWidget(self.address, 1)
        bl.addWidget(promote)
        lay.addWidget(bar)
        # Google refused the sign-in: the same fix as in cards (TabController._offer_signin_fix).
        self.fix_bar = QWidget(self)
        fl = QHBoxLayout(self.fix_bar)
        fl.setContentsMargins(12, 6, 8, 6)
        msg = QLabel("Google couldn't sign you in with this browser. JBrowser can fix this.", self.fix_bar)
        msg.setWordWrap(True)
        fix = QPushButton("Fix and sign in again", self.fix_bar)
        fix.setProperty("primary", True)
        fix.clicked.connect(self._fix_signin)
        fl.addWidget(msg, 1)
        fl.addWidget(fix)
        self.fix_bar.hide()
        lay.addWidget(self.fix_bar)
        self.view = QWebEngineView(self)
        self.page = PopupPage(profile, self)
        self._interceptor = PageInterceptor(ctx.privacy, lambda _h: None, self)
        self.page.setUrlRequestInterceptor(self._interceptor)
        self.view.setPage(self.page)
        lay.addWidget(self.view, 1)
        self.page.urlChanged.connect(self._on_url)
        ctx.profiles.signin.watch(self.page)
        self.page.titleChanged.connect(lambda t: self.setWindowTitle(f"{t} · {space.name}" if t else "JBrowser popup"))
        self.page.windowCloseRequested.connect(self.close)
        self.page.geometryChangeRequested.connect(self._on_geometry)
        self.page.iconChanged.connect(lambda ic: self.setWindowIcon(ic if not ic.isNull() else app_icon()))
        self._bar = bar

    def _on_url(self, url: QUrl) -> None:
        self.fix_bar.setVisible(is_rejection_url(url) and self.ctx.settings.get("advanced.identity") != "firefox")
        self.address.setText(pretty_url(url))
        self.address.setToolTip(url.toString())
        self._secure = url.scheme() == "https"
        self._bar.update()
        self._lock.update()

    def _fix_signin(self) -> None:
        self.fix_bar.hide()
        self.ctx.profiles.start_signin_fix()
        h = self.page.history()
        start = h.itemAt(0).url() if h.count() else QUrl()
        # Start the sign-in again from the page that opened this window's flow (the site's "Sign in with
        # Google" address), so the site still receives the result.
        QTimer.singleShot(0, lambda u=start: self.page.setUrl(u if u.isValid() and not u.isEmpty()
                                                              else QUrl("https://accounts.google.com/")))

    def _on_geometry(self, rect: QRect) -> None:
        if rect.width() > 100 and rect.height() > 100:
            self.resize(rect.width(), rect.height() + self._bar.height())

    def _promote(self) -> None:
        url = self.page.url()
        if url.isValid() and not url.isEmpty():
            self.ui.open_url(url, "new", space_id=self.space.id)
        self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme().c("dialog_solid"))
        secure = getattr(self, "_secure", False)
        draw_glyph(p, self._lock.geometry().toRectF(), "lock" if secure else "warning",
                   theme().c("text2") if secure else theme().c("warning"), 12)
        p.end()

    def closeEvent(self, e) -> None:
        # WA_DeleteOnClose destroys children in creation order: the view before its page.
        self.page.windowCloseRequested.disconnect()
        super().closeEvent(e)
