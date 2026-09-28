"""Hotkey cheat sheet (Ctrl+/ or F1), generated from the command registry."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QKeySequence, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from jbrowser.core.fuzzy import best_match
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import IconButton, Overlay

if TYPE_CHECKING:
    from jbrowser.context import AppContext

EXTRA = [
    ("Canvas & layout", "Pan the canvas", "Alt + Mouse wheel · trackpad swipe"),
    ("Canvas & layout", "Multi-select cards", "Ctrl + Click / Shift + Click on card headers"),
    ("Canvas & layout", "Reorder cards", "Drag a card header"),
    ("Canvas & layout", "Toggle full width", "Double-click a card header"),
    ("Spaces", "Switch spaces from the sidebar", "↑ / ↓ (space list focused)"),
    ("Cards", "Close card", "Middle-click header or sidebar entry"),
    ("Navigation", "Back / forward", "Mouse side buttons"),
    ("Lazy Toolbar", "Scopes", "> commands · @ cards · * bookmarks · # history · $ passwords"),
    ("Lazy Toolbar", "Keyword search", "e.g. “yt lofi”, “gh qt”, “w python” (configure in Settings)"),
    ("Lazy Toolbar", "Open in the other target", "Shift + Enter"),
    ("Page", "Find next / previous", "Enter / Shift + Enter in the find bar"),
]


class KeyCaps(QWidget):
    def __init__(self, parts: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self._parts = [p for p in parts if p]
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        self.setFont(f)
        fm = self.fontMetrics()
        w = sum(fm.horizontalAdvance(p) + 14 for p in self._parts) + 6 * max(0, len(self._parts) - 1)
        self.setFixedSize(QSize(max(10, w), 22))

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = self.fontMetrics()
        x = 0.0
        for part in self._parts:
            w = fm.horizontalAdvance(part) + 14
            r = QRectF(x, 1, w, 20)
            path = QPainterPath()
            path.addRoundedRect(r, 5, 5)
            p.fillPath(path, th.c("input"))
            p.setPen(QPen(th.c("input_border"), 1))
            p.drawPath(path)
            p.setPen(th.c("text"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, part)
            x += w + 6
        p.end()


class HotkeySheet(Overlay):
    def __init__(self, ctx: "AppContext", host: QWidget):
        super().__init__(host)
        self.ctx = ctx
        self.panel = QFrame(self)
        self.panel.setObjectName("HotkeyPanel")
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(22, 18, 14, 16)
        lay.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Keyboard shortcuts", self.panel)
        title.setProperty("heading", True)
        top.addWidget(title)
        top.addStretch(1)
        self.filter = QLineEdit(self.panel)
        self.filter.setPlaceholderText("Filter shortcuts…")
        self.filter.setFixedWidth(240)
        self.filter.textChanged.connect(self._populate)
        top.addWidget(self.filter)
        close = IconButton("close", "Close (Esc)", self.panel, size=32, glyph_px=11)
        close.clicked.connect(self.close_overlay)
        top.addWidget(close)
        lay.addLayout(top)
        self.scroll = QScrollArea(self.panel)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self.scroll, 1)
        theme().changed.connect(self._restyle)
        self._restyle()

    def _restyle(self) -> None:
        t = theme().tokens
        self.panel.setStyleSheet(f"#HotkeyPanel{{background:{t['panel']};border:1px solid {t['panel_border']};"
                                 f"border-radius:16px;}}")

    def panel_rect(self) -> QRect:
        return self.panel.geometry()

    def open_sheet(self) -> None:
        self.filter.clear()
        self._populate()
        self.open_overlay()
        self._layout()
        self.filter.setFocus()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout()

    def _layout(self) -> None:
        r = self.rect()
        w = min(1000, r.width() - 80)
        h = min(720, r.height() - 80)
        self.panel.setGeometry((r.width() - w) // 2, (r.height() - h) // 2, w, h)

    def _populate(self) -> None:
        q = self.filter.text().strip()
        rows: dict[str, list[tuple[str, list[str]]]] = {}
        for cmd in self.ctx.commands.all():
            if not cmd.shortcuts:
                continue
            if cmd.id.startswith("card.goto") and cmd.id not in ("card.goto1", "card.goto_last"):
                continue
            if cmd.id.startswith("layout.scale") and cmd.id not in ("layout.scale1", "layout.scale5",
                                                                    "layout.scale10"):
                continue
            title = cmd.title
            keys = [QKeySequence(sc).toString(QKeySequence.SequenceFormat.NativeText) for sc in cmd.shortcuts]
            if cmd.id == "card.goto1":
                title, keys = "Go to card 1 – 8", ["Ctrl+1 … Ctrl+8"]
            elif cmd.id == "layout.scale1":
                title, keys = "Scale selected card(s) to 10% – 90%", ["Alt+1 … Alt+9"]
            elif cmd.id == "layout.scale5":
                title, keys = "50% split width", ["Alt+5"]
            if q and best_match(q, title, " ".join(keys), cmd.category) is None:
                continue
            rows.setdefault(cmd.category, []).append((title, keys))
        for cat, title, keys in EXTRA:
            if q and best_match(q, title, keys, cat) is None:
                continue
            rows.setdefault(cat, []).append((title, [keys]))
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 10, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(4)
        cols = 2
        col_widgets = [QVBoxLayout() for _ in range(cols)]
        heights = [0] * cols
        for cat, items in rows.items():
            target = heights.index(min(heights))
            box = col_widgets[target]
            head = QLabel(cat.upper())
            f = head.font()
            f.setPointSizeF(8)
            f.setWeight(QFont.Weight.Medium)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
            head.setFont(f)
            head.setProperty("muted", True)
            box.addSpacing(10)
            box.addWidget(head)
            for title, keys in items:
                row = QHBoxLayout()
                lab = QLabel(title)
                lab.setWordWrap(True)
                row.addWidget(lab, 1)
                row.addWidget(KeyCaps(keys))
                box.addLayout(row)
            heights[target] += len(items) + 2
        for i, box in enumerate(col_widgets):
            box.addStretch(1)
            grid.addLayout(box, 0, i)
        if not rows:
            grid.addWidget(QLabel("No shortcuts match."), 0, 0)
        self.scroll.setWidget(body)
