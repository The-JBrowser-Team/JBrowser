"""Settings window.

Translucent navigation pane on the left (Acrylic / Mica shows through), option cards on
the right. Every card explains in plain language what the option does, and every control
writes straight into the settings store, so changes apply immediately.
"""
from __future__ import annotations

import platform
import sys
import time
from typing import Any, Callable

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QEvent, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from jbrowser import APP_NAME, __version__
from jbrowser.core.settings import DEFAULT_SEARCH_KEYWORDS, SLEEP_PRESETS
from jbrowser.platform import win
from jbrowser.services.network import describe_proxy
from jbrowser.services.search import ENGINES
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.icons import draw_glyph, icon, logo_pixmap
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import TintPicker, ToggleSwitch

NAV_W = 250

# The navigation pane, in groups. PAGES (every page, in order) also gives each page a Lazy Toolbar command
# (ui/actions.py: "Settings: Search", ...).
NAV_GROUPS = [
    ("Browsing", [("general", "General", "home"), ("search", "Search", "search"),
                  ("defaults", "Default apps", "newwindow")]),
    ("Look and feel", [("appearance", "Appearance", "sun"), ("ribbon", "Ribbon and sidebar", "sidebar")]),
    ("Privacy and safety", [("privacy", "Privacy and security", "shield"), ("clear", "Clear browsing data", "clear"),
                            ("passwords", "Passwords", "key"), ("downloads", "Downloads", "download")]),
    ("System", [("performance", "Performance", "speed"), ("network", "Network and DNS", "network"),
                ("advanced", "Advanced", "developer"), ("reset", "Reset", "sync"),
                ("about", "About JBrowser", "info")]),
]
PAGES = [page for _group, pages in NAV_GROUPS for page in pages]

CLEAR_RANGES = [(3600, "Last hour"), (86400, "Last 24 hours"), (7 * 86400, "Last 7 days"),
                (28 * 86400, "Last 4 weeks"), (0, "All time")]


def _disconnect_all(links: list) -> None:
    while links:
        signal, slot = links.pop()
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass


class _Glyph(QWidget):
    def __init__(self, name: str, parent: QWidget | None = None, token: str = "text2"):
        super().__init__(parent)
        self.name, self.token = name, token
        self.setFixedSize(28, 28)

    def paintEvent(self, _e) -> None:
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPainter
        p = QPainter(self)
        draw_glyph(p, QRectF(self.rect()), self.name, theme().c(self.token), 16)
        p.end()


class SettingCard(QFrame):
    """One option: icon, title, plain-language description, control on the right."""

    def __init__(self, glyph: str, title: str, description: str, control: QWidget | None = None,
                 extra: QWidget | None = None, token: str = "text2"):
        super().__init__()
        self.setObjectName("SettingCard")
        self.search_text = f"{title} {description}".lower()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(_Glyph(glyph, self, token), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(3)
        t = QLabel(title)
        t.setProperty("cardtitle", True)
        t.setWordWrap(True)
        text.addWidget(t)
        if description:
            d = QLabel(description)
            d.setProperty("carddesc", True)
            d.setWordWrap(True)
            text.addWidget(d)
        row.addLayout(text, 1)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(row)
        if extra is not None:
            extra_box = QHBoxLayout()
            extra_box.setContentsMargins(42, 0, 0, 0)
            extra_box.addWidget(extra, 1)
            outer.addLayout(extra_box)


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("hint", True)
    lab.setWordWrap(True)
    return lab


def _section(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("section", True)
    return lab


def _button(text: str, fn: Callable[[], Any], primary: bool = False, danger: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("primary", primary)
    b.setProperty("danger", danger)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda _c=False: fn())
    return b


def _buttons(*buttons: QPushButton) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for b in buttons:
        lay.addWidget(b)
    lay.addStretch(1)
    return box


class SettingsWindow(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Settings", parent, (1080, 760), nav_width=NAV_W)
        self.ctx = ctx
        self.ui = ui
        self.s = ctx.settings
        self._cards: list[tuple[str, SettingCard]] = []
        self._sections: list[tuple[QLabel, list[SettingCard]]] = []      # headings inside pages, with their cards
        self._nav_groups: list[tuple[QListWidgetItem, list[str]]] = []
        self._index: dict[str, int] = {}
        # Connections to long-lived services; dropped when the window goes away so no slot
        # ever touches a deleted widget.
        self._links: list[tuple[Any, Callable]] = []
        self.destroyed.connect(lambda *_a, links=self._links: _disconnect_all(links))
        self.root.setContentsMargins(0, 0, 0, 0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.root.addLayout(body)

        nav = QWidget()
        nav.setFixedWidth(NAV_W)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(14, 6, 12, 14)
        nl.setSpacing(10)
        self.finder = QLineEdit()
        self.finder.setPlaceholderText("Find a setting")
        self.finder.setClearButtonEnabled(True)
        self.finder.textChanged.connect(self._filter)
        nl.addWidget(self.finder)
        self.nav = QListWidget()
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._style_nav()
        self._listen(theme().changed, self._style_nav)
        nl.addWidget(self.nav, 1)
        body.addWidget(nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsStack")
        body.addWidget(self.stack, 1)
        builders = {"general": self._general, "search": self._search, "defaults": self._defaults,
                    "appearance": self._appearance, "ribbon": self._ribbon, "privacy": self._privacy,
                    "clear": self._clear, "passwords": self._passwords, "downloads": self._downloads,
                    "performance": self._performance, "network": self._network, "advanced": self._advanced,
                    "reset": self._reset, "about": self._about}
        head_font = self.nav.font()
        head_font.setPointSizeF(max(7.5, head_font.pointSizeF() - 1))
        head_font.setWeight(QFont.Weight.DemiBold)
        for n, (group, pages) in enumerate(NAV_GROUPS):
            head = QListWidgetItem(group)
            head.setFlags(Qt.ItemFlag.NoItemFlags)          # a heading: never selected or focused
            head.setFont(head_font)
            head.setSizeHint(QSize(200, 28 if n == 0 else 40))
            head.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            self.nav.addItem(head)
            self._nav_groups.append((head, [key for key, _l, _g in pages]))
            for key, label, glyph in pages:
                it = QListWidgetItem(icon(glyph), label)
                it.setData(Qt.ItemDataRole.UserRole, key)
                it.setSizeHint(QSize(200, 36))
                self.nav.addItem(it)
                self._index[key] = self.stack.count()
                self._current_page = key
                self.stack.addWidget(builders[key]())
        self._style_nav()
        self.nav.currentRowChanged.connect(self._on_nav)
        self.show_page("general")

    # ------------------------------------------------------------ plumbing
    def _listen(self, signal, slot: Callable) -> None:
        signal.connect(slot)
        self._links.append((signal, slot))

    def closeEvent(self, e) -> None:
        _disconnect_all(self._links)
        super().closeEvent(e)

    def _style_nav(self) -> None:
        t = theme().tokens
        self.nav.setStyleSheet(
            "QListWidget{background:transparent;border:none;}"
            "QListWidget::item{padding:7px 10px;border-radius:7px;margin:1px 0;}"
            f"QListWidget::item:selected{{background:{t['selected']};color:{t['text']};}}"
            f"QListWidget::item:hover:!selected{{background:{t['hover']};}}"
            f"QListWidget::item:disabled{{background:transparent;color:{t['text3']};padding:0 10px 3px 10px;}}")

    def _on_nav(self, row: int) -> None:
        item = self.nav.item(row)
        key = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if key in self._index:
            self.stack.setCurrentIndex(self._index[key])

    def show_page(self, key: str) -> None:
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.nav.setCurrentRow(i)
                return

    def _page(self, title: str, intro: str, *widgets) -> QScrollArea:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 14, 28, 28)
        lay.setSpacing(8)
        head = QLabel(title)
        head.setProperty("heading", True)
        lay.addWidget(head)
        if intro:
            i = QLabel(intro)
            i.setProperty("carddesc", True)
            i.setWordWrap(True)
            lay.addWidget(i)
            lay.addSpacing(6)
        section: list[SettingCard] | None = None
        for w in widgets:
            if w is None:
                continue
            if isinstance(w, int):
                lay.addSpacing(w)
            elif isinstance(w, SettingCard):
                self._cards.append((self._current_page, w))
                if section is not None:
                    section.append(w)
                lay.addWidget(w)
            elif isinstance(w, QLabel) and w.property("section"):
                if section is not None:
                    lay.addSpacing(10)
                section = []
                self._sections.append((w, section))
                lay.addWidget(w)
            else:
                lay.addWidget(w)
        lay.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(body)
        return area

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        pages_with_hits: list[str] = []
        for page, card in self._cards:
            hit = all(w in card.search_text for w in words)
            card.setVisible(hit)
            if hit and page not in pages_with_hits:
                pages_with_hits.append(page)
        for label, cards in self._sections:                 # a heading shows while one of its cards does
            label.setVisible(not words or any(not c.isHidden() for c in cards))
        shown: set[str] = set()
        for i in range(self.nav.count()):
            key = self.nav.item(i).data(Qt.ItemDataRole.UserRole)
            if key is None:
                continue
            hidden = bool(words) and key not in pages_with_hits and key != "about"
            self.nav.item(i).setHidden(hidden)
            if not hidden:
                shown.add(key)
        for head, keys in self._nav_groups:
            head.setHidden(not any(k in shown for k in keys))
        if words and pages_with_hits:
            cur = self.nav.currentItem()
            if cur is None or cur.data(Qt.ItemDataRole.UserRole) not in pages_with_hits:
                self.show_page(pages_with_hits[0])

    # control helpers ------------------------------------------------------
    def _toggle(self, key: str, on_change: Callable[[bool], Any] | None = None) -> ToggleSwitch:
        sw = ToggleSwitch(bool(self.s.get(key)))
        sw.toggled.connect(lambda v: (self.s.set(key, bool(v)), on_change(bool(v)) if on_change else None))

        def sync(k, v):
            if k == key and sw.isChecked() != bool(v):
                sw.blockSignals(True)
                sw.setChecked(bool(v))
                sw.knob = 1.0 if v else 0.0
                sw.blockSignals(False)
        self._listen(self.s.changed, sync)
        return sw

    def _combo(self, key: str, options: list[tuple[Any, str]], width: int = 240) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumWidth(width)
        current = self.s.get(key)
        for i, (value, label) in enumerate(options):
            combo.addItem(label, value)
            same = value == current or (isinstance(value, float) and isinstance(current, (int, float))
                                        and abs(value - float(current)) < 0.005)
            if same:
                combo.setCurrentIndex(i)
        combo.currentIndexChanged.connect(lambda i: self.s.set(key, combo.itemData(i)))
        return combo

    def _toggle_card(self, key: str, glyph: str, title: str, desc: str,
                     on_change: Callable[[bool], Any] | None = None) -> SettingCard:
        return SettingCard(glyph, title, desc, self._toggle(key, on_change))

    # --------------------------------------------------------------- pages
    def _general(self) -> QWidget:
        self._current_page = "general"
        width_options = [(0.25, "Narrow (25%)"), (1 / 3, "One third (33%)"), (0.5, "Half (50%)"),
                         (2 / 3, "Two thirds (66%)"), (0.8, "Wide (80%)"), (1.0, "Full width (100%)")]
        return self._page(
            "General",
            "The basics. You can change any of these back at any time.",
            _section("Starting up"),
            SettingCard("home", "Reopen my cards when JBrowser starts",
                        "Your cards come back where you left them. Only the ones on screen load straight away, so "
                        "JBrowser still starts quickly.", self._toggle("startup.restore_session")),
            SettingCard("search", "Search engine",
                        "Used when you type words instead of a web address. To use another engine once, type its "
                        "keyword first, like “yt cats” for YouTube. More in Search.",
                        self._combo("search.engine", [(k, v[0]) for k, v in ENGINES.items()])),
            _section("Cards"),
            SettingCard("columns", "Width of new cards",
                        "Cards sit side by side. Half fits two on screen; full width gives one card the whole "
                        "window. To resize a card, select it and use the width button on the ribbon, or press Alt+1 "
                        "to Alt+9 (Alt+0 for full width).",
                        self._combo("canvas.default_width", width_options)),
            SettingCard("stack", "Stack cards in a column",
                        "Put up to three cards on top of each other: drag a card onto the lower part of another, or "
                        "use the stack button on the ribbon (Alt+Shift+S). Cards in a column always share one width.",
                        _button("Stack a card now", lambda: (self.close(), self.ui.open_stack_picker()))),
            SettingCard("grid", "Show the overview strip",
                        "A thin bar under the cards that shows where you are. Click or drag it to jump around.",
                        self._toggle("canvas.show_minimap")),
            _section("Reading"),
            self._reading_card(),
            _section("Help"),
            SettingCard("lightbulb", "Getting around",
                        "Alt + mouse wheel slides between cards. Alt+← and Alt+→ move between cards, Alt+↑ and Alt+↓ "
                        "switch spaces. Ctrl+T opens a card and Ctrl+K searches everything.",
                        _button("Show shortcuts", lambda: (self.close(), self.ui.open_hotkeys()))),
        )

    def _appearance(self) -> QWidget:
        self._current_page = "appearance"
        return self._page(
            "Appearance", "How JBrowser looks and moves. The buttons on the ribbon are in Ribbon and sidebar.",
            _section("Colours and material"),
            SettingCard("sun", "Theme",
                        "Dark or light. “Match Windows” switches along with your Windows colour mode.",
                        self._combo("appearance.theme", [("system", "Match Windows"), ("dark", "Dark"),
                                                         ("light", "Light")])),
            SettingCard("tiles", "Window material",
                        "The see-through look of the window. Acrylic blurs what's behind it, Mica takes a soft tint "
                        "from your wallpaper (Mica Alt a stronger one), and Solid turns see-through effects off and "
                        "uses the least graphics power. When Windows has transparency effects or energy saver "
                        "turned off, JBrowser looks like Solid until they're back.",
                        self._combo("appearance.material", [("acrylic", "Acrylic (default)"), ("mica", "Mica"),
                                                            ("mica_alt", "Mica Alt"), ("solid", "Solid")])),
            self._tint_card(),
            self._toggle_card("appearance.use_accent", "heart", "Use my Windows accent colour",
                              "Buttons, highlights and the active card's border use your Windows accent colour. "
                              "Turn off for JBrowser's blue."),
            _section("Motion and sound"),
            SettingCard("lightning", "Fluid animations",
                        "Cards, menus and the sidebar slide smoothly. Turn off if your PC feels slow or you prefer "
                        "less motion: everything then changes instantly.", self._toggle("appearance.animations")),
            self._toggle_card("appearance.window_animations", "restore", "Animate minimising and maximising",
                              "Windows' own animation when the window is minimised, maximised or restored. If the "
                              "window flickers or changes colour at those moments on your PC, turn this off."),
            self._toggle_card("appearance.sounds", "volume", "Sound effects",
                              "The gentle sounds of the welcome screen. JBrowser makes no sounds while you browse."),
            _section("Websites"),
            self._toggle_card("appearance.force_dark_web", "moon", "Dark mode for websites",
                              "Shows every website in dark colours, even ones without a dark theme. A few pages may "
                              "look odd; turn it off again if so."),
        )

    def _ribbon(self) -> QWidget:
        self._current_page = "ribbon"
        return self._page(
            "Ribbon and sidebar", "Choose what's on the ribbon at the top of the window and in the sidebar. "
                                  "Right-click the ribbon for the same choices.",
            _section("Ribbon"),
            self._toggle_card("toolbar.width_button", "columns", "Card width button",
                              "Shows the selected card's width. Click it to make the card 20%, 40%, 50%, 60%, 80% or "
                              "full width; the shortcuts are Alt+2, Alt+4, Alt+5, Alt+6, Alt+8 and Alt+0."),
            self._toggle_card("toolbar.reading_button", "reading", "Reading mode button",
                              "Reading mode is always on each card's title bar when a page looks like an article, and "
                              "F9 turns it on or off. Turn this on for a button on the ribbon as well."),
            self._home_card(),
            SettingCard("download", "Downloads button",
                        "Normally it only appears once you download something, and shows the progress as a "
                        "percentage. Downloads are always one Ctrl+J away.",
                        self._combo("toolbar.downloads_button", [("auto", "Show when downloading"),
                                                                 ("always", "Always show")], width=200)),
            self._toggle_card("appearance.favorites_bar", "bookmarks", "Show the bookmarks bar",
                              "Your bookmarked sites under the ribbon, one click away. Ctrl+D bookmarks a page and "
                              "Ctrl+Shift+B shows or hides the bar.", lambda v: self.ui.window.favbar.set_shown(v)),
            _section("Sidebar"),
            self._sidebar_card(),
            self._toggle_card("sidebar.new_card_always", "add", "Always show “New card” in the sidebar",
                              "When off, it only appears once a space has a card."),
        )

    def _defaults(self) -> QWidget:
        self._current_page = "defaults"
        self._default_status = {"browser": _hint(""), "pdf": _hint("")}
        self._refresh_defaults()
        return self._page(
            "Default apps", "Open links and PDF files from other apps in JBrowser. Windows lets only you choose "
                            "these, in Settings → Apps → Default apps: the buttons take you there.",
            SettingCard("globe", "Default browser",
                        "Links in emails, documents and other apps open in JBrowser, as do web pages saved on "
                        "this PC (.html).",
                        _button("Choose in Windows", win.open_default_apps), extra=self._default_status["browser"]),
            SettingCard("open_file", "PDF files",
                        "PDF files you double-click open in JBrowser's PDF viewer, where you can zoom, search, "
                        "print and save them. In Windows, find .pdf and choose JBrowser.",
                        _button("Choose in Windows", win.open_default_apps), extra=self._default_status["pdf"]),
            SettingCard("folder_open", "Open files from this PC",
                        "Type or paste a file's or folder's location into the Lazy Toolbar, such as "
                        "C:\\Users\\you\\Documents\\report.pdf (with or without quotes), or a network location like "
                        "\\\\server\\share. Press Enter to open it in a card."),
        )

    def _refresh_defaults(self) -> None:
        labels = getattr(self, "_default_status", None)
        if not labels:
            return
        where = win.registered_with_windows()
        if where is None:
            text = ("Windows doesn't know about this copy of JBrowser. Run the JBrowser installer and keep "
                    "“Register JBrowser as a web browser and PDF viewer” ticked.")
            for lab in labels.values():
                lab.setText(text)
            return
        labels["browser"].setText("✓ JBrowser is your default browser." if win.is_default("browser")
                                  else "Another browser opens links right now.")
        if not win.handles_pdf():
            labels["pdf"].setText("Install the latest JBrowser to offer it for PDF files.")
        else:
            labels["pdf"].setText("✓ JBrowser opens your PDF files." if win.is_default("pdf")
                                  else "Another app opens PDF files right now.")

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape and self.finder.text():
            self.finder.clear()                   # Esc ends a search first, then closes Settings
            return
        super().keyPressEvent(e)

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._refresh_defaults()              # back from Windows' Default apps
        super().changeEvent(e)

    def _reading_card(self) -> SettingCard:
        font = self._combo("reading.font", [("serif", "Serif text"), ("sans", "Sans-serif text")], width=170)
        colours = self._combo("reading.theme", [("auto", "Match JBrowser"), ("light", "Light"), ("sepia", "Sepia"),
                                                ("dark", "Dark")], width=170)
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        bl.addWidget(QLabel("Look"))
        bl.addWidget(font)
        bl.addWidget(colours)
        bl.addStretch(1)
        return SettingCard("reading", "Suggest reading mode on articles",
                           "Reading mode shows just the text and pictures of an article, without ads or clutter. "
                           "Turn it on with the reading button on the card's title bar, or press F9. When this "
                           "setting is on, JBrowser offers it once while you read an article.",
                           self._toggle("reading.offer"), extra=box)

    def _tint_card(self) -> SettingCard:
        picker = TintPicker(self.s.get("appearance.tint") or "none")
        picker.changed.connect(lambda key: self.s.set("appearance.tint", key))
        self._listen(self.s.changed, lambda k, v: picker.set_value(v or "none") if k == "appearance.tint" else None)
        return SettingCard("colour", "Colour tint",
                           "A gentle colour for the window (a little stronger with the Solid material). Incognito "
                           "spaces always stay black.", extra=picker)

    def _sidebar_card(self) -> SettingCard:
        sw = ToggleSwitch(not self.s.get("appearance.sidebar_collapsed"))
        sw.toggled.connect(lambda v: self.ui.set_sidebar_hidden(not v))

        def sync(k, v):
            if k == "appearance.sidebar_collapsed" and sw.isChecked() == bool(v):
                sw.blockSignals(True)
                sw.setChecked(not v)
                sw.knob = 0.0 if v else 1.0
                sw.blockSignals(False)
        self._listen(self.s.changed, sync)
        return SettingCard("sidebar", "Show the sidebar",
                           "Your favourites, spaces and cards on the left. When it's hidden, point at the left edge "
                           "to peek, or press Ctrl+B.", sw)

    def _home_card(self) -> SettingCard:
        mode = self._combo("toolbar.home_mode", [("lazy", "Open the Lazy Toolbar"), ("url", "Go to a web page")],
                           width=220)
        url = QLineEdit(self.s.get("toolbar.home_url") or "")
        url.setPlaceholderText("For example https://www.bbc.co.uk/news")
        url.setClearButtonEnabled(True)

        def save_url():
            text = url.text().strip()
            if text and "://" not in text:
                text = "https://" + text
            url.setText(text)
            self.s.set("toolbar.home_url", text)
            if text:
                self.s.set("toolbar.home_mode", "url")
                mode.setCurrentIndex(mode.findData("url"))

        url.editingFinished.connect(save_url)
        url.setEnabled(self.s.get("toolbar.home_mode") == "url")
        mode.currentIndexChanged.connect(lambda _i: url.setEnabled(mode.currentData() == "url"))
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        bl.addWidget(QLabel("When I press Home"))
        bl.addWidget(mode)
        bl.addWidget(url, 1)
        return SettingCard("home", "Show the Home button",
                           "A Home button next to Back, Forward and Reload. It can open the Lazy Toolbar or a page "
                           "you choose. Alt+Home works even when the button is hidden.",
                           self._toggle("toolbar.home_button"), extra=box)

    def _search(self) -> QWidget:
        self._current_page = "search"
        s = self.s
        self.kw_table = QTableWidget(0, 3)
        self.kw_table.setHorizontalHeaderLabels(["Keyword", "Name", "Address ({query} = your search)"])
        self.kw_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.kw_table.verticalHeader().setVisible(False)
        self.kw_table.setMinimumHeight(280)
        self._load_keywords()
        table_box = QWidget()
        tl = QVBoxLayout(table_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.kw_table)
        tl.addWidget(_buttons(_button("Add", lambda: self._add_keyword("", "", "https://")),
                              _button("Remove selected", self._remove_keyword),
                              _button("Restore defaults", self._reset_keywords),
                              _button("Save shortcuts", self._save_keywords, primary=True)))
        return self._page(
            "Search", "Where your searches go, and shortcuts for searching your favourite sites.",
            SettingCard("search", "Search engine",
                        "Used when you type words instead of a web address.",
                        self._combo("search.engine", [(k, v[0]) for k, v in ENGINES.items()])),
            SettingCard("sync", "Suggest searches as I type",
                        "Popular searches appear as you type. To find them, what you type is sent to Google. Never "
                        "used in incognito spaces.", self._toggle("search.suggestions")),
            SettingCard("tag", "Keyword shortcuts",
                        "Type a keyword, a space and your search to search one site directly: “w python” searches "
                        "Wikipedia, “gh qt” searches GitHub.",
                        extra=table_box),
            SettingCard("history", "Recent searches",
                        "Your last searches, so you can repeat them quickly.",
                        _button("Clear recent searches", lambda: (s.set("search.recent", []),
                                                                  self.ui.toast("Recent searches cleared", "clear")))),
        )

    def _load_keywords(self) -> None:
        self.kw_table.setRowCount(0)
        for d in self.s.get("search.keywords") or []:
            self._add_keyword(d.get("keyword", ""), d.get("name", ""), d.get("url", ""))

    def _add_keyword(self, k: str, n: str, u: str) -> None:
        r = self.kw_table.rowCount()
        self.kw_table.insertRow(r)
        for c, v in enumerate((k, n, u)):
            self.kw_table.setItem(r, c, QTableWidgetItem(v))

    def _remove_keyword(self) -> None:
        for r in sorted({i.row() for i in self.kw_table.selectedIndexes()}, reverse=True):
            self.kw_table.removeRow(r)

    def _reset_keywords(self) -> None:
        self.s.set("search.keywords", DEFAULT_SEARCH_KEYWORDS)
        self._load_keywords()

    def _save_keywords(self) -> None:
        out = []
        for r in range(self.kw_table.rowCount()):
            vals = [(self.kw_table.item(r, c).text().strip() if self.kw_table.item(r, c) else "") for c in range(3)]
            if vals[0] and "{query}" in vals[2]:
                out.append({"keyword": vals[0].lower(), "name": vals[1] or vals[0], "url": vals[2]})
        self.s.set("search.keywords", out)
        self.ui.toast(f"Saved {len(out)} keyword shortcuts", "search")

    def _privacy(self) -> QWidget:
        self._current_page = "privacy"
        ctx = self.ctx
        self.blocklist_label = _hint("")
        self._refresh_blocklist_label()
        self._listen(ctx.privacy.blocklistUpdated, lambda *_: self._refresh_blocklist_label())
        self._listen(ctx.threats.updated, lambda *_: self._refresh_blocklist_label())
        self.allow_list = QListWidget()
        self.allow_list.setMaximumHeight(120)
        self._load_allowlist()
        self._listen(self.s.changed, lambda k, _v: self._load_allowlist() if k == "privacy.allowlist" else None)
        lists_box = QWidget()
        lb = QVBoxLayout(lists_box)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.addWidget(self.blocklist_label)
        lb.addWidget(_buttons(_button("Update lists now", self._update_lists),
                              _button("Use built-in list only", ctx.privacy.reset_blocklist)))
        allow_box = QWidget()
        ab = QVBoxLayout(allow_box)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.addWidget(self.allow_list)
        ab.addWidget(_buttons(_button("Turn protection back on for selected", self._remove_allow)))
        return self._page(
            "Privacy and security",
            "JBrowser blocks tracking and dangerous sites from the start. Fine-tune it here.",
            _section("Protection"),
            SettingCard("shield", "Block trackers, ads, cryptominers and telemetry",
                        "Stops hidden scripts that follow you between sites, show ads, secretly mine cryptocurrency "
                        "or report what you do, and hides the empty ad boxes. Pages often load faster too. The "
                        "shield in the address bar shows how many were blocked. Lists used: EasyList, EasyPrivacy, "
                        "Peter Lowe and NoCoin.",
                        self._toggle("privacy.block_trackers"), extra=lists_box),
            SettingCard("warning", "Phishing and malware protection",
                        "Stops sites known for fake sign-in pages or harmful software before they load. The lists "
                        "are kept on this PC and updated weekly; the sites you visit are checked here and never sent "
                        "anywhere.", self._toggle("privacy.threat_protection"), token="warning"),
            SettingCard("fingerprint", "Fingerprinting protection",
                        "Some sites recognise your PC by how it draws images. JBrowser gives each site slightly "
                        "different, harmless answers, so it can't follow you that way. Sign-in and security-check "
                        "pages are left alone, so they don't take you for a robot.",
                        self._toggle("privacy.fingerprint_protection")),
            _section("Tracking"),
            SettingCard("link", "Remove tracking codes from links",
                        "Links often carry codes like “utm_source” or “fbclid” that tell companies where you came "
                        "from. JBrowser removes the common ones; pages work the same.",
                        self._toggle("privacy.strip_tracking")),
            SettingCard("people2", "Block third-party cookies",
                        "Cookies from companies other than the site you're on, mostly used for tracking. Blocking "
                        "them rarely breaks anything; if a sign-in fails, turn protection off for that site with the "
                        "shield in the address bar.",
                        self._toggle("privacy.block_third_party_cookies")),
            self._toggle_card("privacy.gpc", "shield", "Tell websites not to sell or share my data",
                              "Sends the Global Privacy Control signal. In places like California and the EU, sites "
                              "must respect it."),
            self._toggle_card("privacy.dnt", "shield", "Send “Do Not Track”",
                              "An older request not to be tracked. Many sites ignore it, but it does no harm."),
            _section("While you browse"),
            self._toggle_card("privacy.https_upgrade", "lock", "Always try the secure version of websites",
                              "Opens the encrypted (https) version of a site first. If there isn't one, the page "
                              "opens normally."),
            self._toggle_card("privacy.popup_blocking", "blocked", "Block pop-ups",
                              "Sites can't open new windows by themselves. Windows you open by clicking, such as "
                              "sign-in windows, still work."),
            self._toggle_card("privacy.webrtc_public_only", "network", "Hide my local network address",
                              "Video calls (WebRTC) can reveal addresses inside your home or office network. This "
                              "hides them without breaking calls."),
            self._toggle_card("privacy.block_autoplay", "mute", "Stop videos from playing on their own",
                              "Videos and sounds only start after you click on the page."),
            _section("Sites"),
            SettingCard("globe", "Sites with protection turned off",
                        "Sites you allowed to use trackers, for example because something didn't work. Select one "
                        "to turn protection back on.", extra=allow_box),
            SettingCard("permissions", "Cookies and site permissions",
                        "See and remove cookies, and choose which sites may use your camera, microphone, location or "
                        "notifications.",
                        _buttons(_button("Cookies", lambda: self.ui.open_dialog("cookies")),
                                 _button("Permissions", lambda: self.ui.open_dialog("permissions")))),
        )

    def _update_lists(self) -> None:
        self.ctx.privacy.update_blocklist()
        self.ctx.threats.refresh()
        self.ui.toast("Downloading the latest protection lists", "sync")

    def _refresh_blocklist_label(self) -> None:
        ts = self.s.get("privacy.blocklist_updated") or 0
        when = time.strftime("%d %b %Y %H:%M", time.localtime(ts)) if ts else "never (using the built-in list)"
        st = self.ctx.stats
        eng = self.ctx.privacy.filters
        extra = (f", {eng.network_count:,} address patterns and {eng.cosmetic_count:,} ad-hiding rules"
                 if eng is not None else "")
        self.blocklist_label.setText(
            f"Lists: {len(self.ctx.privacy.blocklist):,} tracker sites{extra}, and {len(self.ctx.threats):,} "
            f"dangerous sites. Updated: {when}. This session: {st.get('blocked', 0):,} requests blocked, "
            f"{self.ctx.privacy.stripped:,} tracking codes removed, {st.get('threats', 0):,} dangerous pages stopped.")

    def _load_allowlist(self) -> None:
        self.allow_list.clear()
        self.allow_list.addItems(self.s.get("privacy.allowlist") or [])

    def _remove_allow(self) -> None:
        for it in self.allow_list.selectedItems():
            self.ctx.privacy.set_site_protection(it.text(), True)

    # ------------------------------------------------------- clear data page
    def _clear(self) -> QWidget:
        self._current_page = "clear"
        ctx = self.ctx
        self.clear_range = QComboBox()
        for secs, label in CLEAR_RANGES:
            self.clear_range.addItem(label, secs)
        self.clear_range.setCurrentIndex(1)
        self.clear_space = QComboBox()
        self.clear_space.addItem("All spaces", None)
        for sp in ctx.state.spaces:
            self.clear_space.addItem(f"{sp.icon}  {sp.name}", sp.id)
        options = [
            ("history", "Browsing history", "Pages you visited, and the closed cards in the Archive.", True),
            ("downloads", "Download history", "The list of downloads. The files themselves stay.", True),
            ("cookies", "Cookies and other site data", "Signs you out of most sites. All cookies in the chosen "
                                                       "spaces are removed, whatever the time range.", True),
            ("cache", "Cached images and files", "Saved copies that make pages load faster. Some sites may load "
                                                 "a little slower next time.", True),
            ("searches", "Recent searches", "The searches shown in the Lazy Toolbar.", False),
            ("passwords", "Saved passwords", "Logins saved in the chosen time range. This can't be undone.", False),
            ("permissions", "Site permissions", "Your camera, microphone, location and notification choices.",
             False),
            ("zoom", "Zoom levels", "The zoom you set for each site.", False),
            ("favicons", "Site icons", "Small site logos kept for bookmarks and history.", False),
            ("storage", "Everything websites stored on this PC",
             "A deep clean of site storage, databases and offline data. Finishes the next time JBrowser starts.",
             False),
        ]
        self.clear_checks: dict[str, QCheckBox] = {}
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        for key, label, desc, default in options:
            cb = QCheckBox(label)
            cb.setChecked(default)
            self.clear_checks[key] = cb
            bl.addWidget(cb)
            h = _hint(desc)
            h.setContentsMargins(26, 0, 0, 4)
            bl.addWidget(h)
        pickers = QWidget()
        pl = QHBoxLayout(pickers)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel("Time range"))
        pl.addWidget(self.clear_range)
        pl.addSpacing(16)
        pl.addWidget(QLabel("Spaces"))
        pl.addWidget(self.clear_space)
        pl.addStretch(1)
        on_exit = QWidget()
        ol = QVBoxLayout(on_exit)
        ol.setContentsMargins(0, 0, 0, 0)
        current = set(self.s.get("privacy.clear_on_exit") or [])
        for key, label in (("history", "Browsing history"), ("cookies", "Cookies and site data"),
                           ("cache", "Cached images and files"), ("downloads", "Download history")):
            cb = QCheckBox(label)
            cb.setChecked(key in current)
            cb.toggled.connect(lambda on, k=key: self._set_clear_on_exit(k, on))
            ol.addWidget(cb)
        return self._page(
            "Clear browsing data",
            "Choose a time range and what to delete, then press Clear data.",
            SettingCard("clock", "Time range and spaces", "How far back to go, and which spaces to clean.",
                        extra=pickers),
            SettingCard("clear", "What to delete", "", extra=box),
            SettingCard("delete", "Clear now", "Deletes what you ticked, for the chosen time range and spaces.",
                        _button("Clear data", self._clear_now, primary=True)),
            SettingCard("power", "Clear automatically when JBrowser closes",
                        "What you tick here is deleted every time you close JBrowser.",
                        extra=on_exit),
        )

    def _set_clear_on_exit(self, key: str, on: bool) -> None:
        items = set(self.s.get("privacy.clear_on_exit") or [])
        items.add(key) if on else items.discard(key)
        self.s.set("privacy.clear_on_exit", sorted(items))

    def _clear_now(self) -> None:
        ctx = self.ctx
        checks = {k: cb.isChecked() for k, cb in self.clear_checks.items()}
        if not any(checks.values()):
            self.ui.toast("Tick at least one item to clear", "info")
            return
        secs = self.clear_range.currentData()
        start = time.time() - secs if secs else None
        sid = self.clear_space.currentData()
        spaces = [s for s in ctx.state.spaces if sid is None or s.id == sid]
        if checks["passwords"]:
            if QMessageBox.question(self, "Delete saved passwords",
                                    "Permanently delete the saved passwords from this time range?") \
                    != QMessageBox.StandardButton.Yes:
                return
            if self.ui.unlock_vault():
                for c in ctx.vault.entries():
                    if (sid is None or c.space_id in ("", sid)) and (start is None or c.created >= start):
                        ctx.vault.remove(c.id)
        if checks["history"]:
            ctx.history.clear(start, None, sid)
        if checks["downloads"]:
            for item in [i for i in ctx.downloads.items() if not i.active]:
                if (start is None or item.record.started >= start) and (sid is None or item.record.space_id == sid):
                    ctx.downloads.remove(item)
        if checks["searches"]:
            self.s.set("search.recent", [])
        for sp in spaces:
            prof = ctx.profiles.profile_for(sp)
            if checks["cookies"]:
                prof.cookieStore().deleteAllCookies()
            if checks["cache"]:
                prof.clearHttpCache()
                prof.clearAllVisitedLinks()
            if checks["permissions"]:
                for perm in prof.listAllPermissions():
                    perm.reset()
            if checks["storage"] and not sp.incognito:
                pending = self.s.get("profiles.pending_wipe") or []
                if sp.id not in pending:
                    self.s.set("profiles.pending_wipe", pending + [sp.id])
        if checks["zoom"]:
            self.s.set("zoom.sites", {})
        if checks["favicons"]:
            ctx.favicons.clear()
        self.ui.toast("Browsing data cleared", "clear")

    def _passwords(self) -> QWidget:
        self._current_page = "passwords"
        v = self.ctx.vault
        mode = "a master password" if v.mode == "master" else "your Windows account"
        return self._page(
            "Passwords", "JBrowser can remember your logins and fill them in for you.",
            SettingCard("key", "Offer to save passwords",
                        "After you sign in, JBrowser asks whether to remember the login. Nothing is saved unless "
                        "you say yes, and never in incognito spaces.",
                        self._toggle("passwords.offer_save")),
            SettingCard("edit", "Fill in logins automatically",
                        "With one saved login for a site, it's filled in as soon as the sign-in form appears. With "
                        "more, click the key on the card to choose.",
                        self._toggle("passwords.autofill")),
            SettingCard("warning", "Warn me about insecure sign-in pages",
                        "A warning when you type a password on an unencrypted (http) page, where others on the same "
                        "network could read it.",
                        self._toggle("passwords.warn_insecure"), token="warning"),
            SettingCard("lock", "How your passwords are protected",
                        f"They're encrypted (AES-256) with a key protected by {mode}, and never leave this PC. In "
                        "the password manager you can add a master password, find weak or reused passwords and "
                        "import logins from another browser.",
                        _button("Open password manager", lambda: self.ui.open_dialog("passwords"), primary=True)),
        )

    def _performance(self) -> QWidget:
        self._current_page = "performance"
        s = self.s
        self.never = QListWidget()
        self.never.setMaximumHeight(110)
        self.never.addItems(s.get("performance.never_sleep") or [])
        self.never_edit = QLineEdit()
        self.never_edit.setPlaceholderText("For example music.youtube.com")
        never_box = QWidget()
        nb = QVBoxLayout(never_box)
        nb.setContentsMargins(0, 0, 0, 0)
        nb.addWidget(self.never)
        row = QHBoxLayout()
        row.addWidget(self.never_edit, 1)
        row.addWidget(_button("Add", self._add_never))
        row.addWidget(_button("Remove selected", self._remove_never))
        nb.addLayout(row)
        tabs = self.ctx.state.all_tabs()
        stats = (f"{len(tabs)} cards open, {sum(1 for t in tabs if t.sleeping)} asleep and "
                 f"{sum(1 for t in tabs if t.throttled)} resting out of view.")
        return self._page(
            "Performance", "Keep JBrowser light on memory and battery, even with lots of cards open.",
            SettingCard("moon", "Memory saver",
                        "Cards you haven't looked at for a while go to sleep to free up memory, and wake instantly "
                        "when you click them. Cards playing sound or video, with unsaved typing, downloading or in a "
                        "call never sleep.",
                        self._combo("performance.sleep_preset",
                                    [(pid, label + (" (default)" if pid == "moderate" else ""))
                                     for pid, (label, _m) in SLEEP_PRESETS.items()])),
            SettingCard("pin", "Never put these sites to sleep",
                        "Sites that should always stay awake, such as music players or chat apps.",
                        extra=never_box),
            SettingCard("speed", "Rest cards that are out of view",
                        "A few seconds after a card leaves the screen, it stops drawing and pauses in the background "
                        "to save power. It's back to full speed the moment you scroll to it.",
                        self._toggle("performance.throttle")),
            SettingCard("info", "Right now", stats),
        )

    def _add_never(self) -> None:
        host = self.never_edit.text().strip().lower()
        if "://" in host:
            host = QUrl(host).host()
        if not host:
            return
        items = self.s.get("performance.never_sleep") or []
        if host not in items:
            items.append(host)
            self.s.set("performance.never_sleep", items)
            self.never.addItem(host)
        self.never_edit.clear()

    def _remove_never(self) -> None:
        items = self.s.get("performance.never_sleep") or []
        for it in self.never.selectedItems():
            items = [h for h in items if h != it.text()]
            self.never.takeItem(self.never.row(it))
        self.s.set("performance.never_sleep", items)

    def _network(self) -> QWidget:
        self._current_page = "network"
        dns_note = "" if self.ctx.dns.available else " (Not available in this version of Qt.)"
        self.proxy_label = QLabel()
        self.proxy_label.setProperty("carddesc", True)
        self.proxy_label.setWordWrap(True)
        self._refresh_proxy()
        self._listen(self.ctx.proxy.changed, lambda *_: self._refresh_proxy())
        proxy_box = QWidget()
        pb = QVBoxLayout(proxy_box)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.addWidget(self.proxy_label)
        pb.addWidget(_buttons(_button("Proxy for all spaces", lambda: self.ui.open_dialog("proxy")),
                              _button("Proxy for this space", lambda: self.ui.set_space_proxy())))
        return self._page(
            "Network and DNS", "How JBrowser connects to websites.",
            SettingCard("network", "DNS provider",
                        "DNS looks up a site's address from its name (like example.com). Quad9 (recommended) keeps "
                        "these look-ups encrypted and refuses known dangerous sites. Cloudflare encrypts them and is "
                        "very fast. “Windows default” uses your network's DNS, which usually isn't encrypted."
                        + dns_note,
                        self._combo("network.dns_mode", [("quad9", "Quad9 (recommended)"),
                                                         ("cloudflare", "Cloudflare 1.1.1.1"),
                                                         ("system", "Windows default")])),
            self._toggle_card("network.dns_fallback", "sync", "Fall back to Windows DNS if secure DNS fails",
                              "Some hotel, school or office networks block secure DNS. With this on, JBrowser uses "
                              "the normal Windows DNS there instead of showing an error."),
            SettingCard("vpn", "Proxy server",
                        "Sends your browsing through another server, as some workplaces and schools require. Leave "
                        "this alone unless you were given proxy details.", extra=proxy_box),
            SettingCard("developer", "Local development toolkit",
                        "For web developers: give local projects names like app.test and open common development "
                        "ports with one click.",
                        _button("Open toolkit", lambda: self.ui.open_dialog("devhosts"))),
        )

    def _refresh_proxy(self) -> None:
        self.proxy_label.setText(f"All spaces: {describe_proxy(self.s.get('network.proxy'))}. "
                                 f"In use right now: {self.ctx.proxy.description}.")

    def _downloads(self) -> QWidget:
        self._current_page = "downloads"
        self.dl_path = QLineEdit(self.ctx.downloads.default_directory())
        self.dl_path.setReadOnly(True)
        path_box = QWidget()
        pl = QHBoxLayout(path_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self.dl_path, 1)
        pl.addWidget(_button("Change", self._pick_dir))
        return self._page(
            "Downloads", "Where files go, and how JBrowser keeps you safe from harmful ones.",
            SettingCard("folder", "Save downloads to", "The folder for downloaded files.", extra=path_box),
            self._toggle_card("downloads.ask", "save", "Ask where to save each file",
                              "Choose the folder and name for every download."),
            SettingCard("shield", "Download protection",
                        "Watches for files that could harm your PC: programs and scripts (like .exe files), files "
                        "from sites on the dangerous-sites list, and files from sites without a secure connection "
                        "(no HTTPS).\n• Standard (recommended): warns you and lets you keep the file or delete it. "
                        "Until you decide, it's saved so it can't be opened by accident.\n• Strict: blocks those "
                        "downloads.\n• Off: no warnings.\nEvery file is also marked as coming from the internet, so "
                        "Windows SmartScreen checks it before it runs.",
                        self._combo("downloads.protection", [("standard", "Standard (recommended)"),
                                                             ("strict", "Strict"), ("off", "Off")], width=200),
                        token="warning"),
            SettingCard("download", "Your downloads", "See and open the files you downloaded.",
                        _button("Open downloads", lambda: self.ui.open_dialog("downloads"))),
        )

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Download folder", self.dl_path.text())
        if d:
            self.s.set("downloads.directory", d)
            self.dl_path.setText(d)

    def _advanced(self) -> QWidget:
        self._current_page = "advanced"
        paths = self.ctx.paths
        return self._page(
            "Advanced", "Extra tools for power users. Most people never need to change these.",
            _section("Tools"),
            SettingCard("code", "User scripts and styles",
                        "Add your own JavaScript or CSS to chosen websites, per site and per space. Useful for small "
                        "fixes and personal tweaks.",
                        _button("Open editor", lambda: self.ui.open_dialog("userscripts"))),
            SettingCard("folder_open", "Where JBrowser keeps its data",
                        f"Profiles and settings: {paths.data}\nCache: {paths.cache}",
                        _button("Open folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data))))),
            SettingCard("keyboard", "Keyboard shortcuts", "Every shortcut in one place.",
                        _button("Show shortcuts", lambda: (self.close(), self.ui.open_hotkeys()))),
            _section("Compatibility"),
            SettingCard("tiles", "Graphics acceleration",
                        "Uses your graphics card to draw pages quickly. If websites flicker, show stripes or draw in "
                        "the wrong place (it happens with some graphics cards and drivers), try “Compatible”, or "
                        "“Off” as a last resort: pages then draw more slowly, without the graphics card. Applies "
                        "after a restart.",
                        _buttons(self._combo("advanced.gpu_mode", [("auto", "Automatic (recommended)"),
                                                                    ("compatible", "Compatible"),
                                                                    ("off", "Off (slower, no glitches)")]),
                                 _button("Restart now", lambda: (self.close(), self.ui.restart())))),
            SettingCard("globe", "How JBrowser introduces itself to websites",
                        "Every browser tells websites its name and version (its “user agent”). JBrowser says it's "
                        "the newest Chrome, so no site treats it as outdated, and briefly says Firefox while you sign "
                        "in to Google, which Google needs. If Google keeps asking whether you're a robot, try "
                        "“Engine version”. If Google refuses to sign you in, press “Fix and sign in again” on the "
                        "message it shows: JBrowser then says Firefox to every site until you're signed in, and goes "
                        "back by itself. “Firefox” keeps it that way all the time.",
                        self._combo("advanced.identity", [("current", "Newest Chrome (recommended)"),
                                                          ("engine", "Engine version"),
                                                          ("firefox", "Firefox (for Google sign-in trouble)")])),
            self._toggle_card("advanced.media_notice", "info", "Explain videos JBrowser can't play",
                              "Shows a note when a video or sound uses a format JBrowser can't play (such as H.264), "
                              "so you know to open it in another browser."),
        )

    def _reset(self) -> QWidget:
        self._current_page = "reset"
        return self._page(
            "Reset", "Start over: just your settings, or everything.",
            SettingCard("sync", "Restore settings to their defaults",
                        "Every option goes back to how it was when JBrowser was installed. Your spaces, cards, "
                        "history, bookmarks and passwords stay.",
                        _button("Reset settings", self.ui.reset_settings)),
            SettingCard("delete", "Factory reset",
                        "Erases everything JBrowser stored on this PC: spaces and cards, cookies and sign-ins, "
                        "history, bookmarks, passwords, download list, user scripts, caches and settings. Files you "
                        "downloaded stay. JBrowser then restarts as if newly installed. This can't be undone.",
                        _button("Factory reset", self.ui.factory_reset, danger=True), token="danger"),
        )

    def _updates_card(self) -> SettingCard:
        from jbrowser import RELEASES_PAGE
        from jbrowser.ui.dialogs.update import status_text
        up = self.ctx.updater
        status = _hint(status_text(up))
        self._listen(up.stateChanged, lambda _s: status.setText(status_text(up)))
        auto = QCheckBox("Check for updates automatically (once a day)")
        auto.setChecked(bool(self.s.get("updates.auto_check")))
        auto.toggled.connect(lambda v: self.s.set("updates.auto_check", bool(v)))
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(status)
        bl.addWidget(auto)
        bl.addWidget(_buttons(_button("Check now", self.ui.check_for_updates, primary=True),
                              _button("Release notes", lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)))))
        how = ("When you agree, updates download and install themselves and JBrowser restarts on the new version. "
               "Each download is checked against its published fingerprint before it runs."
               if up.installed_copy() else
               "This copy isn't installed (it runs from source or a portable folder), so JBrowser tells you about "
               "new versions and links to the download page instead.")
        return SettingCard("download", "Updates", how, extra=box)

    def _about(self) -> QWidget:
        self._current_page = "about"
        from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

        from jbrowser.engine.identity import chrome_version
        # The engine's real Chromium, and the Chrome JBrowser presents itself as to websites.
        chrome = f"{qWebEngineChromiumVersion()} (sites see Chrome {chrome_version().split('.')[0]})"
        logo = QLabel()
        logo.setPixmap(logo_pixmap(88))
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(logo)
        info = QLabel(f"<div style='font-size:18pt'>{APP_NAME}</div><div>Version {__version__}</div>"
                      "<div style='margin-top:6px; font-size:11pt'>Welcome to the internet - again.</div>")
        info.setTextFormat(Qt.TextFormat.RichText)
        hl.addWidget(info, 1)
        made = QLabel("Made with \u2764\ufe0f by the JBrowser Team\n\u00a9 2026 The JBrowser Team. "
                      "All rights reserved.")
        made.setAlignment(Qt.AlignmentFlag.AlignCenter)
        made.setProperty("carddesc", True)
        made.setContentsMargins(0, 18, 0, 0)
        build = sys.getwindowsversion().build if sys.platform == "win32" else "-"
        return self._page(
            "About JBrowser", "",
            head,
            SettingCard("info", "Components",
                        f"Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}, Chromium {chrome}, "
                        f"Python {platform.python_version()}, Windows build {build}."),
            SettingCard("shield", "Privacy",
                        "No accounts, no telemetry. On its own, JBrowser only downloads its tracker and "
                        "dangerous-site lists, checks GitHub for updates once a day (sending nothing about you) and, "
                        "if they're on, fetches search suggestions as you type."),
            self._updates_card(),
            SettingCard("lightbulb", "Welcome tour",
                        "See the welcome screen again and take the short tour of JBrowser's main features.",
                        _button("Replay welcome", lambda: (self.close(), self.ui.window.start_onboarding(replay=True)))),
            made,
        )

