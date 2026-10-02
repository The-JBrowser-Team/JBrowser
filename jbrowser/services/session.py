"""Session persistence: spaces, card layout and full back/forward history per card."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QTimer

from jbrowser.core.jsonstore import atomic_write_json, read_json
from jbrowser.core.settings import Settings
from jbrowser.models.state import BrowserState
from jbrowser.models.tab import Tab

log = logging.getLogger(__name__)

DEFAULT_SPACES = [
    ("Home", "🏠", "#4c8dff"),
    ("Work", "💼", "#a66bff"),
    ("Other", "✨", "#2ecc71"),
]
# Default spaces shipped by 1.0; empty ones are retired by the 1.1 migration.
_LEGACY_OPTIONAL = {("Development", "🛠️"), ("Research", "🔬")}


class SessionManager(QObject):
    AUTOSAVE_MS = 15000

    def __init__(self, state: BrowserState, settings: Settings, path: Path,
                 history_provider: Callable[[Tab], bytes | None], parent: QObject | None = None):
        super().__init__(parent)
        self.state = state
        self.settings = settings
        self._path = path
        self._history = history_provider
        self._last_digest = ""
        self._dirty = True
        self.dropped_spaces: list[str] = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(2500)
        self._debounce.timeout.connect(self.save_now)
        self._periodic = QTimer(self)
        self._periodic.setInterval(self.AUTOSAVE_MS)
        self._periodic.timeout.connect(lambda: self.save_now() if self._dirty else None)
        state.dirty.connect(self.mark_dirty)

    SESSION_FIELDS = frozenset({"url", "title", "width", "zoom", "muted", "pinned", "stack"})

    def mark_dirty(self, *_args) -> None:
        self._dirty = True
        self._debounce.start()

    def on_tabs_flushed(self, summary: dict) -> None:
        """Pipeline hook: only session-relevant tab changes schedule a save."""
        if any(fields & self.SESSION_FIELDS for fields in summary.values()):
            self._dirty = True

    def start(self) -> None:
        self._periodic.start()

    def snapshot(self) -> dict:
        spaces = []
        for sp in self.state.spaces:
            if sp.incognito:
                continue
            tabs = []
            for t in sp.tabs:
                if not t.url or t.url.startswith(("about:blank", "data:")):
                    continue
                hist = self._history(t)
                tabs.append({"id": t.id, "url": t.url, "title": t.title, "width": round(t.width, 4),
                             "zoom": t.zoom, "muted": t.muted, "pinned": t.pinned, "favourite": t.favourite_id,
                             "stack": t.stack,
                             "history": base64.b64encode(hist).decode("ascii") if hist else ""})
            spaces.append({"id": sp.id, "name": sp.name, "icon": sp.icon, "color": sp.color,
                           "proxy": sp.proxy, "active_tab": sp.active_tab_id, "scroll": sp.scroll,
                           "tabs": tabs})
        active = self.state.active_space
        return {"version": 1, "saved": time.time(),
                "active_space": active.id if active and not active.incognito else "",
                "spaces": spaces}

    def save_now(self) -> None:
        self._debounce.stop()
        self._dirty = False
        try:
            data = self.snapshot()
        except RuntimeError as exc:  # engine objects already torn down
            log.debug("Session snapshot skipped: %s", exc)
            return
        body = dict(data)
        body.pop("saved", None)
        digest = hashlib.sha1(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
        if digest == self._last_digest:
            return
        self._last_digest = digest
        atomic_write_json(self._path, data)

    def _migrate_spaces(self, data: dict) -> dict:
        """1.0 → 1.1: Personal becomes Home, empty Development/Research retire, Other is added."""
        spaces = data.get("spaces") or []
        kept = []
        for sd in spaces:
            if (sd.get("name"), sd.get("icon")) in _LEGACY_OPTIONAL and not sd.get("tabs"):
                if sd.get("id"):
                    self.dropped_spaces.append(sd["id"])
                continue
            if sd.get("name") == "Personal" and sd.get("icon") == "🏠":
                sd["name"] = "Home"
            kept.append(sd)
        if kept and not any(sd.get("name") == "Other" for sd in kept):
            kept.append({"name": "Other", "icon": "✨", "color": "#2ecc71", "tabs": []})
        data["spaces"] = kept
        return data

    def restore(self, restore_tabs: bool | None = None, migrate_from: int = 2) -> bool:
        """Populate the state from disk. Returns False when there was nothing to restore."""
        data = read_json(self._path, None)
        self.dropped_spaces: list[str] = []
        if isinstance(data, dict) and migrate_from < 2:
            data = self._migrate_spaces(data)
        if restore_tabs is None:
            restore_tabs = bool(self.settings.get("startup.restore_session"))
        if not isinstance(data, dict) or not data.get("spaces"):
            for name, icon, color in DEFAULT_SPACES:
                self.state.add_space(name, icon, color, activate=False)
            self.state.set_active_space(self.state.spaces[0].id)
            return False
        for sd in data["spaces"]:
            space = self.state.add_space(sd.get("name") or "Space", sd.get("icon") or "🏠", sd.get("color"),
                                         activate=False, space_id=sd.get("id"), proxy=sd.get("proxy"))
            space.scroll = float(sd.get("scroll") or 0.0)
            if not restore_tabs:
                continue
            for td in sd.get("tabs", []):
                hist = base64.b64decode(td["history"]) if td.get("history") else None
                self.state.add_tab(space.id, td.get("url", ""), index=len(space.tabs), activate=False,
                                   width=float(td.get("width") or 0.5), title=td.get("title", ""),
                                   tab_id=td.get("id"), sleeping=True, history=hist,
                                   zoom=float(td.get("zoom") or 1.0), muted=bool(td.get("muted")),
                                   pinned=bool(td.get("pinned")), favourite_id=td.get("favourite") or "",
                                   stack=str(td.get("stack") or ""))
            self.state.normalize_stacks(space)       # skipped cards (blank pages) may have broken a column
            if sd.get("active_tab") and self.state.tab(sd["active_tab"]):
                self.state.set_active_tab(sd["active_tab"])
        target = self.state.space(data.get("active_space", "")) or (self.state.spaces[0] if self.state.spaces else None)
        if target:
            self.state.set_active_space(target.id)
        return True
