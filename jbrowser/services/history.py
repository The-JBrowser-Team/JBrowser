"""SQLite-backed browsing history with per-space tagging and frecency ranking."""
from __future__ import annotations

import logging
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    space_id TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts);
CREATE INDEX IF NOT EXISTS idx_visits_url ON visits(url);
CREATE INDEX IF NOT EXISTS idx_visits_space ON visits(space_id);
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    visits INTEGER NOT NULL DEFAULT 0,
    last_visit REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pages_last ON pages(last_visit);
"""


@dataclass(slots=True)
class HistoryEntry:
    id: int
    url: str
    title: str
    space_id: str
    ts: float


@dataclass(slots=True)
class PageStat:
    url: str
    title: str
    visits: int
    last_visit: float

    def frecency(self, now: float | None = None) -> float:
        now = now or time.time()
        age_days = max(0.0, (now - self.last_visit) / 86400.0)
        recency = 1.0 / (1.0 + age_days / 3.0)
        return math.log2(1 + self.visits) * 10 * (0.35 + recency)


class HistoryService(QObject):
    changed = pyqtSignal()
    cleared = pyqtSignal(object, object, object)   # start, end, space_id (None = unbounded / all)
    hostDeleted = pyqtSignal(str)
    urlsDeleted = pyqtSignal(list)

    DUPLICATE_WINDOW = 15.0  # seconds: reloads / redirects inside this window aren't new visits

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        try:
            self._db.commit()
            self._db.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------ writes
    def add_visit(self, url: str, title: str, space_id: str) -> None:
        if not url or url.startswith(("about:", "data:", "view-source:", "devtools:", "chrome:", "blob:")):
            return
        now = time.time()
        cur = self._db.execute(
            "SELECT id, ts FROM visits WHERE url=? AND space_id=? ORDER BY ts DESC LIMIT 1", (url, space_id))
        row = cur.fetchone()
        if row and now - row[1] < self.DUPLICATE_WINDOW:
            self._db.execute("UPDATE visits SET ts=?, title=CASE WHEN ?<>'' THEN ? ELSE title END WHERE id=?",
                             (now, title, title, row[0]))
        else:
            self._db.execute("INSERT INTO visits(url, title, space_id, ts) VALUES (?,?,?,?)",
                             (url, title or "", space_id, now))
            self._db.execute(
                "INSERT INTO pages(url, title, visits, last_visit) VALUES (?,?,1,?) "
                "ON CONFLICT(url) DO UPDATE SET visits=visits+1, last_visit=excluded.last_visit, "
                "title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE pages.title END",
                (url, title or "", now))
        self._db.commit()
        self.changed.emit()

    def update_title(self, url: str, title: str) -> None:
        if not url or not title:
            return
        self._db.execute("UPDATE pages SET title=? WHERE url=?", (title, url))
        self._db.execute(
            "UPDATE visits SET title=? WHERE id=(SELECT id FROM visits WHERE url=? ORDER BY ts DESC LIMIT 1)",
            (title, url))
        self._db.commit()

    def delete_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        q = ",".join("?" * len(ids))
        urls = [r[0] for r in self._db.execute(f"SELECT DISTINCT url FROM visits WHERE id IN ({q})", ids)]
        self._db.execute(f"DELETE FROM visits WHERE id IN ({q})", ids)
        self._prune_pages(urls)
        self._db.commit()
        self.changed.emit()
        gone = [u for u in urls if not self._db.execute("SELECT 1 FROM visits WHERE url=? LIMIT 1", (u,)).fetchone()]
        if gone:
            self.urlsDeleted.emit(gone)

    def delete_host(self, host: str) -> int:
        """Delete every visit to ``host`` or its sub-domains. Returns the number of visits removed."""
        from urllib.parse import urlsplit

        host = host.lower().removeprefix("www.")
        ids, urls = [], set()
        for vid, url in self._db.execute("SELECT id, url FROM visits WHERE url LIKE ?", (f"%{host}%",)):
            h = (urlsplit(url).hostname or "").lower().removeprefix("www.")
            if h == host or h.endswith("." + host):
                ids.append(vid)
                urls.add(url)
        if ids:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                self._db.execute(f"DELETE FROM visits WHERE id IN ({','.join('?' * len(chunk))})", chunk)
            for url in urls:
                self._db.execute("DELETE FROM pages WHERE url=?", (url,))
            self._db.commit()
            self.changed.emit()
        self.hostDeleted.emit(host)
        return len(ids)

    def delete_url(self, url: str) -> None:
        self._db.execute("DELETE FROM visits WHERE url=?", (url,))
        self._db.execute("DELETE FROM pages WHERE url=?", (url,))
        self._db.commit()
        self.changed.emit()
        self.urlsDeleted.emit([url])

    def clear(self, start: float | None = None, end: float | None = None, space_id: str | None = None) -> int:
        where, args = self._where(None, space_id, start, end)
        urls = [r[0] for r in self._db.execute(f"SELECT DISTINCT url FROM visits {where}", args)]
        cur = self._db.execute(f"DELETE FROM visits {where}", args)
        if start is None and end is None and space_id is None:
            self._db.execute("DELETE FROM pages")
        else:
            self._prune_pages(urls)
        self._db.commit()
        try:
            self._db.execute("VACUUM")
        except sqlite3.Error:
            pass
        self.changed.emit()
        self.cleared.emit(start, end, space_id)
        return cur.rowcount

    def _prune_pages(self, urls: list[str]) -> None:
        for url in urls:
            row = self._db.execute("SELECT COUNT(*), MAX(ts) FROM visits WHERE url=?", (url,)).fetchone()
            if not row or not row[0]:
                self._db.execute("DELETE FROM pages WHERE url=?", (url,))
            else:
                self._db.execute("UPDATE pages SET visits=?, last_visit=? WHERE url=?", (row[0], row[1], url))

    # ------------------------------------------------------------------- reads
    @staticmethod
    def _where(text: str | None, space_id: str | None, start: float | None, end: float | None):
        clauses, args = [], []
        if text:
            for word in text.split():
                clauses.append("(url LIKE ? OR title LIKE ?)")
                args += [f"%{word}%", f"%{word}%"]
        if space_id:
            clauses.append("space_id=?")
            args.append(space_id)
        if start is not None:
            clauses.append("ts>=?")
            args.append(start)
        if end is not None:
            clauses.append("ts<?")
            args.append(end)
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", args

    def search(self, text: str = "", space_id: str | None = None, start: float | None = None,
               end: float | None = None, limit: int = 1000) -> list[HistoryEntry]:
        where, args = self._where(text, space_id, start, end)
        rows = self._db.execute(
            f"SELECT id, url, title, space_id, ts FROM visits {where} ORDER BY ts DESC LIMIT ?", args + [limit])
        return [HistoryEntry(*r) for r in rows]

    def pages_matching(self, text: str, limit: int = 60) -> list[PageStat]:
        if text:
            clauses, args = [], []
            for word in text.split()[:5]:
                clauses.append("(url LIKE ? OR title LIKE ?)")
                args += [f"%{word}%", f"%{word}%"]
            rows = self._db.execute(
                f"SELECT url, title, visits, last_visit FROM pages WHERE {' AND '.join(clauses)} "
                f"ORDER BY visits DESC, last_visit DESC LIMIT ?", args + [limit])
        else:
            rows = self._db.execute(
                "SELECT url, title, visits, last_visit FROM pages ORDER BY last_visit DESC LIMIT ?", (limit,))
        return [PageStat(*r) for r in rows]

    def top_sites(self, limit: int = 8) -> list[PageStat]:
        rows = self._db.execute(
            "SELECT url, title, visits, last_visit FROM pages ORDER BY visits DESC, last_visit DESC LIMIT 200")
        pages = [PageStat(*r) for r in rows]
        now = time.time()
        pages.sort(key=lambda p: p.frecency(now), reverse=True)
        return pages[:limit]

    def count(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM visits").fetchone()[0])
