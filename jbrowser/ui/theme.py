"""Theme engine: dark/light palettes with alpha-layered surfaces over JBrowser's own Frosted look (ui/frost.py)
or a Solid colour. Windows are opaque; Windows' see-through materials are never used."""
from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPalette
from PyQt6.QtWidgets import QApplication

from jbrowser.core.settings import Settings
from jbrowser.platform import win
from jbrowser.ui.frost import frost

_theme: "Theme | None" = None

UI_FONT = "Segoe UI"          # Windows system UI font
FALLBACK_FONT = "Segoe UI"

DARK = {
    "window": "#1b1b1f", "text": "#f2f2f5", "text2": "rgba(255,255,255,0.66)", "text3": "rgba(255,255,255,0.42)",
    "sidebar": "rgba(10,10,14,0.10)", "sidebar_solid": "#1f1f24",
    "canvas": "rgba(0,0,0,0.20)", "canvas_solid": "#161619",
    "titlebar": "rgba(0,0,0,0.0)",
    "card": "rgba(38,38,44,0.96)", "card_solid": "#26262c", "card_border": "rgba(255,255,255,0.09)",
    "hover": "rgba(255,255,255,0.07)", "pressed": "rgba(255,255,255,0.12)", "selected": "rgba(255,255,255,0.10)",
    "divider": "rgba(255,255,255,0.08)", "panel": "rgba(34,34,40,0.985)", "panel_border": "rgba(255,255,255,0.10)",
    "input": "rgba(255,255,255,0.06)", "input_border": "rgba(255,255,255,0.10)", "scrim": "rgba(0,0,0,0.40)",
    "danger": "#ff6b6b", "warning": "#ffb74d", "success": "#5dd39e", "tooltip": "#2b2b31",
    "dialog": "rgba(28,28,33,0.78)", "dialog_solid": "#202025", "shadow": "rgba(0,0,0,0.45)",
    "sleep": "rgba(160,170,255,0.85)", "minimap": "rgba(255,255,255,0.10)",
    "window_tint": "rgba(10,10,14,0.16)", "layer": "rgba(32,32,38,0.70)", "layer_solid": "#232329",
    "card_hover": "rgba(255,255,255,0.045)", "focus_ring": "rgba(255,255,255,0.22)",
    "frost_tint": "rgba(20,20,26,0.80)",
}
LIGHT = {
    "window": "#f3f3f3", "text": "#1a1a1d", "text2": "rgba(0,0,0,0.62)", "text3": "rgba(0,0,0,0.42)",
    "sidebar": "rgba(255,255,255,0.20)", "sidebar_solid": "#ececef",
    "canvas": "rgba(0,0,0,0.035)", "canvas_solid": "#e4e4e8",
    "titlebar": "rgba(0,0,0,0.0)",
    "card": "rgba(252,252,253,0.97)", "card_solid": "#fcfcfd", "card_border": "rgba(0,0,0,0.10)",
    "hover": "rgba(0,0,0,0.05)", "pressed": "rgba(0,0,0,0.09)", "selected": "rgba(0,0,0,0.07)",
    "divider": "rgba(0,0,0,0.08)", "panel": "rgba(251,251,253,0.985)", "panel_border": "rgba(0,0,0,0.10)",
    "input": "rgba(0,0,0,0.035)", "input_border": "rgba(0,0,0,0.12)", "scrim": "rgba(0,0,0,0.22)",
    "danger": "#d64545", "warning": "#c77700", "success": "#1f9d63", "tooltip": "#ffffff",
    "dialog": "rgba(246,246,248,0.80)", "dialog_solid": "#f6f6f8", "shadow": "rgba(0,0,0,0.20)",
    "sleep": "rgba(90,100,200,0.85)", "minimap": "rgba(0,0,0,0.10)",
    "window_tint": "rgba(255,255,255,0.12)", "layer": "rgba(251,251,253,0.76)", "layer_solid": "#f9f9fb",
    "card_hover": "rgba(0,0,0,0.03)", "focus_ring": "rgba(0,0,0,0.22)",
    "frost_tint": "rgba(245,245,248,0.74)",
}


# Colour tints (Settings → Appearance, and the welcome's look page). With Frosted they are a light wash over
# the frosted picture; with Solid they are blended into the surfaces.
TINTS: dict[str, tuple[str, str]] = {
    "rose": ("Rose", "#e8577a"), "coral": ("Coral", "#ff7a59"), "amber": ("Amber", "#f0a830"),
    "lime": ("Lime", "#98c950"), "mint": ("Mint", "#3ecf9b"), "teal": ("Teal", "#23b0ad"),
    "sky": ("Sky", "#3fa7f5"), "indigo": ("Indigo", "#6c72ff"), "violet": ("Violet", "#a063ff"),
    "slate": ("Slate", "#7d8594"),
}
# How strongly the tint colours each solid surface (dark theme, light theme).
_SOLID_MIX = {"window": (0.20, 0.15), "sidebar_solid": (0.24, 0.19), "canvas_solid": (0.15, 0.12),
              "dialog_solid": (0.09, 0.07), "layer_solid": (0.09, 0.07), "card_solid": (0.05, 0.03)}
_WASH_ALPHA = (0.15, 0.10)          # the translucent wash (dark, light): a tint, never a paint job
_OUTLINE_WASH = (0.30, 0.12)        # how far the active card's outline is washed towards white (dark, light)
_OUTLINE_GREY = ("#8b9099", "#9aa0a8")   # the outline without a tint (dark, light)
# Incognito spaces always look black, whatever the theme or tint (like other browsers' private windows).
_INCOGNITO = {"window": "#0a0a0c", "sidebar_solid": "#0e0e11", "canvas_solid": "#070709", "card_solid": "#141417",
              "dialog_solid": "#121215", "layer_solid": "#141417", "sidebar": "rgba(0,0,0,0.30)",
              "canvas": "rgba(0,0,0,0.42)", "window_tint": "rgba(0,0,0,0.62)", "frost_tint": "rgba(6,6,8,0.93)"}
MATERIALS = ("frosted", "solid")


def mix(base: QColor, other: QColor, amount: float) -> QColor:
    """``base`` moved ``amount`` (0…1) of the way towards ``other``; keeps ``base``'s alpha."""
    a = max(0.0, min(1.0, amount))
    return QColor.fromRgbF(base.redF() + (other.redF() - base.redF()) * a,
                           base.greenF() + (other.greenF() - base.greenF()) * a,
                           base.blueF() + (other.blueF() - base.blueF()) * a, base.alphaF())


def solid(c: QColor) -> QColor:
    """``c`` fully opaque. For widgets drawn over web pages: Qt composites a partly transparent widget over a
    page far more see-through than its alpha suggests, so the page's text would show through."""
    out = QColor(c)
    out.setAlpha(255)
    return out


def parse_color(value: str) -> QColor:
    value = value.strip()
    if value.startswith("rgba"):
        parts = [p.strip() for p in value[value.index("(") + 1:value.rindex(")")].split(",")]
        r, g, b = (int(float(p)) for p in parts[:3])
        a = float(parts[3])
        return QColor(r, g, b, int(round(a * 255 if a <= 1 else a)))
    return QColor(value)


class Theme(QObject):
    changed = pyqtSignal()

    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        global _theme
        _theme = self
        self.settings = settings
        self.dark = True
        self.accent = QColor("#4c8dff")
        self.tokens: dict[str, str] = dict(DARK)
        # True with the Frosted look (JBrowser's own frosted picture under its windows, ui/frost.py); False
        # with Solid. Surfaces are partly see-through over the frosted picture and opaque with Solid.
        self.translucent = True
        self.tint: QColor | None = None
        self.incognito = False
        self._syncing = False
        self._colors: dict[str, QColor] = {}
        self._qss_tokens: dict[str, str] = dict(DARK)
        self._qss = ""                                  # the style sheet last given to Qt
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _s: self.refresh())
        settings.changed.connect(self._on_setting)
        self.refresh()

    def _on_setting(self, key: str, _v) -> None:
        if key in ("appearance.theme", "appearance.use_accent", "appearance.material", "appearance.tint"):
            self.refresh()

    def set_incognito(self, on: bool) -> None:
        """The active space is incognito: switch to the black look (and back)."""
        if bool(on) != self.incognito:
            self.incognito = bool(on)
            self.refresh()

    # ------------------------------------------------------------ resolution
    def _system_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        return True

    def _system_accent(self) -> QColor:
        c = None
        if hasattr(QPalette.ColorRole, "Accent"):
            c = QGuiApplication.palette().color(QPalette.ColorRole.Accent)
            if not c.isValid() or c == QColor("#000000"):
                c = None
        return c or win.system_accent_color() or QColor("#4c8dff")

    def _request_scheme(self, dark: bool | None) -> None:
        """Tell Qt which scheme JBrowser shows (None: follow Windows). Qt re-applies its own idea of
        light/dark to every window's frame whenever the application palette changes, which Windows
        triggers on its own (accent colour, energy saver, ...), so the two must agree."""
        hints = QGuiApplication.styleHints()
        if not hasattr(hints, "setColorScheme"):       # Qt < 6.8
            return
        self._syncing = True
        try:
            if dark is None:
                hints.unsetColorScheme()
            else:
                hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        finally:
            self._syncing = False

    def refresh(self) -> None:
        if self._syncing:            # colorSchemeChanged caused by _request_scheme itself
            return
        mode = self.settings.get("appearance.theme")
        follow_system = mode == "system" and not self.incognito
        if follow_system:
            self._request_scheme(None)                  # so _system_dark() reads Windows' own setting
        self.dark = self.incognito or (self._system_dark() if mode == "system" else mode == "dark")
        self.tokens = dict(DARK if self.dark else LIGHT)
        tint = TINTS.get(self.settings.get("appearance.tint") or "")
        self.tint = QColor(tint[1]) if tint and not self.incognito else None
        if self.incognito:
            self.tokens.update(_INCOGNITO)
        # The style sheet (menus, inputs, lists, ...) takes the colours without the tint: Qt restyles every widget
        # of the app when the style sheet changes (a third of a second with Settings open), and picking a colour
        # tint then never needs it.
        self._qss_tokens = dict(self.tokens)
        if self.tint is not None:
            i = 0 if self.dark else 1
            for key, amounts in _SOLID_MIX.items():
                self.tokens[key] = mix(parse_color(self.tokens[key]), self.tint, amounts[i]).name()
            wash = QColor(self.tint)
            wash.setAlphaF(_WASH_ALPHA[i])
            self.tokens["window_tint"] = (f"rgba({wash.red()},{wash.green()},{wash.blue()},"
                                          f"{wash.alphaF():.3f})")
        accent = self._system_accent() if self.settings.get("appearance.use_accent") else QColor("#4c8dff")
        if self.dark and accent.lightness() < 120:
            accent = accent.lighter(135)
        elif not self.dark and accent.lightness() > 170:
            accent = accent.darker(135)
        self.accent = accent
        self.translucent = self.settings.get("appearance.material") != "solid"
        self._colors = {k: parse_color(v) for k, v in self.tokens.items()}
        self._colors["accent"] = QColor(accent)
        self.apply()
        # Only now tell Qt the scheme: it re-applies light/dark to every window frame when the scheme
        # changes, judging by the palette, which must already be the new one.
        if not follow_system:
            self._request_scheme(self.dark)
        self.changed.emit()

    def c(self, token: str) -> QColor:
        if token == "accent":
            return QColor(self.accent)
        return QColor(self._colors.get(token, QColor("#ff00ff")))

    def accent_text(self) -> QColor:
        a = self.accent
        lum = 0.2126 * a.redF() + 0.7152 * a.greenF() + 0.0722 * a.blueF()
        return QColor("#111111") if lum > 0.6 else QColor("#ffffff")

    def accent_alpha(self, alpha: float) -> QColor:
        c = QColor(self.accent)
        c.setAlphaF(alpha)
        return c

    def card_outline(self, alpha: float = 0.9) -> QColor:
        """Outline of the active card: a washed (paler, slightly see-through) version of the colour
        tint, or grey with *No colour* and in incognito spaces."""
        base = QColor(self.tint) if self.tint is not None else QColor(_OUTLINE_GREY[0 if self.dark else 1])
        c = mix(base, QColor("#ffffff"), _OUTLINE_WASH[0 if self.dark else 1])
        c.setAlphaF(alpha)
        return c

    def backdrop_wash(self) -> QColor | None:
        """Colour laid over the frosted picture: the tint, black for incognito, or None."""
        if self.incognito or self.tint is not None:
            return self.c("window_tint")
        return None

    def frost_look(self) -> tuple:
        """What the frosted picture depends on besides the wallpaper: its tint and the colour wash."""
        wash = self.backdrop_wash()
        return self.c("frost_tint").rgba(), (wash.rgba() if wash is not None else 0)

    def paint_backdrop(self, p: QPainter, widget, rect, layer: str | None = None) -> None:
        """Paint the window's background under ``rect`` of ``widget``: the Frosted picture (fitted to the
        widget's window, so every widget's part lines up), or the Solid colour. ``layer`` is a surface token
        laid over it (the canvas's), baked into the picture so it costs nothing extra."""
        if self.translucent:
            frost().paint(p, widget, rect, self.frost_look(), self.c(layer).rgba() if layer else 0)
        else:
            p.fillRect(rect, self.c(layer + "_solid") if layer and layer + "_solid" in self._colors
                       else self.c("window"))

    def surface(self, token: str) -> QColor:
        """Surface colour: partly see-through over Frosted, opaque with Solid."""
        if not self.translucent and token + "_solid" in self._colors:
            return self.c(token + "_solid")
        return self.c(token)

    # ------------------------------------------------------------------ QSS
    def font_family(self) -> str:
        from PyQt6.QtGui import QFontDatabase
        fams = set(QFontDatabase.families())
        return UI_FONT if UI_FONT in fams else FALLBACK_FONT

    def apply(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        font = QFont(self.font_family())
        font.setPointSizeF(9.5)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
        pal = QPalette()
        text = self.c("text")
        pal.setColor(QPalette.ColorRole.Window, self.c("window"))
        pal.setColor(QPalette.ColorRole.WindowText, text)
        pal.setColor(QPalette.ColorRole.Base, self.c("dialog_solid"))
        pal.setColor(QPalette.ColorRole.AlternateBase, self.c("card_solid"))
        pal.setColor(QPalette.ColorRole.Text, text)
        pal.setColor(QPalette.ColorRole.Button, self.c("card_solid"))
        pal.setColor(QPalette.ColorRole.ButtonText, text)
        pal.setColor(QPalette.ColorRole.Highlight, self.accent)
        pal.setColor(QPalette.ColorRole.HighlightedText, self.accent_text())
        pal.setColor(QPalette.ColorRole.ToolTipBase, self.c("tooltip"))
        pal.setColor(QPalette.ColorRole.ToolTipText, text)
        pal.setColor(QPalette.ColorRole.PlaceholderText, self.c("text3"))
        pal.setColor(QPalette.ColorRole.Link, self.accent)
        app.setPalette(pal)
        qss = self.stylesheet()
        if qss != self._qss:                            # restyling is slow: only when it changed
            self._qss = qss
            app.setStyleSheet(qss)                      # (repaints every widget)
        else:
            for w in app.topLevelWidgets():             # the new colours, everywhere (the main window repaints
                if w.isVisible():                       # its root itself, on `changed`)
                    w.update()

    def stylesheet(self) -> str:
        t = self._qss_tokens
        a = self.accent.name()
        at = self.accent_text().name()
        a_soft = f"rgba({self.accent.red()},{self.accent.green()},{self.accent.blue()},0.22)"
        a_hover = self.accent.lighter(112).name() if self.dark else self.accent.darker(110).name()
        # Menus are opaque (Windows 11 rounds their corners).
        menu_bg = t["dialog_solid"]
        menu_border = f"1px solid {t['panel_border']}"
        from jbrowser.ui.icons import glyph_png
        check_png = glyph_png("check", self.accent_text(), 14)
        arrow_png = glyph_png("chev_down", self.c("text2"), 12)
        up_png = glyph_png("chev_up", self.c("text2"), 10)
        down_png = glyph_png("chev_down", self.c("text2"), 10)
        return f"""
* {{ outline: none; }}
QToolTip {{ background: {t['tooltip']}; color: {t['text']}; border: 1px solid {t['panel_border']};
            padding: 5px 8px; }}
QMenu {{ background: {menu_bg}; color: {t['text']}; border: {menu_border}; padding: 5px; }}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 6px; margin: 1px 2px; }}
QMenu::item:selected {{ background: {t['hover']}; }}
QMenu::item:disabled {{ color: {t['text3']}; }}
QMenu::separator {{ height: 1px; background: {t['divider']}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t['text3']}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t['text2']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background: {t['input']}; color: {t['text']}; border: 1px solid {t['input_border']};
    border-radius: 7px; padding: 5px 8px; selection-background-color: {a}; selection-color: {at}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 1px solid {a}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {t['text3']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({arrow_png}); width: 12px; height: 12px; }}
QSpinBox::up-arrow, QDateEdit::up-arrow {{ image: url({up_png}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDateEdit::down-arrow {{ image: url({down_png}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {t['dialog_solid']}; color: {t['text']};
    border: 1px solid {t['panel_border']}; padding: 4px; selection-background-color: {t['hover']};
    selection-color: {t['text']}; }}
QSpinBox::up-button, QSpinBox::down-button, QDateEdit::up-button, QDateEdit::down-button {{ width: 16px; border: none; }}
QCalendarWidget QWidget {{ alternate-background-color: {t['input']}; }}

QPushButton {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['input_border']};
    border-radius: 7px; padding: 6px 14px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['pressed']}; }}
QPushButton:disabled {{ color: {t['text3']}; }}
QPushButton[primary="true"] {{ background: {a}; color: {at}; border: 1px solid {a}; }}
QPushButton[primary="true"]:hover {{ background: {a_hover}; }}
QPushButton[danger="true"] {{ color: {t['danger']}; }}
QPushButton:flat {{ background: transparent; border: none; }}

QCheckBox, QRadioButton {{ color: {t['text']}; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {t['text3']};
    background: {t['input']}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {a}; border: 1px solid {a}; }}
QCheckBox::indicator:checked {{ image: url({check_png}); }}

QListView, QTreeView, QTableView, QListWidget, QTreeWidget, QTableWidget {{
    background: {t['input']}; color: {t['text']}; border: 1px solid {t['input_border']}; border-radius: 8px;
    alternate-background-color: transparent; selection-background-color: {a_soft}; selection-color: {t['text']}; }}
QTableView {{ gridline-color: transparent; }}
QTableView::item, QTreeView::item, QListView::item {{ padding: 4px 6px; border: none; }}
QTableView::item:hover, QTreeView::item:hover, QListView::item:hover {{ background: {t['hover']}; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{ background: {a_soft}; color: {t['text']}; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{ background: transparent; color: {t['text2']}; border: none;
    border-bottom: 1px solid {t['divider']}; padding: 6px 8px; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {t['text2']}; padding: 7px 14px; border-radius: 7px; margin: 2px; }}
QTabBar::tab:selected {{ background: {t['selected']}; color: {t['text']}; }}
QTabBar::tab:hover {{ background: {t['hover']}; }}

QSlider::groove:horizontal {{ height: 4px; background: {t['input_border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0; background: {a}; border-radius: 7px; }}
QProgressBar {{ background: {t['input']}; border: none; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {a}; border-radius: 3px; }}
QGroupBox {{ color: {t['text2']}; border: 1px solid {t['divider']}; border-radius: 10px; margin-top: 16px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
QLabel {{ color: {t['text']}; background: transparent; }}
QLabel[muted="true"] {{ color: {t['text2']}; }}
QLabel[heading="true"] {{ font-size: 17pt; font-weight: 600; }}
QLabel[subheading="true"] {{ font-size: 10.5pt; }}
QLabel[section="true"] {{ font-size: 10.5pt; color: {t['text']}; padding-top: 6px; }}
QLabel[cardtitle="true"] {{ font-size: 10pt; }}
QLabel[carddesc="true"] {{ font-size: 9pt; color: {t['text2']}; }}
QLabel[hint="true"] {{ font-size: 8.5pt; color: {t['text3']}; }}
QFrame#SettingCard {{ background: {t['card_hover']}; border: 1px solid {t['divider']}; border-radius: 9px; }}
QSplitter::handle {{ background: {t['divider']}; }}
QSplitter::handle:hover {{ background: {a}; }}

QWidget#DialogBody {{ background: transparent; }}
QStackedWidget#SettingsStack > QWidget {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""


def theme() -> Theme:
    assert _theme is not None, "Theme not initialised"
    return _theme
