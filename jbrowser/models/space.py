"""Space model: an isolated workspace with its own web profile."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jbrowser.models.tab import Tab

SPACE_COLORS = ["#4c8dff", "#a66bff", "#ff6b9a", "#ff9f43", "#2ecc71", "#1abc9c", "#f1c40f", "#e74c3c"]
SPACE_ICONS = ["🏠", "💼", "🛠️", "🔬", "🎮", "🎵", "📚", "✈️", "💡", "🧪", "📰", "🛒", "🎨", "🌱", "⚡", "🕶️"]


@dataclass(eq=False)
class Space:
    name: str
    icon: str = "🏠"
    color: str = SPACE_COLORS[0]
    incognito: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    tabs: list[Tab] = field(default_factory=list)
    active_tab_id: str = ""
    selected: set[str] = field(default_factory=set)
    anchor_tab_id: str = ""             # range-selection anchor
    proxy: dict | None = None           # per-space proxy override (None = inherit global)
    scroll: float = 0.0                 # persisted canvas offset

    def index_of(self, tab_id: str) -> int:
        for i, t in enumerate(self.tabs):
            if t.id == tab_id:
                return i
        return -1

    def active_tab(self) -> Tab | None:
        for t in self.tabs:
            if t.id == self.active_tab_id:
                return t
        return None
