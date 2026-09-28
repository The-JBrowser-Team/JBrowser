"""AppContext: the dependency container that owns and wires every service.

Construction order matters: state → services → engine (profiles, registry, lifecycle).
UI components are built afterwards and only depend on this object.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

from jbrowser.core.commands import CommandRegistry
from jbrowser.core.motion import Motion
from jbrowser.core.settings import Settings
from jbrowser.core.urls import looks_like_url, strip_www, to_url
from jbrowser.core.workers import stop_worker
from jbrowser.engine.js import CLEAR_SITE_STORAGE_JS
from jbrowser.engine.lifecycle import LifecycleManager
from jbrowser.engine.profiles import ProfileManager
from jbrowser.engine.registry import EngineRegistry
from jbrowser.models.space import Space
from jbrowser.models.state import BrowserState
from jbrowser.models.tab import TabUpdatePipeline
from jbrowser.paths import AppPaths
from jbrowser.services.archive import ArchiveService
from jbrowser.services.bookmarks import BookmarkService
from jbrowser.services.cookies import CookieMonitor
from jbrowser.services.downloads import DownloadManager
from jbrowser.services.favicons import FaviconCache
from jbrowser.services.favourites import FavouritesService
from jbrowser.services.history import HistoryService
from jbrowser.services.network import DnsManager, ProxyManager
from jbrowser.services.privacy import PrivacyService
from jbrowser.services.search import SearchEngines, SuggestionClient
from jbrowser.services.session import SessionManager
from jbrowser.services.threats import ThreatService
from jbrowser.services.updater import UpdateService
from jbrowser.services.userscripts import UserScriptService
from jbrowser.services.vault import PasswordVault

log = logging.getLogger(__name__)


class UiHooks:
    """Callbacks the engine layer uses to ask the UI for something (set by MainWindow)."""

    def ask_credentials(self, title: str, message: str) -> tuple[str, str] | None:
        return None

    def unlock_vault(self) -> bool:
        return False

    def create_popup(self, profile: QWebEngineProfile, space: Space) -> QWebEnginePage | None:
        return None

    def toast(self, text: str, icon: str = "info") -> None:
        log.info("toast: %s", text)

    def notify(self, notification: Any) -> None:
        pass


class AppContext(QObject):
    def __init__(self, paths: AppPaths, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.paths = paths
        self.settings = settings
        self.hooks = UiHooks()
        self.stats: dict[str, int] = {"blocked": 0, "threats": 0}
        self.restart_requested = False       # set by factory reset / restart actions
        self.motion = Motion(bool(settings.get("appearance.animations")), self)
        self.pipeline = TabUpdatePipeline(self)
        self.state = BrowserState(self)
        self.commands = CommandRegistry(self)

        self.history = HistoryService(paths.history_db, self)
        self.bookmarks = BookmarkService(paths.bookmarks_file, self)
        self.archive = ArchiveService(paths.archive_file, self)
        self.favourites = FavouritesService(paths.favourites_file, self)
        self.favicons = FaviconCache(paths.favicons, self)
        self.vault = PasswordVault(paths.vault_file, self)
        self.downloads = DownloadManager(settings, paths.downloads_file, self)
        self.privacy = PrivacyService(settings, paths.blocklist_file, self)
        self.threats = ThreatService(settings, paths.threatlist_file, self)
        self.privacy.threats = self.threats
        self.dns = DnsManager(settings, self)
        self.proxy = ProxyManager(settings, self)
        self.search = SearchEngines(settings, self)
        self.suggest = SuggestionClient(self)
        self.userscripts = UserScriptService(paths.userscripts_file, self)
        self.cookies = CookieMonitor(self)
        self.updater = UpdateService(settings, self)

        self.profiles = ProfileManager(self, self)
        self.engine = EngineRegistry(self, self)
        self.lifecycle = LifecycleManager(self, self)
        self.session = SessionManager(self.state, settings, paths.session_file, self.engine.history_for, self)

        self.proxy.set_profile_provider(self.profiles.all)
        self.privacy.proxy_provider = self.proxy.requests_proxies
        self.threats.proxy_provider = self.proxy.requests_proxies
        self.downloads.tab_resolver = self.engine.tab_for_page
        self.downloads.referrer_resolver = self._referrer_for_page
        self.pipeline.flushed.connect(self.session.on_tabs_flushed)
        # The Archive follows browsing history: deleting history deletes the matching closed cards.
        self.state.tabArchived.connect(self.archive.add_closed)
        self.history.cleared.connect(self.archive.purge_range)
        self.history.hostDeleted.connect(self.archive.purge_host)
        self.history.urlsDeleted.connect(self.archive.purge_urls)
        self.state.spaceRemoved.connect(lambda sp: self.archive.purge_space(sp.id))
        self.state.activeSpaceChanged.connect(lambda sp, _prev: self.proxy.apply(sp.proxy))
        self.state.spaceUpdated.connect(self._on_space_updated)
        settings.changed.connect(self._on_setting)

    # -------------------------------------------------------------- wiring
    def _on_setting(self, key: str, value) -> None:
        if key == "appearance.animations":
            self.motion.set_enabled(bool(value))
        elif key in ("network.dns_mode", "network.dns_fallback"):
            self.dns.apply()
        elif key == "network.proxy":
            sp = self.state.active_space
            self.proxy.apply(sp.proxy if sp else None, force=True)

    def _on_space_updated(self, space: Space) -> None:
        if space.id == self.state.active_space_id:
            self.proxy.apply(space.proxy)

    def present_notification(self, notification) -> None:
        self.hooks.notify(notification)

    def _referrer_for_page(self, page) -> str:
        return page.url().toString() if page is not None else ""

    # ------------------------------------------------------------- helpers
    def resolve_input(self, text: str, remember: bool = True) -> QUrl:
        """Turn Lazy Toolbar input into a URL: keyword search, direct URL or web search."""
        text = text.strip()
        kw = self.search.parse_keyword(text)
        if kw:
            engine, query = kw
            if remember:
                self.search.remember(query)
            return QUrl(engine.build(query))
        if looks_like_url(text, self.privacy.dev_hosts()):
            return to_url(text)
        if remember:
            self.search.remember(text)
        return self.search.search_url(text)

    def save_all(self) -> None:
        for fn in (self.session.save_now, self.settings.save_now, self.bookmarks.save_now,
                   self.downloads.save_now, self.userscripts.save_now, self.archive.save_now,
                   self.favourites.save_now):
            try:
                fn()
            except Exception:
                log.exception("Save failed: %s", getattr(fn, "__qualname__", fn))

    def forget_site(self, host: str) -> dict:
        """Remove every trace of ``host`` (and its sub-domains): history, cookies, zoom,
        permissions and page storage for open cards. Returns counts for the UI."""
        host = strip_www(host.lower())
        removed = {"history": self.history.delete_host(host), "cookies": 0, "permissions": 0}
        for space in self.state.spaces:
            prof = self.profiles.get(space.id)
            if prof is None:
                continue
            victims = self.cookies.cookies_for_host(space.id, host)
            self.cookies.delete(space.id, victims)
            removed["cookies"] += len(victims)
            for perm in prof.listAllPermissions():
                ph = strip_www(perm.origin().host().lower())
                if ph == host or ph.endswith("." + host):
                    perm.reset()
                    removed["permissions"] += 1
        for tab in self.state.all_tabs():
            th = strip_www(QUrl(tab.url).host().lower())
            if th == host or th.endswith("." + host):
                ctrl = self.engine.controller(tab.id)
                if ctrl is not None and tab.loaded and not tab.sleeping:
                    ctrl.page.runJavaScript(CLEAR_SITE_STORAGE_JS, 0)
        zooms = {h: z for h, z in (self.settings.get("zoom.sites") or {}).items()
                 if not (strip_www(h) == host or strip_www(h).endswith("." + host))}
        self.settings.set("zoom.sites", zooms)
        self.favicons.forget(host)
        return removed

    def _clear_on_exit(self) -> None:
        items = set(self.settings.get("privacy.clear_on_exit") or [])
        if not items:
            return
        if "history" in items:
            self.history.clear()       # also empties the Archive (history.cleared)
        if "downloads" in items:
            self.downloads.clear_finished()
        for sid, prof in [(s.id, self.profiles.get(s.id)) for s in self.state.spaces]:
            if prof is None:
                continue
            if "cookies" in items:
                prof.cookieStore().deleteAllCookies()
            if "cache" in items:
                prof.clearHttpCache()

    def shutdown(self) -> None:
        # Background list downloads must never outlive their QThread objects (Qt would abort).
        # Ask both to stop first so their (short) waits overlap.
        workers = [w for w in (self.privacy._updater, self.threats._worker) if w is not None]
        for worker in workers:
            if worker.isRunning():
                worker.requestInterruption()
        deadline = time.monotonic() + 2.0            # one shared budget, never more than 2 s at exit
        for worker in workers:
            stop_worker(worker, max(0, int((deadline - time.monotonic()) * 1000)))
        try:
            self._clear_on_exit()
        except Exception:
            log.exception("Clear-on-exit failed")
        self.save_all()
        self.proxy.release_all()
        self.engine.dispose_all()
        self.history.close()
