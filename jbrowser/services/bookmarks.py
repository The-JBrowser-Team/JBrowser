"""Bookmarks / favorites store."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_json, read_json


@dataclass
class Bookmark:
    title: str
    url: str
    folder: str = ""
    on_bar: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: float = field(default_factory=time.time)


class BookmarkService(QObject):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        raw = read_json(path, [])
        self._items: list[Bookmark] = []
        for d in raw if isinstance(raw, list) else []:
            try:
                self._items.append(Bookmark(**{k: v for k, v in d.items() if k in Bookmark.__dataclass_fields__}))
            except TypeError:
                continue
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.save_now)

    def save_now(self) -> None:
        self._timer.stop()
        atomic_write_json(self._path, [asdict(b) for b in self._items])

    def _changed(self) -> None:
        self._timer.start()
        self.changed.emit()

    def all(self) -> list[Bookmark]:
        return list(self._items)

    def bar_items(self) -> list[Bookmark]:
        return [b for b in self._items if b.on_bar]

    def folders(self) -> list[str]:
        return sorted({b.folder for b in self._items if b.folder})

    def find_url(self, url: str) -> Bookmark | None:
        norm = url.rstrip("/")
        for b in self._items:
            if b.url.rstrip("/") == norm:
                return b
        return None

    def get(self, bid: str) -> Bookmark | None:
        return next((b for b in self._items if b.id == bid), None)

    def add(self, title: str, url: str, folder: str = "", on_bar: bool = True) -> Bookmark:
        existing = self.find_url(url)
        if existing:
            return existing
        b = Bookmark(title=title or url, url=url, folder=folder, on_bar=on_bar)
        self._items.append(b)
        self._changed()
        return b

    def update(self, bid: str, **fields) -> None:
        b = self.get(bid)
        if not b:
            return
        for k, v in fields.items():
            if hasattr(b, k):
                setattr(b, k, v)
        self._changed()

    def remove(self, bid: str) -> None:
        self._items = [b for b in self._items if b.id != bid]
        self._changed()

    def move(self, bid: str, new_index: int) -> None:
        b = self.get(bid)
        if not b:
            return
        self._items.remove(b)
        self._items.insert(max(0, min(new_index, len(self._items))), b)
        self._changed()

    def toggle(self, title: str, url: str) -> bool:
        """Bookmark ``url`` or remove it. Returns True if it is now bookmarked."""
        b = self.find_url(url)
        if b:
            self.remove(b.id)
            return False
        self.add(title, url)
        return True
