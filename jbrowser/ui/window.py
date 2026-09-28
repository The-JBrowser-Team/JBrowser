"""MainWindow: frameless-looking Windows 11 window hosting sidebar, title bar and canvases."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor, QGuiApplication, QPainter
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow, QSystemTrayIcon, QVBoxLayout, QWidget)

from jbrowser import APP_NAME
from jbrowser.context import AppContext, UiHooks
from jbrowser.platform import win
from jbrowser.ui.actions import register_commands
from jbrowser.ui.canvas import SpaceStack
from jbrowser.ui.card import WebCard
from jbrowser.ui.controller import BrowserController
from jbrowser.ui.favorites_bar import FavoritesBar
from jbrowser.ui.hotkeys import HotkeySheet
from jbrowser.ui.icons import app_icon
from jbrowser.ui.lazy_toolbar import LazyToolbar
from jbrowser.ui.sidebar import PEEK_EDGE, Sidebar
from jbrowser.ui.theme import theme
from jbrowser.ui.titlebar import TitleBar
from jbrowser.ui.widgets import ToastManager

log = logging.getLogger(__name__)


class RootWidget(QWidget):
    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        if th.translucent:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        else:
            p.fillRect(self.rect(), th.c("window"))
        p.end()


class WindowHooks(UiHooks):
    """UI services the engine layer may request (dialogs, popups, notifications)."""

    def __init__(self, window: "MainWindow"):
        self.win = window
        self.popups: list = []
        self._notifications: list = []
        self._tray: QSystemTrayIcon | None = None

    def ask_credentials(self, title: str, message: str):
        from jbrowser.ui.dialogs.auth import ask_credentials
        return ask_credentials(self.win, title, message)

    def unlock_vault(self) -> bool:
        return self.win.ui.unlock_vault()

    def create_popup(self, profile, space):
        from jbrowser.ui.dialogs.popup import PopupWindow
        popup = PopupWindow(self.win.ctx, self.win.ui, profile, space)
        self.popups.append(popup)
        popup.destroyed.connect(lambda *_a, p=popup: self.popups.remove(p) if p in self.popups else None)
        popup.show()
        return popup.page

    def close_popups(self) -> None:
        for p in list(self.popups):
            p.close()

    def toast(self, text: str, icon: str = "info") -> None:
        self.win.toasts.show(text, icon)

    def notify(self, notification) -> None:
        self._notifications.append(notification)
        notification.closed.connect(lambda n=notification: self._notifications.remove(n)
                                    if n in self._notifications else None)
        notification.show()
        origin = notification.origin().host()
        title = notification.title() or origin
        self.win.toasts.show(f"{title}: {notification.message()}"[:140], "ringer", 5000)
        if not self.win.isActiveWindow():
            if self._tray is None:
                self._tray = QSystemTrayIcon(app_icon(), self.win)
                self._tray.messageClicked.connect(self._tray_clicked)
            self._tray.show()
            self._tray.showMessage(f"{title} · {origin}", notification.message(),
                                   QSystemTrayIcon.MessageIcon.Information, 6000)
            self._last_notification = notification
            QTimer.singleShot(9000, lambda: self._tray.hide() if self._tray else None)

    def _tray_clicked(self) -> None:
        self.win.showNormal() if self.win.isMinimized() else None
        self.win.raise_()
        self.win.activateWindow()
        n = getattr(self, "_last_notification", None)
        if n is not None:
            try:
                n.click()
            except RuntimeError:
                pass


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.was_maximized = False
        self._immersive: tuple | None = None
        self._backdrop_done = False
        self._shut_down = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(760, 480)

        self.ui = BrowserController(ctx, self)
        self.hooks = WindowHooks(self)
        ctx.hooks = self.hooks

        root = RootWidget(self)
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar(ctx, self.ui, root)
        h.addWidget(self.sidebar)
        right = QWidget(root)
        v = QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.titlebar = TitleBar(ctx, self.ui, right)
        self.favbar = FavoritesBar(ctx, self.ui, right)
        self.stack = SpaceStack(ctx, self.ui, right)
        v.addWidget(self.titlebar)
        v.addWidget(self.favbar)
        v.addWidget(self.stack, 1)
        h.addWidget(right, 1)
        self.right = right

        self.lazy = LazyToolbar(ctx, self.ui, root)
        self.hotkeys = HotkeySheet(ctx, root)
        self.toasts = ToastManager(root)

        register_commands(ctx, self.ui)
        ctx.commands.install_shortcuts(self)

        mb = self.titlebar.max_btn
        self.native = win.NativeFrame(lambda: int(self.winId()), self.devicePixelRatioF, self._hit_test,
                                      mb.set_force_hover, mb.set_force_pressed, self.ui.toggle_maximize)
        self.native.resizable = lambda: not self.isFullScreen() and self._immersive is None
        self.native.on_caption_menu = self._on_caption_menu
        self._onboarding = None
        self._peek_timer = QTimer(self)
        self._peek_timer.setSingleShot(True)
        self._peek_timer.setInterval(140)
        self._peek_timer.timeout.connect(self._maybe_peek)

        th = theme()
        th.changed.connect(self.apply_backdrop)
        lc = ctx.lifecycle
        lc.aboutToThrottle.connect(self._on_about_to_throttle)
        lc.aboutToSleep.connect(self._on_about_to_sleep)
        lc.woke.connect(self._on_woke)
        lc.sleepBlocked.connect(self.ui.on_sleep_blocked)
        ctx.downloads.window_provider = lambda: self
        ctx.downloads.confirm_dangerous = self.ui.confirm_dangerous_download
        ctx.updater.available.connect(self.ui.on_update_available)
        ctx.downloads.added.connect(self._on_download_added)
        ctx.downloads.finished.connect(lambda item: self.toasts.show(f"Downloaded {item.record.filename}", "check"))
        ctx.privacy.blocklistUpdated.connect(self._on_blocklist)
        ctx.dns.applied.connect(self._on_dns)
        app = QApplication.instance()
        app.installEventFilter(self)
        app.focusChanged.connect(self._on_focus_changed)
        self._restore_geometry()

    # ------------------------------------------------------------- geometry
    def _restore_geometry(self) -> None:
        geo = self.ctx.settings.get("window.geometry")
        screens = [s.availableGeometry() for s in QGuiApplication.screens()]
        if isinstance(geo, list) and len(geo) == 4:
            rect = QRect(*[int(v) for v in geo])
            if any(s.intersects(rect) for s in screens) and rect.width() >= 600 and rect.height() >= 400:
                self.setGeometry(rect)
                return
        avail = QGuiApplication.primaryScreen().availableGeometry()
        w, h = int(avail.width() * 0.82), int(avail.height() * 0.86)
        self.setGeometry(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2, w, h)

    def show_restored(self) -> None:
        if self.ctx.settings.get("window.maximized"):
            self.showMaximized()
        else:
            self.show()

    # ------------------------------------------------------------- backdrop
    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self._backdrop_done:
            self._backdrop_done = True
            self.apply_backdrop()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WinIdChange and self._backdrop_done:
            # The native window was recreated (e.g. surface type change): DWM state is per-HWND.
            QTimer.singleShot(0, self.apply_backdrop)
        return super().event(e)

    def apply_backdrop(self) -> None:
        if not self._backdrop_done:
            return
        hwnd = int(self.winId())
        material = self.ctx.settings.get("appearance.material")
        ok = win.apply_backdrop(hwnd, material, theme().dark)
        translucent = ok and material != "solid"
        if translucent != theme().translucent:
            theme().translucent = translucent
            theme().apply()
        win.refresh_frame(hwnd)
        self.update()

    # ----------------------------------------------------------- native frame
    def nativeEvent(self, event_type, message):
        # Note: do not chain to super().nativeEvent() — with PyQt6 6.11 that call crashes
        # inside the window procedure. Returning (False, 0) lets Qt handle the message.
        try:
            handled, result = self.native.handle(int(message))
        except Exception:  # never let an exception escape a window procedure
            log.exception("nativeEvent failed")
            return False, 0
        return (True, result) if handled else (False, 0)

    def _hit_test(self, local: QPoint) -> int:
        if self.isFullScreen() or self._immersive is not None:
            return win.HTCLIENT
        if self.lazy.isVisible() or self.hotkeys.isVisible():
            return win.HTCLIENT
        w = self.childAt(local)
        while w is not None and w.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents):
            w = w.parentWidget()
        if w is None:
            return win.HTCLIENT
        mb = self.titlebar.max_btn
        if w is mb:
            return win.HTMAXBUTTON
        if w.property("dragRegion"):
            return win.HTCAPTION
        return win.HTCLIENT

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())
            if self._immersive is None:
                fs = self.isFullScreen()
                self.sidebar.setVisible(not fs and not self.sidebar.hidden_mode)
                self.titlebar.setVisible(not fs)
                self.favbar.setVisible(not fs)
                if fs:
                    QTimer.singleShot(200, lambda: self.toasts.show("Press F11 to exit full screen", "fullscreen"))
            for c in self.stack.canvases.values():
                QTimer.singleShot(0, c.refresh_visibility)
            # Qt re-applies the saved window style when leaving full screen; force a new
            # WM_NCCALCSIZE so the native caption never reappears, and restore the backdrop.
            QTimer.singleShot(0, self._refresh_native_frame)
            QTimer.singleShot(250, self._refresh_native_frame)
        super().changeEvent(e)

    def _refresh_native_frame(self) -> None:
        if self._backdrop_done and not self._shut_down:
            win.refresh_frame(int(self.winId()))
            self.apply_backdrop()

    # ------------------------------------------------------------- lifecycle
    def _card(self, tab_id: str) -> WebCard | None:
        return self.ui.card(tab_id)

    def _on_about_to_throttle(self, tab_id: str) -> None:
        card = self._card(tab_id)
        if card is not None:
            card.take_snapshot()

    def _on_about_to_sleep(self, tab_id: str) -> None:
        card = self._card(tab_id)
        if card is not None:
            card.enter_sleep()

    def _on_woke(self, tab_id: str) -> None:
        card = self._card(tab_id)
        if card is not None:
            card.exit_sleep()

    def _on_download_added(self, item) -> None:
        self.toasts.show(f"Downloading {item.record.filename}", "download")
        ctrl = self.ctx.engine.controller(item.tab_id) if item.tab_id else None
        if ctrl is None:
            return

        def close_if_empty(tid=item.tab_id, url=item.record.url):
            c = self.ctx.engine.controller(tid)
            if c is None:
                return
            h = c.page.history()
            only_download = h.count() == 0 or (h.count() == 1 and c.page.url().toString() == url)
            title = c.page.title().strip()
            if only_download and (not title or title in url):
                self.ui.close_tab(tid, remember=False)

        # A card whose only navigation became a download would stay blank: close it.
        QTimer.singleShot(300, close_if_empty)

    def _on_blocklist(self, size: int, error: str) -> None:
        if not self.ctx.privacy.last_update_manual:
            return   # quiet weekly refresh
        if error:
            self.toasts.show("Some tracker lists could not be downloaded", "warning", 4000)
        self.toasts.show(f"Tracker protection ready: {size:,} rules", "shield")

    def _on_dns(self, mode: str, ok: bool) -> None:
        if not ok and mode != "system":
            self.toasts.show("Secure DNS could not be enabled in this Qt build", "warning", 4000)

    # --------------------------------------------------------- input routing
    @staticmethod
    def _card_of(widget) -> WebCard | None:
        w = widget
        while w is not None:
            if isinstance(w, WebCard):
                return w
            w = w.parentWidget() if isinstance(w, QWidget) else None
        return None

    def eventFilter(self, obj, ev) -> bool:
        t = ev.type()
        if t == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow() and \
                obj.windowType() in (Qt.WindowType.Popup, Qt.WindowType.ToolTip):
            # Native Windows 11 rounded corners + border for menus, combo popups and tooltips.
            win.set_corner_preference(int(obj.winId()), 3 if obj.windowType() == Qt.WindowType.ToolTip else 2)
            return False
        if t == QEvent.Type.Wheel and isinstance(obj, QWidget) and \
                ev.modifiers() & Qt.KeyboardModifier.AltModifier and obj.window() is self:
            canvas = self.stack.current()
            if canvas is not None and (canvas is obj or canvas.isAncestorOf(obj)):
                canvas.pan_from_wheel(ev)
                return True
        elif t == QEvent.Type.MouseMove and self.sidebar.hidden_mode and not self.sidebar.floating \
                and self._onboarding is None and self._immersive is None and isinstance(obj, QWidget) \
                and obj.window() is self:
            near = ev.globalPosition().x() - self.mapToGlobal(QPoint(0, 0)).x() <= PEEK_EDGE
            if near and not self._peek_timer.isActive():
                self._peek_timer.start()
            elif not near:
                self._peek_timer.stop()
        elif t == QEvent.Type.MouseButtonPress and isinstance(obj, QWidget) and obj.window() is self:
            btn = ev.button()
            card = self._card_of(obj)
            if card is not None and btn in (Qt.MouseButton.BackButton, Qt.MouseButton.ForwardButton):
                card.ctrl.back() if btn == Qt.MouseButton.BackButton else card.ctrl.forward()
                return True
            if card is not None and card.stack.isAncestorOf(obj) and not card.tab.sleeping:
                if self.ctx.state.active_space_id == card.tab.space_id and \
                        self.ctx.state.active_space.active_tab_id != card.tab.id:
                    self.ctx.state.set_active_tab(card.tab.id)
        return False

    def _on_focus_changed(self, _old, new) -> None:
        if new is None or not isinstance(new, QWidget) or new.window() is not self:
            return
        card = self._card_of(new)
        if card is None or card.tab.disposed:
            return
        st = self.ctx.state
        space = st.space_of(card.tab)
        if space is not None and space.id == st.active_space_id and space.active_tab_id != card.tab.id:
            st.set_active_tab(card.tab.id)

    # ------------------------------------------------------------- sidebar
    def _maybe_peek(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        if 0 <= local.y() <= self.height() and local.x() <= PEEK_EDGE and self.sidebar.hidden_mode:
            self.sidebar.peek()

    def _on_caption_menu(self) -> None:
        pos = QCursor.pos()
        w = self.childAt(self.mapFromGlobal(pos))
        if w is not None and (w is self.sidebar or self.sidebar.isAncestorOf(w)):
            self.ui.show_sidebar_menu(pos)
        elif self._onboarding is None:
            self.ui.show_ribbon_menu(pos)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.sidebar.floating:
            self.sidebar.host_resized(self.centralWidget().height())

    # ------------------------------------------------------------ welcome
    def start_onboarding(self, replay: bool = False) -> None:
        if self._onboarding is not None:
            return
        from jbrowser.ui.onboarding import Onboarding
        if self.lazy.isVisible():
            self.lazy.close_overlay()
        if self.hotkeys.isVisible():
            self.hotkeys.close_overlay()
        if self._immersive is not None:
            self.exit_immersive()
        if self.sidebar.floating:
            self.sidebar._end_peek(immediate=True)
        ob = Onboarding(self, replay)
        self._onboarding = ob
        self.ctx.commands.set_shortcuts_enabled(False)
        ob.finished.connect(self._onboarding_done)
        ob.start()

    def _onboarding_done(self) -> None:
        self._onboarding = None
        self.ctx.commands.set_shortcuts_enabled(True)
        space = self.ctx.state.active_space
        if space is not None and not space.tabs:
            QTimer.singleShot(200, lambda: self.ui.open_lazy_toolbar("new"))
        else:
            QTimer.singleShot(0, self.ui.focus_active_card)

    # ------------------------------------------------------------ immersive
    def enter_immersive(self, card: WebCard) -> None:
        if self._immersive is not None:
            return
        self._immersive = (card, self.isMaximized(), self.isFullScreen())
        self.sidebar.hide()
        self.titlebar.hide()
        self.favbar.hide()
        canvas = self.stack.canvas(card.tab.space_id)
        if canvas:
            canvas.set_solo(card.tab.id)
        card.set_immersive(True)
        self.showFullScreen()

    def exit_immersive(self) -> None:
        if self._immersive is None:
            return
        card, was_max, was_fs = self._immersive
        self._immersive = None
        try:
            card.set_immersive(False)
            canvas = self.stack.canvas(card.tab.space_id)
        except RuntimeError:
            canvas = None
        for c in self.stack.canvases.values():
            c.set_solo(None)
        if not self.sidebar.hidden_mode:
            self.sidebar.show()
        self.titlebar.show()
        self.favbar.show()
        if not was_fs:
            self.showMaximized() if was_max else self.showNormal()
        if canvas:
            QTimer.singleShot(50, lambda: canvas.ensure_visible(card.tab.id))

    # ---------------------------------------------------------------- close
    def closeEvent(self, e) -> None:
        if self._shut_down:
            e.accept()
            return
        s = self.ctx.settings
        if self._immersive is not None:
            self.exit_immersive()
        if not self.isMaximized() and not self.isFullScreen():
            g = self.geometry()
            s.set("window.geometry", [g.x(), g.y(), g.width(), g.height()])
        s.set("window.maximized", self.isMaximized())
        self.hooks.close_popups()
        for dlg in list(self.ui._dialogs.values()):
            try:
                dlg.close()
            except RuntimeError:
                pass
        self.ctx.save_all()
        self._shut_down = True
        QApplication.instance().removeEventFilter(self)
        # Tear down in dependency order: views → pages → profiles (see app.run()).
        for canvas in self.stack.canvases.values():
            for card in list(canvas.cards.values()):
                card.teardown()
            canvas.cards.clear()
        self.ctx.shutdown()
        e.accept()
        QApplication.instance().quit()
