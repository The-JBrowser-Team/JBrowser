"""QWebEnginePage subclass and the isolated-world bridge object."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSlot
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

from jbrowser.core.urls import EXTERNAL_SCHEMES, INTERNAL_SCHEMES

if TYPE_CHECKING:
    from jbrowser.engine.tab_controller import TabController

log = logging.getLogger(__name__)


class BrowserPage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile, controller: "TabController"):
        super().__init__(profile, controller)
        self._controller = controller

    def createWindow(self, window_type: QWebEnginePage.WebWindowType) -> QWebEnginePage | None:
        return self._controller.create_window(window_type)

    def acceptNavigationRequest(self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main: bool) -> bool:
        scheme = url.scheme().lower()
        if scheme and scheme not in INTERNAL_SCHEMES and (scheme in EXTERNAL_SCHEMES or is_main):
            self._controller.external_protocol(url)
            return False
        if scheme in ("http", "https") and self._controller.ctx.threats.match(url.host()):
            if is_main:
                # Chromium must not be asked to start a new navigation from inside this
                # callback (it aborts the process), so the interstitial loads a moment later.
                ctrl = self._controller
                QTimer.singleShot(0, lambda u=QUrl(url): None if ctrl.disposed else ctrl.show_threat(u))
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main)

    def javaScriptConsoleMessage(self, level, message: str, line: int, source: str) -> None:
        if log.isEnabledFor(logging.DEBUG):
            log.debug("console[%s] %s:%s %s", level, source, line, message)


class PageBridge(QObject):
    """Exposed as ``jbBridge`` over QWebChannel inside JBrowser's isolated script world."""

    def __init__(self, controller: "TabController"):
        super().__init__(controller)
        self._controller = controller

    @pyqtSlot(int)
    def loginFormDetected(self, count: int) -> None:
        self._controller.on_login_form(int(count))

    @pyqtSlot(str, str)
    def credentialsSubmitted(self, username: str, password: str) -> None:
        self._controller.on_credentials(username, password)
