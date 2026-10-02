"""Tab state model and the asynchronous, coalescing tab-update pipeline.

Web engine signals (title, favicon, progress, audio, ...) fire at high frequency and for
cards the user cannot currently see. Instead of pushing each one straight into widgets,
controllers write into a :class:`Tab` model; the :class:`TabUpdatePipeline` batches dirty
fields and flushes them at most once per frame. Views then decide whether to repaint now
(visible) or merely remember that they are stale (off-screen / hidden space).
"""
from __future__ import annotations

import time
import uuid

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon

_pipeline: "TabUpdatePipeline | None" = None


class TabUpdatePipeline(QObject):
    """Coalesces tab field changes and emits them once per ~frame."""

    flushed = pyqtSignal(dict)  # {tab_id: frozenset(fields)}

    FRAME_MS = 16

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        global _pipeline
        _pipeline = self
        self._dirty: dict[str, tuple["Tab", set[str]]] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self.flush)

    def mark(self, tab: "Tab", fields: set[str]) -> None:
        entry = self._dirty.get(tab.id)
        if entry is None:
            self._dirty[tab.id] = (tab, set(fields))
        else:
            entry[1].update(fields)
        if not self._timer.isActive():
            self._timer.start()

    def flush(self) -> None:
        if not self._dirty:
            return
        batch, self._dirty = self._dirty, {}
        summary: dict[str, frozenset] = {}
        for tab_id, (tab, fields) in batch.items():
            if tab.disposed:
                continue
            frozen = frozenset(fields)
            summary[tab_id] = frozen
            tab.changed.emit(frozen)
        if summary:
            self.flushed.emit(summary)


def pipeline() -> TabUpdatePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = TabUpdatePipeline()
    return _pipeline


class Tab(QObject):
    """Pure state for one web card. Never touches widgets or the web engine directly."""

    changed = pyqtSignal(object)  # frozenset[str] of changed field names

    def __init__(self, space_id: str, url: str = "", title: str = "", width: float = 0.5,
                 tab_id: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.id: str = tab_id or uuid.uuid4().hex
        self.space_id = space_id
        self.url = url
        self.title = title
        self.icon = QIcon()
        self.loading = False
        self.progress = 0
        self.can_back = False
        self.can_forward = False
        self.loaded = False            # has the engine ever loaded this card?
        self.sleeping = False          # hibernated by the memory saver (or lazily restored)
        self.throttled = False         # rendering throttled / JS frozen while out of view
        self.audible = False
        self.muted = False
        self.crashed = False
        self.width = width             # fraction of canvas width (0.1 .. 1.0)
        self.zoom = 1.0
        self.blocked = 0               # trackers blocked on the current page
        self.saved_logins = 0          # saved credentials for the current origin
        self.devtools = False
        self.secure = False
        self.pending_history: bytes | None = None
        self.pinned = False            # kept at the start of its space, no close button
        self.favourite_id = ""         # set when the card was opened from a sidebar favourite
        self.stack = ""                # shared by cards stacked in one column (models/state.py)
        self.readable = False          # the page looks like an article (engine/reader.py)
        self.reading = False           # shown in reading mode
        self.last_active = time.monotonic()
        self.created = time.time()
        self.disposed = False

    def update(self, **fields) -> None:
        dirty = set()
        for name, value in fields.items():
            if getattr(self, name) != value or name == "icon":
                setattr(self, name, value)
                dirty.add(name)
        if dirty:
            pipeline().mark(self, dirty)

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def display_title(self) -> str:
        from jbrowser.core.urls import display_title
        return display_title(self.title, self.url)
