"""Reading mode inside a card, and the small offer that suggests it on articles.

ReaderView shows the article that engine/reader.py pulled out of the page, in its own page with no
website scripts. The real page stays loaded underneath, so leaving reading mode is instant and the
card's history is untouched.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt, QTimer, QUrl, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QPushButton,
                             QVBoxLayout, QWidget)

from jbrowser.core.motion import motion
from jbrowser.engine import reader
from jbrowser.engine.js import BRIDGE_WORLD
from jbrowser.ui.icons import draw_glyph
from jbrowser.ui.theme import solid, theme
from jbrowser.ui.widgets import IconButton, menu_action

if TYPE_CHECKING:
    from jbrowser.ui.card import WebCard

NT = QWebEnginePage.NavigationType
SWATCHES = {"light": "#ffffff", "sepia": "#f1e7d0", "dark": "#26262c"}


class _LinkCatcher(QWebEnginePage):
    """Stands in for a new window (Ctrl+click, middle-click): opens the link as a background card."""

    def __init__(self, view: "ReaderView"):
        super().__init__(view.page.profile(), view)
        self._view = view

    def acceptNavigationRequest(self, url: QUrl, _type, _main: bool) -> bool:
        if url.scheme() in ("http", "https"):
            card = self._view.card
            card.ui.open_url(QUrl(url), "background", after_tab=card.tab.id)
        QTimer.singleShot(0, self.deleteLater)
        return False


class ReaderWeb(QWebEngineView):
    """The article view, with a short menu of its own (copy, links), not the engine's page menu."""

    def __init__(self, view: "ReaderView"):
        super().__init__(view)
        self._view = view

    def contextMenuEvent(self, event) -> None:
        req = self.lastContextMenuRequest()
        if req is None:
            return
        card = self._view.card
        m = QMenu(self)
        link = QUrl(req.linkUrl())
        if link.isValid() and not link.isEmpty() and link.scheme() in ("http", "https"):
            menu_action(m, "Open link in new card", lambda: card.ui.open_url(link, "new", after_tab=card.tab.id),
                        "add")
            menu_action(m, "Open link in background card",
                        lambda: card.ui.open_url(link, "background", after_tab=card.tab.id), "taskview")
            menu_action(m, "Copy link address", lambda: QGuiApplication.clipboard().setText(link.toString()), "link")
            m.addSeparator()
        if req.selectedText().strip():
            menu_action(m, "Copy", lambda: self.page().triggerAction(QWebEnginePage.WebAction.Copy), "copy",
                        shortcut="Ctrl+C")
        menu_action(m, "Select all", lambda: self.page().triggerAction(QWebEnginePage.WebAction.SelectAll),
                    "selectall", shortcut="Ctrl+A")
        m.addSeparator()
        menu_action(m, "Leave reading mode", self._view.leave, "reading", shortcut="F9")
        m.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        m.popup(event.globalPos())


class ReaderPage(QWebEnginePage):
    def __init__(self, view: "ReaderView"):
        super().__init__(view.card.ctx.profiles.reader_profile(), view)
        self._view = view
        self.loading_article = False
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadIconsForPage, False)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if self.loading_article and nav_type != NT.NavigationTypeLinkClicked:
            return True
        if is_main_frame and nav_type == NT.NavigationTypeLinkClicked and url.scheme() in ("http", "https"):
            QTimer.singleShot(0, lambda u=QUrl(url): self._view.follow_link(u))
        return False                        # nothing else may navigate the article page

    def createWindow(self, _type) -> QWebEnginePage:
        return _LinkCatcher(self._view)

    def javaScriptConsoleMessage(self, *_a) -> None:
        pass


class _Swatch(QAbstractButton):
    def __init__(self, key: str, parent: QWidget):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip({"auto": "Match JBrowser's theme", "light": "Light", "sepia": "Sepia",
                         "dark": "Dark"}[key])

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self.key == "auto":
            half = QPainterPath()
            half.addEllipse(r)
            p.fillPath(half, QColor(SWATCHES["light"]))
            p.save()
            p.setClipRect(QRectF(r.center().x(), r.top(), r.width() / 2 + 1, r.height()))
            p.fillPath(half, QColor(SWATCHES["dark"]))
            p.restore()
        else:
            dot = QPainterPath()
            dot.addEllipse(r)
            p.fillPath(dot, QColor(SWATCHES[self.key]))
        p.setPen(QPen(th.c("accent"), 2) if self.isChecked() else QPen(th.c("input_border"), 1))
        p.drawEllipse(r.adjusted(-1, -1, 1, 1) if self.isChecked() else r)
        p.end()


class ReaderBar(QWidget):
    """Slim bar over the article: text style, size, colours and the way out."""

    def __init__(self, view: "ReaderView"):
        super().__init__(view)
        self.view = view
        s = view.card.ctx.settings
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(4)
        self.label = QLabel("Reading mode", self)
        f = QFont(self.label.font())
        f.setWeight(QFont.Weight.DemiBold)
        self.label.setFont(f)
        self.minutes = QLabel("", self)
        self.minutes.setProperty("muted", True)
        lay.addSpacing(22)                               # the reading glyph is painted here
        lay.addWidget(self.label)
        lay.addWidget(self.minutes)
        lay.addStretch(1)
        self.font_btn = QPushButton("Sans" if s.get("reading.font") == "serif" else "Serif", self)
        self.font_btn.setFlat(True)
        self.font_btn.setToolTip("Switch between a serif and a sans-serif font")
        self.font_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.smaller = IconButton("zoom_out", "Smaller text (Ctrl+-)", self, size=28, glyph_px=12)
        self.bigger = IconButton("zoom_in", "Bigger text (Ctrl+=)", self, size=28, glyph_px=12)
        lay.addWidget(self.font_btn)
        lay.addWidget(self.smaller)
        lay.addWidget(self.bigger)
        lay.addSpacing(6)
        self.swatches = []
        for key in reader.THEMES:
            sw = _Swatch(key, self)
            sw.clicked.connect(lambda _c=False, k=key: view.set_theme(k))
            self.swatches.append(sw)
            lay.addWidget(sw)
        lay.addSpacing(6)
        self.exit = QPushButton("Leave reading mode", self)
        self.exit.setToolTip("Back to the original page (F9 or Esc)")
        self.exit.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.exit)
        self.font_btn.clicked.connect(view.toggle_font)
        self.smaller.clicked.connect(lambda: view.step_zoom(-1))
        self.bigger.clicked.connect(lambda: view.step_zoom(1))
        self.exit.clicked.connect(view.leave)
        self.sync()

    def sync(self) -> None:
        s = self.view.card.ctx.settings
        self.font_btn.setText("Sans" if s.get("reading.font") != "sans" else "Serif")
        current = s.get("reading.theme") or "auto"
        for sw in self.swatches:
            sw.setChecked(sw.key == current)
        z = self.view.zoom()
        self.smaller.setEnabled(z > reader.ZOOM_STEPS[0] + 0.001)
        self.bigger.setEnabled(z < reader.ZOOM_STEPS[-1] - 0.001)

    def resizeEvent(self, e) -> None:
        # Narrow cards keep only what matters: size and the way out.
        w = self.width()
        self.minutes.setVisible(w >= 560)
        self.label.setVisible(w >= 470)
        for sw in self.swatches:
            sw.setVisible(w >= 400)
        self.font_btn.setVisible(w >= 330)
        self.exit.setText("Leave reading mode" if w >= 300 else "Leave")
        super().resizeEvent(e)

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), th.surface("card"))
        p.fillRect(self.rect(), th.accent_alpha(0.06))
        draw_glyph(p, QRectF(10, 0, 22, self.height()), "reading", th.c("accent"), 14)
        p.setPen(QPen(th.c("divider"), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class ReaderView(QWidget):
    def __init__(self, card: "WebCard"):
        super().__init__(card)
        self.card = card
        self.article: dict | None = None
        self.url = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.web = ReaderWeb(self)
        self.page = ReaderPage(self)
        self.page.setUrlRequestInterceptor(card.ctrl.url_interceptor())   # trackers stay blocked
        self.web.setPage(self.page)
        self.page.loadFinished.connect(self._on_loaded)
        self.bar = ReaderBar(self)
        lay.addWidget(self.bar)
        lay.addWidget(self.web, 1)
        for keys, fn in ((("Esc",), self.leave), (("Ctrl+=", "Ctrl++"), lambda: self.step_zoom(1)),
                         (("Ctrl+-",), lambda: self.step_zoom(-1)), (("Ctrl+0",), lambda: self.set_zoom(1.0))):
            for k in keys:
                sc = QShortcut(QKeySequence(k), self)
                sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                sc.activated.connect(fn)
        theme().changed.connect(self._on_theme)
        card.ctx.settings.changed.connect(self._on_setting)

    def _on_setting(self, key: str, _value) -> None:
        # Also changed from Settings › Appearance while an article is open.
        try:
            if key in ("reading.font", "reading.theme"):
                self._apply_classes()
            elif key == "reading.zoom":
                self.page.setZoomFactor(self.zoom())
                self.bar.sync()
        except RuntimeError:
            pass

    # ----------------------------------------------------------- content
    def show_article(self, article: dict, url: str) -> None:
        self.article, self.url = article, url
        mins = reader.reading_minutes(int(article.get("length") or 0))
        self.bar.minutes.setText(f"· {mins} min read")
        self._render()

    def _render(self) -> None:
        if self.article is None:
            return
        s = self.card.ctx.settings
        th = theme()
        page_html = reader.render(self.article, self.url, s.get("reading.font") or "serif",
                                  s.get("reading.theme") or "auto", th.dark, th.accent.name())
        self.page.loading_article = True
        self.page.setHtml(page_html, QUrl(self.url))
        self.page.setZoomFactor(self.zoom())

    def _on_loaded(self, _ok: bool) -> None:
        self.page.loading_article = False
        self.page.setZoomFactor(self.zoom())

    def _apply_classes(self) -> None:
        s = self.card.ctx.settings
        cls = reader.classes(s.get("reading.font") or "serif", s.get("reading.theme") or "auto", theme().dark)
        self.page.runJavaScript(f"document.documentElement.className = {json.dumps(cls)};", BRIDGE_WORLD)
        self.bar.sync()

    def _on_theme(self) -> None:
        try:
            if self.isVisible() and (self.card.ctx.settings.get("reading.theme") or "auto") == "auto":
                self._apply_classes()
            self.bar.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------ choices
    def zoom(self) -> float:
        try:
            return max(reader.ZOOM_STEPS[0], min(reader.ZOOM_STEPS[-1],
                                                 float(self.card.ctx.settings.get("reading.zoom") or 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def set_zoom(self, z: float) -> None:
        self.card.ctx.settings.set("reading.zoom", round(z, 2))     # _on_setting applies it

    def step_zoom(self, direction: int) -> None:
        z = self.zoom()
        steps = reader.ZOOM_STEPS
        nxt = next((s for s in steps if s > z + 0.001), steps[-1]) if direction > 0 else \
            next((s for s in reversed(steps) if s < z - 0.001), steps[0])
        self.set_zoom(nxt)

    def toggle_font(self) -> None:
        s = self.card.ctx.settings
        s.set("reading.font", "sans" if s.get("reading.font") != "sans" else "serif")

    def set_theme(self, key: str) -> None:
        self.card.ctx.settings.set("reading.theme", key)
        self.bar.sync()                   # the same theme again changes no setting

    def follow_link(self, url: QUrl) -> None:
        """A link in the article: leave reading mode and open it in the card, like on the page."""
        self.leave()
        self.card.ctrl.load(url)

    def leave(self) -> None:
        self.card.ui.set_reading(self.card.tab.id, False)

    def focus(self) -> None:
        self.web.setFocus(Qt.FocusReason.OtherFocusReason)

    def dispose(self) -> None:
        for signal, slot in ((theme().changed, self._on_theme), (self.card.ctx.settings.changed, self._on_setting)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.web.setPage(None)
        self.page.deleteLater()


class ReadingOffer(QFrame):
    """"This looks like an article": appears over the page, offers reading mode, never blocks the page."""

    def __init__(self, card: "WebCard"):
        super().__init__(card.stack)
        self.card = card
        self._opacity = 0.0
        self.setObjectName("ReadingOffer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(46, 10, 10, 10)
        lay.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("Read this in reading mode?", self)
        f = QFont(title.font())
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        title.setWordWrap(True)
        sub = QLabel("Just the text and pictures, without the clutter.", self)
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        self.never = QPushButton("Don't show again", self)
        self.never.setFlat(True)
        self.never.setCursor(Qt.CursorShape.PointingHandCursor)
        self.never.setToolTip("Stop suggesting reading mode. You can still use the reading mode button")
        self.never.setStyleSheet("QPushButton{padding:0;border:none;background:transparent;text-align:left;"
                                 f"color:{theme().c('accent').name()};font-size:8.5pt;}}"
                                 "QPushButton:hover{text-decoration:underline;}")
        text.addWidget(title)
        text.addWidget(sub)
        text.addWidget(self.never, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(text, 1)
        self.read_btn = QPushButton("Reading mode", self)
        self.read_btn.setProperty("primary", True)
        self.read_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn = IconButton("close", "Close", self, size=28, glyph_px=10)
        lay.addWidget(self.read_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.read_btn.clicked.connect(self._read)
        self.close_btn.clicked.connect(self.dismiss)
        self.never.clicked.connect(self._never)
        self.hide()

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, v: float) -> None:
        self._opacity = float(v)
        self._effect.setOpacity(self._opacity)
        self.place()

    fade = pyqtProperty(float, _get_opacity, _set_opacity)

    def place(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        w = min(460, host.width() - 24)
        self.setFixedWidth(max(220, w))
        self.adjustSize()
        lift = int(10 * (1.0 - self._opacity))
        self.move((host.width() - self.width()) // 2, host.height() - self.height() - 16 + lift)

    def present(self) -> None:
        if self.parentWidget() is None or self.parentWidget().width() < 260:
            return
        self.place()
        self.show()
        self.raise_()
        motion().animate_property(self, b"fade", 0.0, 1.0, motion().NORMAL)

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        motion().animate_property(self, b"fade", self._opacity, 0.0, motion().FAST, on_finished=self.hide)

    def _read(self) -> None:
        self.hide()
        self.card.ui.set_reading(self.card.tab.id, True)

    def _never(self) -> None:
        self.card.ctx.settings.set("reading.offer", False)
        self.dismiss()
        self.card.ui.toast("Reading mode won't be suggested again. Turn it back on in Settings › Appearance",
                           "reading")

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        # Solid: over a web page even a slightly see-through fill lets the page's text show through.
        p.fillPath(path, solid(th.c("panel")))
        p.fillPath(path, th.accent_alpha(0.06))
        p.setPen(QPen(th.accent_alpha(0.40), 1.1))
        p.drawPath(path)
        draw_glyph(p, QRectF(12, 0, 26, min(self.height(), 64)), "reading", th.c("accent"), 18)
        p.end()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.place()
