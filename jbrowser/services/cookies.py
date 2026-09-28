"""Mirrors each space's cookie store so cookies can be browsed and deleted from the UI."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEngineProfile


def _key(c: QNetworkCookie) -> tuple[bytes, str, str]:
    return bytes(c.name()), c.domain().lower(), c.path()


class CookieMonitor(QObject):
    changed = pyqtSignal(str)  # space id

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cookies: dict[str, dict[tuple, QNetworkCookie]] = {}
        self._stores: dict[str, QWebEngineProfile] = {}
        self._dirty: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._flush)

    def attach(self, space_id: str, profile: QWebEngineProfile) -> None:
        self._cookies[space_id] = {}
        self._stores[space_id] = profile
        store = profile.cookieStore()
        store.cookieAdded.connect(lambda c, sid=space_id: self._add(sid, c))
        store.cookieRemoved.connect(lambda c, sid=space_id: self._remove(sid, c))
        store.loadAllCookies()

    def detach(self, space_id: str) -> None:
        self._cookies.pop(space_id, None)
        self._stores.pop(space_id, None)

    def _add(self, sid: str, c: QNetworkCookie) -> None:
        bucket = self._cookies.get(sid)
        if bucket is not None:
            bucket[_key(c)] = QNetworkCookie(c)
            self._mark(sid)

    def _remove(self, sid: str, c: QNetworkCookie) -> None:
        bucket = self._cookies.get(sid)
        if bucket is not None:
            bucket.pop(_key(c), None)
            self._mark(sid)

    def _mark(self, sid: str) -> None:
        self._dirty.add(sid)
        self._timer.start()

    def _flush(self) -> None:
        dirty, self._dirty = self._dirty, set()
        for sid in dirty:
            self.changed.emit(sid)

    def cookies(self, space_id: str) -> list[QNetworkCookie]:
        return list(self._cookies.get(space_id, {}).values())

    def cookies_for_host(self, space_id: str, host: str) -> list[QNetworkCookie]:
        host = (host or "").lower()
        out = []
        for c in self.cookies(space_id):
            d = c.domain().lower().lstrip(".")
            if host == d or host.endswith("." + d) or d.endswith("." + host):
                out.append(c)
        return out

    def delete(self, space_id: str, cookies: list[QNetworkCookie]) -> None:
        prof = self._stores.get(space_id)
        if not prof:
            return
        store = prof.cookieStore()
        for c in cookies:
            store.deleteCookie(c)

    def delete_all(self, space_id: str) -> None:
        prof = self._stores.get(space_id)
        if prof:
            prof.cookieStore().deleteAllCookies()

    def delete_session(self, space_id: str) -> None:
        prof = self._stores.get(space_id)
        if prof:
            prof.cookieStore().deleteSessionCookies()
