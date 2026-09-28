"""Sidebar favourites: sites pinned above the spaces (Arc-style), available in every space.

A favourite is a saved address with a title. Clicking it focuses the card that was opened
from it in the current space, or opens a new one, so each favourite behaves like an app you
keep coming back to.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_json, read_json
from jbrowser.core.urls import strip_www

MAX_FAVOURITES = 16


@dataclass
class Favourite:
    url: str
    title: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def host(self) -> str:
        return strip_www(QUrl(self.url).host().lower())

    def label(self) -> str:
        return self.title or self.host or self.url


class FavouritesService(QObject):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        self._items: list[Favourite] = []
        raw = read_json(path, [])
        if isinstance(raw, list):
            for d in raw:
                if isinstance(d, dict) and d.get("url"):
                    self._items.append(Favourite(url=d["url"], title=d.get("title", ""), id=d.get("id") or
                                                 uuid.uuid4().hex[:12]))
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self.save_now)

    def all(self) -> list[Favourite]:
        return list(self._items)

    def get(self, fid: str) -> Favourite | None:
        return next((f for f in self._items if f.id == fid), None)

    def find_url(self, url: str) -> Favourite | None:
        return next((f for f in self._items if f.url == url), None)

    def is_full(self) -> bool:
        return len(self._items) >= MAX_FAVOURITES

    def add(self, url: str, title: str = "") -> Favourite | None:
        existing = self.find_url(url)
        if existing is not None:
            return existing
        if self.is_full():
            return None
        fav = Favourite(url=url, title=title)
        self._items.append(fav)
        self._changed()
        return fav

    def remove(self, fid: str) -> None:
        before = len(self._items)
        self._items = [f for f in self._items if f.id != fid]
        if len(self._items) != before:
            self._changed()

    def update(self, fid: str, **fields) -> None:
        fav = self.get(fid)
        if fav is None:
            return
        for k, v in fields.items():
            if k in ("url", "title"):
                setattr(fav, k, v)
        self._changed()

    def move(self, fid: str, index: int) -> None:
        fav = self.get(fid)
        if fav is None:
            return
        self._items.remove(fav)
        self._items.insert(max(0, min(index, len(self._items))), fav)
        self._changed()

    def _changed(self) -> None:
        self._save_timer.start()
        self.changed.emit()

    def save_now(self) -> None:
        self._save_timer.stop()
        atomic_write_json(self._path, [asdict(f) for f in self._items])
