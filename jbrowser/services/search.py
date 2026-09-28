"""Search engines, keyword shortcuts and live (Google) search suggestions."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import quote_plus

from PyQt6.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from jbrowser.core.settings import Settings

log = logging.getLogger(__name__)

ENGINES = {
    "google": ("Google", "https://www.google.com/search?q={query}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={query}"),
    "bing": ("Bing", "https://www.bing.com/search?q={query}"),
    "brave": ("Brave Search", "https://search.brave.com/search?q={query}"),
    "startpage": ("Startpage", "https://www.startpage.com/do/search?q={query}"),
    "ecosia": ("Ecosia", "https://www.ecosia.org/search?q={query}"),
    "kagi": ("Kagi", "https://kagi.com/search?q={query}"),
}


@dataclass(slots=True)
class KeywordEngine:
    keyword: str
    name: str
    url: str

    def build(self, query: str) -> str:
        return self.url.replace("{query}", quote_plus(query)).replace("%s", quote_plus(query))


class SearchEngines(QObject):
    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings

    @property
    def default_id(self) -> str:
        eid = self.settings.get("search.engine")
        return eid if eid in ENGINES else "google"

    @property
    def default_name(self) -> str:
        return ENGINES[self.default_id][0]

    def search_url(self, query: str) -> QUrl:
        return QUrl(ENGINES[self.default_id][1].replace("{query}", quote_plus(query)))

    def keywords(self) -> list[KeywordEngine]:
        out = []
        for d in self.settings.get("search.keywords") or []:
            if d.get("keyword") and d.get("url"):
                out.append(KeywordEngine(d["keyword"].strip().lower(), d.get("name") or d["keyword"], d["url"]))
        return out

    def parse_keyword(self, text: str) -> tuple[KeywordEngine, str] | None:
        """``"yt lofi beats"`` -> (YouTube engine, "lofi beats")."""
        parts = text.strip().split(None, 1)
        if len(parts) != 2:
            return None
        kw = parts[0].lower()
        for eng in self.keywords():
            if eng.keyword == kw:
                return eng, parts[1]
        return None

    def remember(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        recent = [q for q in self.settings.get("search.recent") or [] if q.lower() != query.lower()]
        recent.insert(0, query)
        self.settings.set("search.recent", recent[:25])

    def recent(self) -> list[str]:
        return list(self.settings.get("search.recent") or [])


class SuggestionClient(QObject):
    """Debounced, cancellable Google Suggest client (JSON "firefox" flavour)."""

    suggestions = pyqtSignal(str, list)  # query, [suggestion strings]

    ENDPOINT = "https://suggestqueries.google.com/complete/search"
    DEBOUNCE_MS = 110

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._pending = ""
        self._cache: dict[str, list[str]] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self._fire)

    def request(self, query: str) -> None:
        query = query.strip()
        if not query:
            self.cancel()
            return
        if query in self._cache:
            self.suggestions.emit(query, self._cache[query])
            return
        self._pending = query
        self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()
        if self._reply is not None:
            self._reply.abort()
            self._reply = None

    def _fire(self) -> None:
        if self._reply is not None:
            self._reply.abort()
        query = self._pending
        url = QUrl(self.ENDPOINT)
        q = QUrlQuery()
        q.addQueryItem("client", "firefox")
        q.addQueryItem("q", query)
        url.setQuery(q)
        req = QNetworkRequest(url)
        req.setTransferTimeout(3500)
        req.setRawHeader(b"DNT", b"1")
        req.setRawHeader(b"Sec-GPC", b"1")
        reply = self._nam.get(req)
        self._reply = reply
        reply.finished.connect(lambda r=reply, qq=query: self._done(r, qq))

    def _done(self, reply: QNetworkReply, query: str) -> None:
        if reply is self._reply:
            self._reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            raw = bytes(reply.readAll())
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            data = json.loads(text)
            items = [s for s in data[1] if isinstance(s, str)][:8] if isinstance(data, list) and len(data) > 1 else []
            if len(self._cache) > 300:
                self._cache.clear()
            self._cache[query] = items
            self.suggestions.emit(query, items)
        except (ValueError, IndexError, TypeError) as exc:
            log.debug("Bad suggestion payload: %s", exc)
        finally:
            reply.deleteLater()
