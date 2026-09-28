"""Create / edit a space (name, icon, color, incognito)."""
from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QWidget)

from jbrowser.models.space import SPACE_COLORS, SPACE_ICONS, Space
from jbrowser.ui.dialogs.base import JDialog


class SpaceDialog(JDialog):
    def __init__(self, ctx, space: Space | None, parent: QWidget | None = None):
        super().__init__("Edit space" if space else "New space", parent, (460, 420), modal=True)
        self.ctx = ctx
        self._icon = space.icon if space else SPACE_ICONS[len(ctx.state.spaces) % len(SPACE_ICONS)]
        self._color = space.color if space else SPACE_COLORS[len(ctx.state.spaces) % len(SPACE_COLORS)]
        form = QFormLayout()
        form.setSpacing(12)
        self.name = QLineEdit(space.name if space else "")
        self.name.setPlaceholderText("e.g. Work, Research, Side project")
        form.addRow("Name", self.name)

        icons = QWidget()
        grid = QGridLayout(icons)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self._icon_buttons: list[QPushButton] = []
        for i, emoji in enumerate(SPACE_ICONS):
            b = QPushButton(emoji)
            b.setCheckable(True)
            b.setChecked(emoji == self._icon)
            b.setFixedSize(QSize(38, 34))
            f = b.font()
            f.setFamily("Segoe UI Emoji")
            f.setPointSizeF(13)
            b.setFont(f)
            b.clicked.connect(lambda _c=False, e=emoji: self._pick_icon(e))
            self._icon_buttons.append(b)
            grid.addWidget(b, i // 8, i % 8)
        self.custom_icon = QLineEdit()
        self.custom_icon.setPlaceholderText("…or type any emoji")
        self.custom_icon.setMaxLength(4)
        self.custom_icon.textChanged.connect(lambda t: self._pick_icon(t.strip()) if t.strip() else None)
        grid.addWidget(self.custom_icon, 2, 0, 1, 8)
        form.addRow("Icon", icons)

        colors = QWidget()
        cg = QGridLayout(colors)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(6)
        self._color_buttons: list[QPushButton] = []
        for i, col in enumerate(SPACE_COLORS + ["custom"]):
            b = QPushButton("…" if col == "custom" else "")
            b.setFixedSize(28, 28)
            b.setCheckable(col != "custom")
            if col != "custom":
                b.setStyleSheet(f"QPushButton{{background:{col};border-radius:14px;border:2px solid transparent;}}"
                                f"QPushButton:checked{{border:2px solid white;}}")
                b.setChecked(col == self._color)
                b.clicked.connect(lambda _c=False, cc=col: self._pick_color(cc))
            else:
                b.clicked.connect(self._custom_color)
            self._color_buttons.append(b)
            cg.addWidget(b, 0, i)
        form.addRow("Color", colors)
        self.incognito = QCheckBox("Incognito (kept in memory only, nothing is written to disk)")
        self.incognito.setChecked(bool(space and space.incognito))
        self.incognito.setEnabled(space is None)
        form.addRow("", self.incognito)
        self.root.addLayout(form)
        note = QLabel("Every space has its own isolated cookies, logins, storage and cache.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        self.root.addWidget(note)
        self.root.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Save" if space else "Create space")
        ok.setProperty("primary", True)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)
        self.name.setFocus()

    def _pick_icon(self, emoji: str) -> None:
        self._icon = emoji
        for b in self._icon_buttons:
            b.setChecked(b.text() == emoji)

    def _pick_color(self, color: str) -> None:
        self._color = color
        for b, c in zip(self._color_buttons, SPACE_COLORS):
            b.setChecked(c == color)

    def _custom_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Space color")
        if c.isValid():
            self._pick_color(c.name())

    def _accept(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            self.name.setPlaceholderText("Please enter a name")
            return
        self.accept()

    def values(self) -> tuple[str, str, str, bool]:
        return self.name.text().strip(), self._icon or "🏠", self._color, self.incognito.isChecked()
