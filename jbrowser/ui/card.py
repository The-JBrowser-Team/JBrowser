"""WebCard: a single web viewport living on the horizontal canvas."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

from jbrowser.core.urls import pretty_url
from jbrowser.models.infobar import InfoBarSpec
from jbrowser.models.tab import Tab
from jbrowser.ui.icons import GLYPHS, draw_glyph
from jbrowser.ui.icons import icon as make_icon
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import (ElidedLabel, IconButton, InfoBarWidget, ProgressLine, Spinner, menu_action,
                                 submenu)

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.engine.tab_controller import TabController
    from jbrowser.ui.controller import BrowserController

HEADER_H = 36
RADIUS = 10.0


def is_blank(pm: QPixmap) -> bool:
    """True when a grabbed page is one flat colour: it hasn't painted yet (or is empty)."""
    img = pm.toImage().scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)   # averages, so text still shows
    first = img.pixelColor(0, 0)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if abs(c.red() - first.red()) > 3 or abs(c.green() - first.green()) > 3 \
                    or abs(c.blue() - first.blue()) > 3:
                return False
    return True


class BrowserView(QWebEngineView):
    """QWebEngineView with JBrowser's context menu."""

    def __init__(self, card: "WebCard"):
        super().__init__(card)
        self._card = card
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        req = self.lastContextMenuRequest()
        if req is None:              # no request from the page: Qt's standard menu would crash
            return
        ui = self._card.ui
        tab_id = self._card.tab.id
        standard = self.createStandardContextMenu()   # engine actions (copy, paste, save image, ...)
        menu = QMenu(self)
        standard.setParent(menu, standard.windowFlags())
        if req is not None and req.linkUrl().isValid() and not req.linkUrl().isEmpty():
            link = QUrl(req.linkUrl())
            menu_action(menu, "Open link in new card", lambda: ui.open_url(link, "new", after_tab=tab_id), "add")
            menu_action(menu, "Open link in background card",
                        lambda: ui.open_url(link, "background", after_tab=tab_id), "taskview")
            others = [sp for sp in ui.ctx.state.spaces if sp.id != self._card.tab.space_id]
            if others:
                sub = submenu(menu, "Open link in space", "people")
                for sp in others:
                    menu_action(sub, f"{sp.icon}  {sp.name}",
                                lambda sid=sp.id: ui.open_url(link, "new", space_id=sid))
            menu_action(menu, "Copy link address", lambda: QGuiApplication.clipboard().setText(link.toString()),
                        "link")
            menu.addSeparator()
        if req is not None and req.selectedText().strip():
            text = req.selectedText().strip()
            short = text if len(text) <= 28 else text[:27] + "…"
            menu_action(menu, f"Search {ui.ctx.search.default_name} for “{short}”",
                        lambda: ui.open_url(ui.ctx.search.search_url(text), "new", after_tab=tab_id), "search")
            menu.addSeparator()
        # Chromium's own actions, minus Back / Forward / Reload / Stop (the card header has them, and Qt's
        # icons for them clashed with the rest of the menu), with JBrowser's glyphs instead of Qt's icons.
        WA = QWebEnginePage.WebAction
        page = self.page()
        hidden = {page.action(a) for a in (WA.Back, WA.Forward, WA.Reload, WA.Stop, WA.ReloadAndBypassCache)}
        glyphs = {page.action(a): g for a, g in (
            (WA.Cut, "cut"), (WA.Copy, "copy"), (WA.Paste, "paste"), (WA.SelectAll, "selectall"),
            (WA.SavePage, "save"), (WA.DownloadImageToDisk, "save"), (WA.CopyImageToClipboard, "picture"),
            (WA.CopyImageUrlToClipboard, "link"), (WA.CopyLinkToClipboard, "link"),
            (WA.DownloadLinkToDisk, "download"), (WA.DownloadMediaToDisk, "save"),
            (WA.CopyMediaUrlToClipboard, "link"), (WA.ViewSource, "code"), (WA.InspectElement, "code"))}
        last_separator = True
        for action in standard.actions():
            if action.isSeparator():
                if not last_separator:
                    menu.addSeparator()
                last_separator = True
            elif action.isVisible() and action not in hidden:
                action.setIcon(make_icon(glyphs[action]) if action in glyphs and glyphs[action] in GLYPHS else QIcon())
                menu.addAction(action)
                last_separator = False
        menu.addSeparator()
        menu_action(menu, "Copy card screenshot", lambda: ui.copy_screenshot(tab_id), "crop")
        menu_action(menu, "Inspect", lambda: self._card.toggle_devtools(True), "code")
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(event.globalPos())


class CardHeader(QWidget):
    pressed = pyqtSignal(object)        # Qt.KeyboardModifier
    doubleClicked = pyqtSignal()
    dragMoved = pyqtSignal(QPoint)      # global position
    dragFinished = pyqtSignal()
    contextRequested = pyqtSignal(QPoint)

    def __init__(self, card: "WebCard"):
        super().__init__(card)
        self.card = card
        self.setFixedHeight(HEADER_H)
        self._press_pos: QPoint | None = None
        self._dragging = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 4, 0)
        lay.setSpacing(2)
        self.icon_slot = QWidget(self)
        self.icon_slot.setFixedSize(20, 20)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.spinner = Spinner(16, self.icon_slot)
        self.spinner.move(2, 2)
        self.spinner.hide()
        lay.addWidget(self.icon_slot)
        lay.addSpacing(6)
        self.title = ElidedLabel("", self)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.title, 1)
        self.audio = IconButton("volume", "Mute card", self, size=26, glyph_px=13)
        self.sleep_badge = IconButton("moon", "Sleeping. Click to wake", self, size=26, glyph_px=13)
        self.sleep_badge.set_active_color("sleep")
        self.shield = IconButton("shield", "Trackers blocked", self, size=26, glyph_px=13)
        self.key = IconButton("key", "Saved passwords", self, size=26, glyph_px=13)
        self.zoom = QPushButton("100%", self)
        self.zoom.setFlat(True)
        self.zoom.setFixedHeight(22)
        self.zoom.setToolTip("Reset zoom (Ctrl+0)")
        self.zoom.setStyleSheet("QPushButton{padding:0 6px;font-size:8pt;border-radius:6px;}")
        self.back = IconButton("back", "Back (Ctrl+[)", self, size=28, glyph_px=12)
        self.forward = IconButton("forward", "Forward (Ctrl+])", self, size=28, glyph_px=12)
        self.reload = IconButton("refresh", "Reload (F5)", self, size=28, glyph_px=12)
        self.more = IconButton("more", "Card menu", self, size=28, glyph_px=13)
        self.close = IconButton("close", "Close card (Ctrl+W)", self, size=28, glyph_px=10)
        for w in (self.audio, self.sleep_badge, self.shield, self.key, self.zoom, self.back, self.forward,
                  self.reload, self.more, self.close):
            lay.addWidget(w)
        self.audio.hide()
        self.sleep_badge.hide()
        self.shield.hide()
        self.key.hide()
        self.zoom.hide()

    def _is_button_area(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        return child is not None and child not in (self.title, self.icon_slot)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self._dragging = False
            self.pressed.emit(e.modifiers())
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.card.ui.close_tab(self.card.tab.id)
        e.accept()

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._dragging and (e.position().toPoint() - self._press_pos).manhattanLength() > 8:
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self._dragging:
            self.dragMoved.emit(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e) -> None:
        if self._dragging:
            self.dragFinished.emit()
            self.unsetCursor()
        self._press_pos = None
        self._dragging = False

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()

    def contextMenuEvent(self, e) -> None:
        self.contextRequested.emit(e.globalPos())

    def resizeEvent(self, e) -> None:
        self.card.update_header_density()
        super().resizeEvent(e)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.card.selected and self.card.multi_selected:
            p.fillRect(self.rect(), th.card_outline(0.14))
        r = QRectF(self.icon_slot.geometry())
        tab = self.card.tab
        if tab.loading and not tab.sleeping:
            pass  # spinner child paints
        elif tab.crashed:
            draw_glyph(p, r, "error", th.c("danger"), 14)
        elif not tab.icon.isNull():
            pm = tab.icon.pixmap(QSize(16, 16), self.devicePixelRatioF())
            if tab.sleeping:
                p.setOpacity(0.45)
            p.drawPixmap(QRect(int(r.x()) + 2, int(r.y()) + 2, 16, 16), pm)
            p.setOpacity(1.0)
        else:
            draw_glyph(p, r, "globe", th.c("text3") if tab.sleeping else th.c("text2"), 14)
        if tab.sleeping:
            # small moon badge on the favicon corner
            br = QRectF(r.right() - 9, r.bottom() - 9, 11, 11)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(th.surface("card"))
            p.drawEllipse(br.adjusted(-1, -1, 1, 1))
            draw_glyph(p, br, "moon", th.c("sleep"), 8)
        p.setPen(QPen(th.c("divider"), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class SnapshotView(QWidget):
    """Lightweight stand-in shown while a card sleeps (static snapshot or placeholder)."""

    clicked = pyqtSignal()

    def __init__(self, card: "WebCard"):
        super().__init__(card)
        self.card = card
        self.pixmap: QPixmap | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), th.surface("card"))
        tab = self.card.tab
        if self.pixmap is not None and not self.pixmap.isNull():
            p.setOpacity(0.42)
            src = self.pixmap
            target = QRect(0, 0, self.width(), int(self.width() * src.height() / max(1, src.width())))
            p.drawPixmap(target, src)
            p.setOpacity(1.0)
        # centred pill: moon + label
        text = "Sleeping. Click to wake" if tab.loaded else "Click to load"
        f = p.font()
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 52
        pill = QRectF((self.width() - w) / 2, self.height() / 2 - 20, w, 40)
        path = QPainterPath()
        path.addRoundedRect(pill, 20, 20)
        p.fillPath(path, th.c("panel"))
        p.setPen(QPen(th.c("panel_border"), 1))
        p.drawPath(path)
        draw_glyph(p, QRectF(pill.left() + 12, pill.top(), 22, pill.height()), "moon" if tab.loaded else "play",
                   th.c("sleep"), 15)
        p.setPen(th.c("text"))
        p.drawText(pill.adjusted(40, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, text)
        if self.pixmap is None:
            title = tab.display_title()
            p.setPen(th.c("text2"))
            f.setWeight(400)
            p.setFont(f)
            p.drawText(QRectF(16, pill.bottom() + 12, self.width() - 32, 40),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       f"{title}\n{pretty_url(tab.url, keep_path=False)}")
            if not tab.icon.isNull():
                pm = tab.icon.pixmap(QSize(32, 32), self.devicePixelRatioF())
                p.drawPixmap(QRect((self.width() - 32) // 2, int(pill.top()) - 52, 32, 32), pm)
        p.end()


class FindBar(QFrame):
    search = pyqtSignal(str, bool, bool)   # text, backward, case sensitive
    closed = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(42)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 6, 5)
        lay.setSpacing(4)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Find in page")
        self.edit.setClearButtonEnabled(True)
        self.count = QLabel("", self)
        self.count.setProperty("muted", True)
        self.count.setMinimumWidth(56)
        self.case = IconButton("font", "Match case", self, size=28, glyph_px=12, checkable=True)
        self.prev = IconButton("chev_up", "Previous (Shift+Enter)", self, size=28, glyph_px=11)
        self.next = IconButton("chev_down", "Next (Enter)", self, size=28, glyph_px=11)
        self.close = IconButton("close", "Close (Esc)", self, size=28, glyph_px=10)
        for w in (self.edit, self.count, self.case, self.prev, self.next, self.close):
            lay.addWidget(w)
        lay.setStretch(0, 1)
        self.edit.textChanged.connect(lambda t: self.search.emit(t, False, self.case.isChecked()))
        self.edit.returnPressed.connect(lambda: self.search.emit(self.edit.text(), False, self.case.isChecked()))
        self.prev.clicked.connect(lambda: self.search.emit(self.edit.text(), True, self.case.isChecked()))
        self.next.clicked.connect(lambda: self.search.emit(self.edit.text(), False, self.case.isChecked()))
        self.case.toggled.connect(lambda c: self.search.emit(self.edit.text(), False, c))
        self.close.clicked.connect(self.closed)
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.edit and ev.type() == QEvent.Type.KeyPress:
            if ev.key() == Qt.Key.Key_Escape:
                self.closed.emit()
                return True
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.search.emit(self.edit.text(), True, self.case.isChecked())
                return True
        return False

    def set_result(self, active: int, total: int) -> None:
        if not self.edit.text():
            self.count.setText("")
        else:
            self.count.setText(f"{active}/{total}" if total else "No matches")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme().surface("card"))
        p.setPen(QPen(theme().c("divider"), 1))
        p.drawLine(0, 0, self.width(), 0)
        p.end()


class StatusBubble(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setContentsMargins(8, 3, 8, 3)

    def show_text(self, text: str) -> None:
        if not text:
            self.hide()
            return
        fm = self.fontMetrics()
        maxw = max(120, self.parentWidget().width() - 24)
        self.setText(fm.elidedText(text, Qt.TextElideMode.ElideMiddle, maxw - 16))
        self.adjustSize()
        self.move(6, self.parentWidget().height() - self.height() - 6)
        self.show()
        self.raise_()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.fillPath(path, theme().c("panel"))
        p.setPen(QPen(theme().c("panel_border"), 1))
        p.drawPath(path)
        p.setPen(theme().c("text2"))
        p.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignVCenter, self.text())
        p.end()


class WebCard(QFrame):
    """A card: header + (web view | sleep snapshot) + info bars + find bar + docked DevTools."""

    def __init__(self, ctx: "AppContext", tab: Tab, ctrl: "TabController", ui: "BrowserController",
                 parent: QWidget):
        super().__init__(parent)
        self.ctx = ctx
        self.tab = tab
        self.ctrl = ctrl
        self.ui = ui
        self.active = False
        self.selected = False
        self.multi_selected = False
        self.on_screen = False
        self._stale: set[str] = set()
        self._infobars: dict[str, InfoBarWidget] = {}
        self._devtools: QWebEngineView | None = None
        self._fullscreen = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        self.header = CardHeader(self)
        root.addWidget(self.header)
        self.progress = ProgressLine(self)
        root.addWidget(self.progress)
        self.infobar_box = QVBoxLayout()
        self.infobar_box.setSpacing(0)
        root.addLayout(self.infobar_box)
        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)
        self.splitter = QSplitter(Qt.Orientation.Vertical, self.stack)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(3)
        self.view = BrowserView(self)
        self.view.setPage(ctrl.page)
        self.splitter.addWidget(self.view)
        self.stack.addWidget(self.splitter)
        self.snapshot = SnapshotView(self)
        self.stack.addWidget(self.snapshot)
        self.findbar = FindBar(self)
        self.findbar.hide()
        root.addWidget(self.findbar)
        self.status = StatusBubble(self.stack)

        h = self.header
        h.pressed.connect(self._on_header_pressed)
        h.doubleClicked.connect(lambda: ui.toggle_full_width(self.tab.id))
        h.contextRequested.connect(self.show_menu)
        h.back.clicked.connect(ctrl.back)
        h.forward.clicked.connect(ctrl.forward)
        h.reload.clicked.connect(lambda: ctrl.stop() if self.tab.loading else ctrl.reload())
        h.close.clicked.connect(lambda: ui.close_tab(self.tab.id))
        h.more.clicked.connect(lambda: self.show_menu(h.more.mapToGlobal(QPoint(0, h.more.height()))))
        h.audio.clicked.connect(ctrl.toggle_mute)
        h.sleep_badge.clicked.connect(lambda: ui.wake_tab(self.tab.id))
        h.shield.clicked.connect(lambda: ui.show_shield_menu(self.tab.id, h.shield.mapToGlobal(
            QPoint(0, h.shield.height()))))
        h.key.clicked.connect(lambda: ui.show_password_menu(self.tab.id, h.key.mapToGlobal(QPoint(0, h.key.height()))))
        h.zoom.clicked.connect(lambda: ctrl.set_zoom(1.0))
        self.snapshot.clicked.connect(lambda: ui.activate_card(self.tab.id, Qt.KeyboardModifier.NoModifier, wake=True))
        self.findbar.search.connect(lambda t, b, c: ctrl.find(t, b, c))
        self.findbar.closed.connect(self.close_find)

        tab.changed.connect(self._on_tab_changed)
        ctrl.infobar.connect(self.add_infobar)
        ctrl.infobarClosed.connect(self.remove_infobar)
        ctrl.findResult.connect(self.findbar.set_result)
        ctrl.linkHovered.connect(self.status.show_text)
        ctrl.fullscreenRequested.connect(lambda req: ui.handle_fullscreen(self, req))
        ctrl.closeRequested.connect(lambda: ui.close_tab(self.tab.id))
        ctrl.printRequested.connect(lambda: ui.print_card(self.tab.id))
        ctrl.desktopMediaRequested.connect(lambda req: ui.choose_desktop_media(req))
        ctrl.navigated.connect(self._on_navigated)
        self.apply(frozenset({"title", "icon", "loading", "audible", "muted", "sleeping", "blocked",
                              "saved_logins", "zoom", "can_back", "can_forward", "url", "crashed"}))

    # ------------------------------------------------------------ state sync
    def set_on_screen(self, on: bool) -> None:
        if on == self.on_screen:
            return
        self.on_screen = on
        if on and self._stale:
            stale, self._stale = self._stale, set()
            self.apply(frozenset(stale))

    def _on_tab_changed(self, fields: frozenset) -> None:
        # Off-screen cards only record staleness (no layout/paint work) except for the
        # structural 'sleeping' swap which must happen immediately.
        if not self.on_screen:
            self._stale |= set(fields)
            if "sleeping" in fields:
                self._apply_sleep_state()
            return
        self.apply(fields)

    def apply(self, fields: frozenset) -> None:
        tab = self.tab
        h = self.header
        if fields & {"title", "url"}:
            h.title.setText(tab.display_title())
            h.title.setToolTip(f"{tab.display_title()}\n{tab.url}")
        if fields & {"loading", "sleeping"}:
            h.spinner.setVisible(tab.loading and not tab.sleeping)
            h.reload.set_glyph("stop" if tab.loading else "refresh")
            h.reload.setToolTip("Stop (Esc)" if tab.loading else "Reload (F5)")
        if fields & {"loading", "progress"}:
            self.progress.set_progress(tab.progress, tab.loading)
        if fields & {"audible", "muted"}:
            h.audio.setVisible(tab.audible or tab.muted)
            h.audio.set_glyph("mute" if tab.muted else "volume")
            h.audio.setToolTip("Unmute card" if tab.muted else "Mute card")
        if "blocked" in fields:
            h.shield.set_badge(str(tab.blocked) if tab.blocked else None)
            h.shield.setToolTip(f"{tab.blocked} tracker{'s' if tab.blocked != 1 else ''} blocked on this page")
        if "saved_logins" in fields:
            h.key.setToolTip(f"{tab.saved_logins} saved login(s). Click to fill")
        if "zoom" in fields:
            h.zoom.setText(f"{round(tab.zoom * 100)}%")
        if fields & {"can_back", "can_forward"}:
            h.back.setEnabled(tab.can_back)
            h.forward.setEnabled(tab.can_forward)
        if "sleeping" in fields:
            self._apply_sleep_state()
        self.update_header_density()
        h.update()

    def update_header_density(self) -> None:
        h = self.header
        w = self.width()
        tab = self.tab
        roomy = w >= 420
        medium = w >= 300
        for b in (h.back, h.forward):
            b.setVisible(roomy)
        h.reload.setVisible(w >= 250)
        h.more.setVisible(w >= 200)
        h.shield.setVisible(medium and tab.blocked > 0)
        h.key.setVisible(medium and tab.saved_logins > 0)
        h.zoom.setVisible(medium and abs(tab.zoom - 1.0) > 0.001)
        h.sleep_badge.setVisible(tab.sleeping and w >= 220)

    def _apply_sleep_state(self) -> None:
        if self.tab.sleeping:
            if self.stack.currentWidget() is not self.snapshot:
                self.stack.setCurrentWidget(self.snapshot)
            self.snapshot.update()
        else:
            if self.stack.currentWidget() is not self.splitter:
                self.stack.setCurrentWidget(self.splitter)
        self.header.update()

    def take_snapshot(self) -> None:
        if self.tab.sleeping or not self.tab.loaded or not self.view.isVisible():
            return
        if self.view.width() < 40 or self.view.height() < 40:
            return
        pm = self.view.grab()
        if pm.isNull():
            return
        if pm.width() > 1000:   # a faded preview; full resolution would cost ~9 MB per card
            pm = pm.scaledToWidth(1000, Qt.TransformationMode.SmoothTransformation)
        # A blank picture (the page hadn't painted yet) would outlive it: show the title placeholder instead.
        self.snapshot.pixmap = None if is_blank(pm) else pm

    def enter_sleep(self) -> None:
        self.take_snapshot()
        self.close_find()
        self.stack.setCurrentWidget(self.snapshot)   # hides the live view → page becomes invisible
        self.snapshot.update()
        self.header.update()

    def exit_sleep(self) -> None:
        self.stack.setCurrentWidget(self.splitter)
        self.header.update()

    # --------------------------------------------------------------- focus
    def set_active(self, active: bool) -> None:
        if active != self.active:
            self.active = active
            self.update()

    def set_selected(self, selected: bool, multi: bool) -> None:
        if selected != self.selected or multi != self.multi_selected:
            self.selected = selected
            self.multi_selected = multi
            self.update()
            self.header.update()

    def _on_header_pressed(self, modifiers) -> None:
        self.ui.activate_card(self.tab.id, modifiers)

    def focus_view(self) -> None:
        if self.tab.sleeping:
            self.snapshot.setFocus()
        else:
            self.view.setFocus(Qt.FocusReason.OtherFocusReason)

    # ----------------------------------------------------------- info bars
    def add_infobar(self, spec: InfoBarSpec) -> None:
        self.remove_infobar(spec.key)
        w = InfoBarWidget(spec, self)
        w.closed.connect(self.remove_infobar)
        self._infobars[spec.key] = w
        self.infobar_box.addWidget(w)

    def remove_infobar(self, key: str) -> None:
        w = self._infobars.pop(key, None)
        if w is not None:
            w.hide()
            w.deleteLater()

    def _on_navigated(self) -> None:
        for w in list(self._infobars.values()):
            if not w.spec.persist_navigation:
                w.dismiss()
        self.status.hide()

    # ------------------------------------------------------------- find
    def open_find(self) -> None:
        if self.tab.sleeping:
            return
        self.findbar.show()
        sel = self.view.selectedText().strip()
        if sel and "\n" not in sel and len(sel) < 80:
            self.findbar.edit.setText(sel)
        self.findbar.edit.setFocus()
        self.findbar.edit.selectAll()

    def close_find(self) -> None:
        if self.findbar.isVisible():
            self.findbar.hide()
            self.ctrl.stop_find()
            self.findbar.set_result(0, 0)
            self.view.setFocus()

    # ----------------------------------------------------------- devtools
    def toggle_devtools(self, force_open: bool | None = None) -> None:
        want = (self._devtools is None) if force_open is None else force_open
        if want and self._devtools is None:
            dev = QWebEngineView(self.splitter)
            dev_page = QWebEnginePage(self.ctrl.page.profile(), dev)
            dev.setPage(dev_page)
            self.ctrl.page.setDevToolsPage(dev_page)
            self.splitter.addWidget(dev)
            total = max(200, self.splitter.height())
            self.splitter.setSizes([int(total * 0.58), int(total * 0.42)])
            self._devtools = dev
            self.tab.update(devtools=True)
            if force_open and self.ctrl.page is not None:
                self.ctrl.page.triggerAction(QWebEnginePage.WebAction.InspectElement)
        elif not want and self._devtools is not None:
            self.ctrl.page.setDevToolsPage(None)
            self._devtools.hide()
            self._devtools.deleteLater()
            self._devtools = None
            self.tab.update(devtools=False)

    # --------------------------------------------------------------- menu
    def show_menu(self, global_pos: QPoint) -> None:
        self.ui.show_card_menu(self.tab.id, global_pos)

    # ---------------------------------------------------------- fullscreen
    def set_immersive(self, on: bool) -> None:
        self._fullscreen = on
        self.header.setVisible(not on)
        self.progress.setVisible(not on)
        self.layout().setContentsMargins(*((0, 0, 0, 0) if on else (1, 1, 1, 1)))
        self.update()

    # -------------------------------------------------------------- paint
    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        radius = 0 if self._fullscreen else RADIUS
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, th.surface("card"))
        if self._fullscreen:
            p.end()
            return
        if self.active:
            pen = QPen(th.card_outline(), 2)
        elif self.selected and self.multi_selected:
            pen = QPen(th.card_outline(0.6), 1.5)
        else:
            pen = QPen(th.c("card_border"), 1)
        p.setPen(pen)
        p.drawPath(path)
        p.end()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.update_header_density()

    def teardown(self) -> None:
        """Detach from the engine before deletion (views go before pages)."""
        try:
            self.tab.changed.disconnect(self._on_tab_changed)
        except (TypeError, RuntimeError):
            pass
        if self._devtools is not None:
            try:
                self.ctrl.page.setDevToolsPage(None)
            except RuntimeError:
                pass
        self.hide()
        self.deleteLater()
