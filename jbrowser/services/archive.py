"""The Archive: cards closed in the last 48 hours, ready to be reopened.

Entries keep the card's address, title, space and full back/forward history. They expire
after 48 hours, are never recorded for incognito spaces, and are removed together with the
matching browsing history (clearing history by time range, by site or all at once).
"""
from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_json, read_json
from jbrowser.core.urls import strip_www

RETENTION_S = 48 * 3600
MAX_ENTRIES = 300


class ArchiveEntry:
    __slots__ = ("id", "url", "title", "space_id", "space_name", "space_icon", "closed_at", "width", "pinned",
                 "history")

    def __init__(self, url: str, title: str = "", space_id: str = "", space_name: str = "", space_icon: str = "",
                 closed_at: float | None = None, width: float = 0.5, pinned: bool = False, history: str = "",
                 id: str | None = None):
        self.id = id or uuid.uuid4().hex[:16]
        self.url = url
        self.title = title
        self.space_id = space_id
        self.space_name = space_name
        self.space_icon = space_icon
        self.closed_at = closed_at if closed_at is not None else time.time()
        self.width = width
        self.pinned = pinned
        self.history = history            # base64 of the serialised QWebEngineHistory

    @property
    def host(self) -> str:
        return strip_www(QUrl(self.url).host().lower())

    def history_bytes(self) -> bytes | None:
        try:
            return base64.b64decode(self.history) if self.history else None
        except ValueError:
            return None

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


class ArchiveService(QObject):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        self._entries: list[ArchiveEntry] = []
        raw = read_json(path, [])
        if isinstance(raw, list):
            for d in raw:
                if isinstance(d, dict) and d.get("url"):
                    try:
                        self._entries.append(ArchiveEntry(**{k: d[k] for k in ArchiveEntry.__slots__ if k in d}))
                    except TypeError:
                        continue
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.save_now)
        self._expiry = QTimer(self)
        self._expiry.setInterval(10 * 60 * 1000)
        self._expiry.timeout.connect(self.prune)
        self._expiry.start()
        self.prune()

    # --------------------------------------------------------------- queries
    def entries(self) -> list[ArchiveEntry]:
        """Newest first."""
        return sorted(self._entries, key=lambda e: e.closed_at, reverse=True)

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, entry_id: str) -> ArchiveEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    # --------------------------------------------------------------- changes
    def add_closed(self, data: dict) -> ArchiveEntry:
        hist = data.get("history")
        entry = ArchiveEntry(url=data["url"], title=data.get("title", ""), space_id=data.get("space_id", ""),
                             space_name=data.get("space_name", ""), space_icon=data.get("space_icon", ""),
                             width=float(data.get("width") or 0.5), pinned=bool(data.get("pinned")),
                             history=base64.b64encode(hist).decode("ascii") if hist else "")
        # Closing the same page again replaces the older entry.
        self._entries = [e for e in self._entries if not (e.url == entry.url and e.space_id == entry.space_id)]
        self._entries.append(entry)
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self.entries()[:MAX_ENTRIES]
        self._changed()
        return entry

    def take(self, entry_id: str) -> ArchiveEntry | None:
        """Remove and return an entry (used when it is reopened)."""
        entry = self.get(entry_id)
        if entry is not None:
            self._entries.remove(entry)
            self._changed()
        return entry

    def take_latest(self, space_ids: set[str] | None = None) -> ArchiveEntry | None:
        for entry in self.entries():
            if space_ids is None or entry.space_id in space_ids:
                return self.take(entry.id)
        return None

    def remove(self, entry_id: str) -> None:
        self.take(entry_id)

    def clear(self) -> None:
        if self._entries:
            self._entries = []
            self._changed()

    def prune(self) -> None:
        cutoff = time.time() - RETENTION_S
        kept = [e for e in self._entries if e.closed_at >= cutoff]
        if len(kept) != len(self._entries):
            self._entries = kept
            self._changed()

    # -------------------------------------------- kept in step with history
    def purge_range(self, start: float | None, end: float | None, space_id: str | None) -> None:
        def hit(e: ArchiveEntry) -> bool:
            return ((start is None or e.closed_at >= start) and (end is None or e.closed_at <= end)
                    and (not space_id or e.space_id == space_id))
        self._drop(hit)

    def purge_host(self, host: str) -> None:
        host = strip_www(host.lower())
        self._drop(lambda e: e.host == host or e.host.endswith("." + host))

    def purge_urls(self, urls: list[str]) -> None:
        wanted = set(urls)
        self._drop(lambda e: e.url in wanted)

    def purge_space(self, space_id: str) -> None:
        self._drop(lambda e: e.space_id == space_id)

    def _drop(self, predicate) -> None:
        kept = [e for e in self._entries if not predicate(e)]
        if len(kept) != len(self._entries):
            self._entries = kept
            self._changed()

    # ------------------------------------------------------------ persistence
    def _changed(self) -> None:
        self._save_timer.start()
        self.changed.emit()

    def save_now(self) -> None:
        self._save_timer.stop()
        atomic_write_json(self._path, [e.to_json() for e in self._entries])
