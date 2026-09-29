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

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from jbrowser import APP_NAME, __version__
from jbrowser.core.settings import DEFAULT_SEARCH_KEYWORDS, SLEEP_PRESETS
from jbrowser.services.network import describe_proxy
from jbrowser.services.search import ENGINES
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.icons import draw_glyph, icon, logo_pixmap
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import TintPicker, ToggleSwitch

NAV_W = 250

PAGES = [
    ("general", "General", "home"), ("appearance", "Appearance", "sun"), ("search", "Search", "search"),
    ("privacy", "Privacy and security", "shield"), ("clear", "Clear browsing data", "clear"),
    ("passwords", "Passwords", "key"), ("performance", "Performance", "speed"),
    ("network", "Network and DNS", "network"), ("downloads", "Downloads", "download"),
    ("advanced", "Advanced", "developer"), ("reset", "Reset", "sync"), ("about", "About JBrowser", "info"),
]

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
        builders = {"general": self._general, "appearance": self._appearance, "search": self._search,
                    "privacy": self._privacy, "clear": self._clear, "passwords": self._passwords,
                    "performance": self._performance, "network": self._network, "downloads": self._downloads,
                    "advanced": self._advanced, "reset": self._reset, "about": self._about}
        for key, label, glyph in PAGES:
            it = QListWidgetItem(icon(glyph), label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setSizeHint(QSize(200, 38))
            self.nav.addItem(it)
            self._index[key] = self.stack.count()
            self._current_page = key
            self.stack.addWidget(builders[key]())
        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(0)

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
            "QListWidget::item{padding:8px 10px;border-radius:7px;margin:1px 0;}"
            f"QListWidget::item:selected{{background:{t['selected']};color:{t['text']};}}"
            f"QListWidget::item:hover:!selected{{background:{t['hover']};}}")

    def _on_nav(self, row: int) -> None:
        item = self.nav.item(row)
        if item is not None:
            self.stack.setCurrentIndex(self._index[item.data(Qt.ItemDataRole.UserRole)])

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
        for w in widgets:
            if w is None:
                continue
            if isinstance(w, int):
                lay.addSpacing(w)
            elif isinstance(w, SettingCard):
                self._cards.append((self._current_page, w))
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
        for i in range(self.nav.count()):
            key = self.nav.item(i).data(Qt.ItemDataRole.UserRole)
            self.nav.item(i).setHidden(bool(words) and key not in pages_with_hits and key != "about")
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
            "The basics. If you are new to JBrowser, start here: every option below explains what it does, and you "
            "can change anything back at any time.",
            SettingCard("home", "Reopen my cards when JBrowser starts",
                        "When this is on, the cards you had open in each space come back the next time you open "
                        "JBrowser. Only the cards you can see are loaded straight away; the others wait quietly "
                        "until you click them, so start-up stays fast. Your spaces and signed-in websites are kept "
                        "either way.", self._toggle("startup.restore_session")),
            SettingCard("search", "Search engine",
                        "The service used when you type words (rather than a web address) into the Lazy Toolbar. "
                        "You can still search with any engine by typing its keyword first, for example “yt cats” "
                        "for YouTube (see Search).",
                        self._combo("search.engine", [(k, v[0]) for k, v in ENGINES.items()])),
            SettingCard("columns", "Width of new cards",
                        "Cards sit side by side on a long horizontal canvas. This decides how wide a new card is. "
                        "Half means two cards fit on screen together; full width gives one card the whole screen. "
                        "Resize any time: select cards and press Alt+1 to Alt+9 (10% to 90%) or Alt+0 (100%).",
                        self._combo("canvas.default_width", width_options)),
            SettingCard("grid", "Show the overview strip under the cards",
                        "A thin bar at the bottom of the canvas that shows every card as a small block and "
                        "highlights the part you are looking at. Click or drag it to jump around quickly.",
                        self._toggle("canvas.show_minimap")),
            SettingCard("lightbulb", "How to get around",
                        "Hold Alt and turn the mouse wheel to slide the canvas sideways. Alt+← and Alt+→ move "
                        "between cards, Alt+↑ and Alt+↓ switch spaces. Press Ctrl+T to open a new card, Ctrl+K to "
                        "search everything, and Ctrl+/ to see every keyboard shortcut.",
                        _button("Show shortcuts", lambda: (self.close(), self.ui.open_hotkeys()))),
        )

    def _appearance(self) -> QWidget:
        self._current_page = "appearance"
        return self._page(
            "Appearance", "How JBrowser looks and moves.",
            SettingCard("lightning", "Fluid animations",
                        "Smooth sliding and resizing of cards, the sidebar, menus and the Lazy Toolbar. Turn this "
                        "off if your computer feels slow or if you prefer less motion on screen; every change will "
                        "then happen instantly instead of animating.", self._toggle("appearance.animations")),
            SettingCard("sun", "Theme",
                        "Dark or light colours. “Match Windows” follows the colour mode you picked in Windows "
                        "Settings and switches automatically when you change it.",
                        self._combo("appearance.theme", [("system", "Match Windows"), ("dark", "Dark"),
                                                         ("light", "Light")])),
            SettingCard("tiles", "Window material",
                        "The see-through effect behind the sidebar and title bar. Acrylic softly blurs whatever is "
                        "behind the window. Mica gently tints the window with your desktop wallpaper. Mica Alt is a "
                        "stronger tint. Solid turns transparency off and uses the least graphics power.",
                        self._combo("appearance.material", [("acrylic", "Acrylic (default)"), ("mica", "Mica"),
                                                            ("mica_alt", "Mica Alt"), ("solid", "Solid")])),
            self._tint_card(),
            self._toggle_card("appearance.use_accent", "heart", "Use my Windows accent colour",
                              "Highlights, buttons and the active card border use the accent colour you chose in "
                              "Windows. Turn off to use JBrowser's blue."),
            self._sidebar_card(),
            self._toggle_card("sidebar.new_card_always", "add", "Always show the “New card” button",
                              "The “New card” row under the cards in the sidebar. When this is off, it only appears "
                              "once a space has at least one card."),
            self._toggle_card("appearance.favorites_bar", "bookmarks", "Show the bookmarks bar",
                              "A row of your bookmarked sites under the ribbon, one click away. Bookmark the current "
                              "page with Ctrl+D. You can also toggle the bar with Ctrl+Shift+B or by right-clicking "
                              "the ribbon.", lambda v: self.ui.window.favbar.set_shown(v)),
            self._home_card(),
            self._toggle_card("appearance.sounds", "volume", "Sound effects",
                              "Plays the gentle sounds of the welcome screen. JBrowser never plays sounds while you "
                              "browse; websites control their own audio."),
            self._toggle_card("appearance.force_dark_web", "moon", "Dark mode for websites",
                              "Asks every website to render with dark colours, even sites that have no dark theme "
                              "of their own. Some pages may look odd; switch it off again if so."),
        )

    def _tint_card(self) -> SettingCard:
        picker = TintPicker(self.s.get("appearance.tint") or "none")
        picker.changed.connect(lambda key: self.s.set("appearance.tint", key))
        self._listen(self.s.changed, lambda k, v: picker.set_value(v or "none") if k == "appearance.tint" else None)
        return SettingCard("colour", "Colour tint",
                           "Gives the window a gentle colour. With Acrylic or Mica it is a light tint over the "
                           "see-through background; with the Solid material the colour is a little stronger. "
                           "Incognito spaces always stay black.", extra=picker)

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
                           "The panel on the left with your favourites, spaces and cards. When it is hidden, point "
                           "at the left edge of the window to peek at it, press Ctrl+B, or right-click the ribbon "
                           "to bring it back.", sw)

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
                           "Adds a Home button next to Back, Forward and Reload on the ribbon. Choose whether it "
                           "opens the Lazy Toolbar (search or type an address) or takes you to a page you pick. "
                           "Alt+Home works even when the button is hidden.",
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
            "Search", "Choose where your searches go and set up shortcuts for your favourite sites.",
            SettingCard("search", "Search engine",
                        "Used whenever you type words into the Lazy Toolbar instead of a web address.",
                        self._combo("search.engine", [(k, v[0]) for k, v in ENGINES.items()])),
            SettingCard("sync", "Show search suggestions while I type",
                        "Shows popular searches from Google as you type, so you can pick one instead of typing it "
                        "all. To do this, what you type is sent to Google. Suggestions are never requested in "
                        "incognito spaces.", self._toggle("search.suggestions")),
            SettingCard("tag", "Keyword shortcuts",
                        "Type a keyword, a space and your search in the Lazy Toolbar to search a particular site "
                        "directly. For example “w python” searches Wikipedia and “gh qt” searches GitHub.",
                        extra=table_box),
            SettingCard("history", "Recent searches",
                        "JBrowser remembers your last searches so you can repeat them quickly. Clear the list here.",
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
            "JBrowser blocks tracking and dangerous sites by default. These switches let you fine-tune that.",
            SettingCard("shield", "Block trackers, ads, cryptominers and telemetry",
                        "Stops websites from loading hidden scripts that follow you from site to site, show ads, "
                        "secretly use your computer to mine cryptocurrency, or report what you do, and hides the "
                        "empty ad boxes they leave behind. Pages usually load faster too. The shield in the title "
                        "bar shows how many were blocked. Uses the EasyList, EasyPrivacy, Peter Lowe and NoCoin "
                        "lists.",
                        self._toggle("privacy.block_trackers"), extra=lists_box),
            SettingCard("warning", "Phishing and malware protection",
                        "Warns you and stops the page before it loads if a site is on public lists of fake login "
                        "pages and sites that spread harmful software. The lists are downloaded to this computer and "
                        "refreshed about once a week; the addresses you visit are checked locally and never sent "
                        "anywhere.", self._toggle("privacy.threat_protection"), token="warning"),
            SettingCard("fingerprint", "Fingerprinting protection",
                        "Websites can recognise your computer by quietly measuring how it draws images. JBrowser "
                        "gives each site slightly different, harmless answers so that measurement cannot be used to "
                        "follow you. Sign-in and security-check pages (Google, Microsoft, Cloudflare and similar) "
                        "are left alone, so they don't mistake you for a robot.",
                        self._toggle("privacy.fingerprint_protection")),
            SettingCard("link", "Remove tracking codes from links",
                        "Many links carry extra codes (like “utm_source” or “fbclid”) that tell companies where you "
                        "came from. JBrowser removes the common ones before the page opens. The page itself works "
                        "the same.", self._toggle("privacy.strip_tracking")),
            SettingCard("people2", "Block third-party cookies",
                        "Cookies are small files websites store. “Third-party” cookies come from companies other than "
                        "the site you are on and are mostly used for tracking. Blocking them rarely breaks sites; "
                        "if a sign-in fails, turn protection off for that site from the address bar.",
                        self._toggle("privacy.block_third_party_cookies")),
            self._toggle_card("privacy.gpc", "shield", "Tell websites not to sell or share my data",
                              "Sends the Global Privacy Control signal with every visit. In some regions (such as "
                              "California and the EU) websites are legally required to respect it."),
            self._toggle_card("privacy.dnt", "shield", "Send “Do Not Track”",
                              "An older request asking websites not to track you. Many sites ignore it, but it does "
                              "no harm to send."),
            self._toggle_card("privacy.https_upgrade", "lock", "Always try the secure version of websites",
                              "When a link points to an insecure “http” address, JBrowser tries the encrypted “https” "
                              "version first. If the site does not support it, the page still opens normally."),
            self._toggle_card("privacy.popup_blocking", "blocked", "Block pop-ups",
                              "Stops websites from opening new windows on their own. Pop-ups you open by clicking, "
                              "such as sign-in windows, still work."),
            self._toggle_card("privacy.webrtc_public_only", "network", "Hide my local network address",
                              "Video-call technology (WebRTC) can reveal addresses inside your home or office network. "
                              "This keeps them hidden without breaking calls."),
            self._toggle_card("privacy.block_autoplay", "mute", "Stop videos from playing on their own",
                              "Videos and sounds only start after you click on the page."),
            SettingCard("globe", "Sites with protection turned off",
                        "Sites you have allowed to use trackers, for example because something did not work. "
                        "Select a site and turn protection back on.", extra=allow_box),
            SettingCard("permissions", "Cookies and site permissions",
                        "See and remove cookies, and review which sites may use your camera, microphone, location or "
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
        when = time.strftime("%d %b %Y %H:%M", time.localtime(ts)) if ts else "never (built-in list only)"
        st = self.ctx.stats
        eng = self.ctx.privacy.filters
        extra = (f" plus {eng.network_count:,} address patterns and {eng.cosmetic_count:,} ad-box hiding rules"
                 if eng is not None else "")
        self.blocklist_label.setText(
            f"{len(self.ctx.privacy.blocklist):,} tracker domains{extra}, and {len(self.ctx.threats):,} dangerous sites "
            "known. "
            f"Tracker lists last updated: {when}. This session: {st.get('blocked', 0):,} requests blocked, "
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
            ("history", "Browsing history", "The list of pages you have visited, and the closed cards kept in "
                                            "the Archive.", True),
            ("downloads", "Download history", "The list of files you downloaded. The files themselves stay "
                                              "where they are.", True),
            ("cookies", "Cookies and other site data", "Signs you out of most websites. Websites don't record "
                                                       "when a cookie was set, so all cookies in the chosen "
                                                       "spaces are removed.", True),
            ("cache", "Cached images and files", "Copies of pages kept to load them faster. Some sites may "
                                                 "load a little slower the next time.", True),
            ("searches", "Recent searches", "The searches shown in the Lazy Toolbar.", False),
            ("passwords", "Saved passwords", "Logins saved during the chosen time range. This cannot be "
                                             "undone.", False),
            ("permissions", "Site permissions", "Camera, microphone, location and notification choices you "
                                                "made for websites.", False),
            ("zoom", "Zoom levels", "The zoom you set for individual websites.", False),
            ("favicons", "Site icons", "Small website logos kept for bookmarks and history.", False),
            ("storage", "Everything websites stored on this computer",
             "Deep clean of local storage, databases and offline data. Takes effect the next time JBrowser "
             "starts.", False),
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
            "Delete what JBrowser has saved while you browsed. Pick a time range and what to remove, then press "
            "Clear data.",
            SettingCard("clock", "What and when", "Choose how far back to go and which spaces to clean.",
                        extra=pickers),
            SettingCard("clear", "Choose what to delete", "", extra=box),
            SettingCard("delete", "Clear now", "Deletes the items you ticked for the chosen time range and spaces.",
                        _button("Clear data", self._clear_now, primary=True)),
            SettingCard("power", "Clear automatically when JBrowser closes",
                        "Anything you tick here is deleted every time you close JBrowser, so it never builds up.",
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
                        "After you sign in to a website, JBrowser asks whether to remember the username and "
                        "password. Nothing is saved unless you say yes, and incognito spaces never save.",
                        self._toggle("passwords.offer_save")),
            SettingCard("edit", "Fill in logins automatically",
                        "When a site has exactly one saved login, JBrowser fills it in as soon as the sign-in form "
                        "appears. With several logins, click the key in the card header to choose one.",
                        self._toggle("passwords.autofill")),
            SettingCard("warning", "Warn me about insecure sign-in pages",
                        "Shows a warning when you type a password on a page that does not use encryption (http), "
                        "because others on the same network could read it.",
                        self._toggle("passwords.warn_insecure"), token="warning"),
            SettingCard("lock", "How your passwords are protected",
                        f"Passwords are encrypted with AES-256 and the key is protected by {mode}. They never leave "
                        "this computer. You can add a master password, check for weak or reused passwords and import "
                        "logins from another browser in the password manager.",
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
        stats = (f"Right now: {len(tabs)} cards open, {sum(1 for t in tabs if t.sleeping)} asleep and "
                 f"{sum(1 for t in tabs if t.throttled)} resting because they are out of view.")
        return self._page(
            "Performance", "Keep JBrowser light on memory and battery, even with many cards open.",
            SettingCard("moon", "Memory saver",
                        "Cards you have not looked at for a while are put to sleep to free up memory. A sleeping "
                        "card shows a faded picture with a moon and wakes up instantly when you click it. Cards "
                        "that are playing sound or video, have unsaved typing, are downloading or are in a call "
                        "are never put to sleep.",
                        self._combo("performance.sleep_preset",
                                    [(pid, label + (" (default)" if pid == "moderate" else ""))
                                     for pid, (label, _m) in SLEEP_PRESETS.items()])),
            SettingCard("pin", "Never put these sites to sleep",
                        "Add sites that should always stay awake, such as music players or chat apps.",
                        extra=never_box),
            SettingCard("speed", "Rest cards that are out of view",
                        "Five seconds after a card scrolls off screen (or its space is hidden), JBrowser stops "
                        "drawing it and pauses its background timers, saving processor and battery power. It comes "
                        "back to full speed the moment you scroll to it.", self._toggle("performance.throttle")),
            SettingCard("info", "Current status", stats),
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
            "Network and DNS", "How JBrowser finds and connects to websites.",
            SettingCard("network", "DNS provider",
                        "DNS turns names like example.com into the numeric addresses computers use. Quad9 "
                        "(recommended) encrypts these look-ups and refuses to look up known dangerous sites. "
                        "Cloudflare encrypts them and is very fast. “Windows default” uses whatever your network "
                        "provides, which is usually not encrypted." + dns_note,
                        self._combo("network.dns_mode", [("quad9", "Quad9 (recommended)"),
                                                         ("cloudflare", "Cloudflare 1.1.1.1"),
                                                         ("system", "Windows default")])),
            self._toggle_card("network.dns_fallback", "sync", "Fall back to Windows DNS if secure DNS fails",
                              "If the secure DNS service cannot be reached (for example on some hotel or office "
                              "networks), use the normal Windows DNS instead of showing an error."),
            SettingCard("vpn", "Proxy server",
                        "A proxy sends your browsing through another server, often required at work or school. "
                        "Leave this alone unless you were given proxy details.", extra=proxy_box),
            SettingCard("developer", "Local development toolkit",
                        "For web developers: give local projects friendly names like app.test and open common "
                        "development ports with one click.",
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
            "Downloads", "Where files are saved and how they are checked.",
            SettingCard("folder", "Save downloads to",
                        "The folder where downloaded files go.", extra=path_box),
            self._toggle_card("downloads.ask", "save", "Ask where to save each file",
                              "Shows a Save dialog for every download so you can pick the folder and file name."),
            SettingCard("shield", "Download protection",
                        "Asks before keeping programs and scripts (like .exe or .msi files), and warns louder when "
                        "they come over an insecure connection. Every downloaded file is also marked as coming from "
                        "the internet, so Windows SmartScreen and Office can check it before it runs.",
                        self._toggle("downloads.protect")),
            SettingCard("download", "Your downloads", "See, open and manage files you have downloaded.",
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
            "Advanced", "Extra tools for power users.",
            SettingCard("code", "User scripts and styles",
                        "Add your own JavaScript or CSS to chosen websites, per site and per space. Useful for small "
                        "fixes and personal tweaks.",
                        _button("Open editor", lambda: self.ui.open_dialog("userscripts"))),
            SettingCard("folder_open", "Where JBrowser keeps its data",
                        f"Profiles and settings: {paths.data}\nCache: {paths.cache}",
                        _button("Open folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data))))),
            SettingCard("keyboard", "Keyboard shortcuts", "Every shortcut in one place.",
                        _button("Show shortcuts", lambda: (self.close(), self.ui.open_hotkeys()))),
        )

    def _reset(self) -> QWidget:
        self._current_page = "reset"
        return self._page(
            "Reset", "Start over, either for your settings only or for everything.",
            SettingCard("sync", "Restore settings to their defaults",
                        "Puts every option back the way it was when JBrowser was installed. Your spaces, cards, "
                        "history, bookmarks and saved passwords are not touched.",
                        _button("Reset settings", self.ui.reset_settings)),
            SettingCard("delete", "Factory reset",
                        "Erases everything JBrowser has stored on this computer: all spaces and cards, cookies and "
                        "signed-in sessions, history, bookmarks, saved passwords, download records, user scripts, "
                        "caches and settings. Files you downloaded are kept. JBrowser then restarts as if it had "
                        "just been installed. This cannot be undone.",
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
        how = ("Updates download and install themselves after you agree, and JBrowser restarts on the new version. "
               "Every download is checked against its published fingerprint before it runs."
               if up.installed_copy() else
               "This copy runs from source or a portable folder, so JBrowser tells you about new versions and "
               "links to the download page instead of installing them.")
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
        made = QLabel("Made with \u2764\ufe0f by the JBrowser Company\n\u00a9 2026 The JBrowser Company. "
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
                        "JBrowser has no accounts and no telemetry. The only network requests it makes on its own "
                        "are downloading the tracker and dangerous-site lists, a daily update check with GitHub "
                        "(it sends nothing about you), and, if enabled, search suggestions while you type."),
            self._updates_card(),
            SettingCard("lightbulb", "Welcome tour",
                        "Watch the welcome screen again and take the short guided tour of JBrowser's main features.",
                        _button("Replay welcome", lambda: (self.close(), self.ui.window.start_onboarding(replay=True)))),
            made,
        )

