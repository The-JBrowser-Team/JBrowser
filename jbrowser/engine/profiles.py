"""One isolated QWebEngineProfile per space.

Persistent spaces get their own storage + cache directories (cookies, localStorage,
IndexedDB, service workers, HTTP cache, permissions). Incognito spaces use off-the-record
profiles that keep everything in memory and leave nothing on disk once closed.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QStandardPaths, QTimer
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript, QWebEngineSettings

from jbrowser.engine import identity
from jbrowser.engine.js import AUTOFILL_JS, BRIDGE_WORLD, GUARD_JS, privacy_js, qwebchannel_js
from jbrowser.engine.signin import SigninIdentity
from jbrowser.models.space import Space
from jbrowser.services.privacy import CHALLENGE_SITES, ProfileInterceptor

if TYPE_CHECKING:
    from jbrowser.context import AppContext

log = logging.getLogger(__name__)

WA = QWebEngineSettings.WebAttribute


def accept_language() -> str:
    """Chrome-style Accept-Language from the Windows display languages, e.g.
    "en-AU,en;q=0.9". Qt sends none by default, and a browser without one looks like a bot."""
    from PyQt6.QtCore import QLocale
    langs: list[str] = []
    for tag in QLocale.system().uiLanguages() or ["en-US"]:
        parts = tag.replace("_", "-").split("-")
        lang = parts[0].lower()
        # Windows adds script subtags ("en-Latn-AU"); browsers send just language-REGION ("en-AU").
        region = next((p.upper() for p in parts[1:] if len(p) == 2 or (len(p) == 3 and p.isdigit())), "")
        for t in (f"{lang}-{region}" if region else lang, lang):   # each language's base follows it
            if lang and t not in langs:
                langs.append(t)
    langs = langs[:6]
    return ",".join(t if i == 0 else f"{t};q={max(0.1, 1 - i / 10):.1f}" for i, t in enumerate(langs))


class ProfileManager(QObject):
    def __init__(self, ctx: "AppContext", parent: QObject | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._profiles: dict[str, QWebEngineProfile] = {}
        self._interceptors: dict[str, ProfileInterceptor] = {}
        self._incognito: set[str] = set()
        self._fp_seed = secrets.randbits(31)   # fingerprint noise key, new every session
        self.signin = SigninIdentity(self._apply_identity, self)   # Firefox while signing in to Google
        self._wipe_pending_profiles()
        self._clear_on_start()
        self._remove_stray_default_dirs()
        ctx.settings.changed.connect(self._on_setting)
        ctx.privacy.blocklistUpdated.connect(lambda *_a: self.reinstall_scripts())   # new element-hiding rules
        ctx.userscripts.changed.connect(self.sync_user_scripts)
        ctx.motion.changed.connect(lambda _e: self._apply_settings_all())

    # ------------------------------------------------------------ lifecycle
    def _wipe_pending_profiles(self) -> None:
        pending = self.ctx.settings.get("profiles.pending_wipe") or []
        for sid in pending:
            self.ctx.paths.wipe_profile(sid)
        if pending:
            self.ctx.settings.set("profiles.pending_wipe", [])

    def _clear_on_start(self) -> None:
        """Belt and braces for "clear when JBrowser closes": cookie and cache deletions issued
        during shutdown are asynchronous, so the on-disk copies are removed again here,
        before any profile opens them."""
        items = set(self.ctx.settings.get("privacy.clear_on_exit") or [])
        if items & {"cookies", "cache"}:
            self.ctx.paths.clear_profile_cookies_and_cache(cookies="cookies" in items, cache="cache" in items)

    @staticmethod
    def _default_dirs(storage_name: str) -> list[str]:
        """Folders Qt creates for a named profile before its paths can be redirected."""
        roots = [QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation),
                 QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)]
        return [os.path.join(r, "QtWebEngine", storage_name) for r in roots if r]

    @staticmethod
    def _rmdir_empty(path: str) -> None:
        """Remove ``path`` and then its parents while they are empty (never touches files)."""
        for _ in range(4):
            try:
                os.rmdir(path)
            except OSError:
                return
            path = os.path.dirname(path)

    def _remove_stray_default_dirs(self) -> None:
        for root in (QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation),
                     QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)):
            base = os.path.join(root, "QtWebEngine") if root else ""
            if not base or not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                if name.startswith("space-"):
                    self._rmdir_empty(os.path.join(base, name))

    def profile_for(self, space: Space) -> QWebEngineProfile:
        prof = self._profiles.get(space.id)
        if prof is None:
            prof = self._create(space)
            self._profiles[space.id] = prof
        return prof

    def get(self, space_id: str) -> QWebEngineProfile | None:
        return self._profiles.get(space_id)

    def all(self) -> list[QWebEngineProfile]:
        return list(self._profiles.values())

    def space_id_of(self, profile: QWebEngineProfile) -> str:
        for sid, p in self._profiles.items():
            if p is profile:
                return sid
        return ""

    def _create(self, space: Space) -> QWebEngineProfile:
        paths = self.ctx.paths
        if space.incognito:
            prof = QWebEngineProfile(self)          # off-the-record: memory only
            prof.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.StoreInMemory)
            self._incognito.add(space.id)
        else:
            prof = QWebEngineProfile(f"space-{space.id}", self)
            storage = paths.profile_storage(space.id)
            cache = paths.profile_cache_dir(space.id)
            storage.mkdir(parents=True, exist_ok=True)
            cache.mkdir(parents=True, exist_ok=True)
            prof.setPersistentStoragePath(str(storage))
            prof.setCachePath(str(cache))
            prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            prof.setHttpCacheMaximumSize(512 * 1024 * 1024)
            prof.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            prof.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk)
            for stray in self._default_dirs(prof.storageName()):
                self._rmdir_empty(stray)
        self._apply_identity(prof)                  # the current Chrome, in headers and JavaScript
        if not prof.httpAcceptLanguage():
            prof.setHttpAcceptLanguage(accept_language())
        interceptor = ProfileInterceptor(self.ctx.privacy, prof)
        self._interceptors[space.id] = interceptor
        prof.setUrlRequestInterceptor(interceptor)
        privacy = self.ctx.privacy
        prof.cookieStore().setCookieFilter(lambda req, p=privacy: p.allow_cookie(req))
        prof.downloadRequested.connect(
            lambda req, sid=space.id, inc=space.incognito: self.ctx.downloads.handle(req, sid, inc))
        prof.setNotificationPresenter(self.ctx.present_notification)
        self._install_base_scripts(prof)
        self._apply_settings(prof)
        self.ctx.userscripts.sync_profile(prof, space.id)
        self.ctx.cookies.attach(space.id, prof)
        log.info("Created %s profile for space %s", "off-the-record" if space.incognito else "persistent", space.name)
        return prof

    def release(self, space: Space) -> None:
        """Destroy a space's profile once its pages are gone; wipe its disk data if persistent."""
        prof = self._profiles.pop(space.id, None)
        self._interceptors.pop(space.id, None)
        self.ctx.cookies.detach(space.id)
        if prof is None:
            return
        self.signin.forget_profile(prof)
        if not space.incognito:
            pending = self.ctx.settings.get("profiles.pending_wipe") or []
            if space.id not in pending:
                self.ctx.settings.set("profiles.pending_wipe", pending + [space.id])

        def finish():
            prof.deleteLater()
        QTimer.singleShot(0, finish)

    def dispose_all(self) -> None:
        for prof in self._profiles.values():
            prof.deleteLater()
        self._profiles.clear()
        self._interceptors.clear()

    # --------------------------------------------------------------- scripts
    def _install_base_scripts(self, prof: QWebEngineProfile) -> None:
        coll = prof.scripts()
        for existing in coll.toList():
            if existing.name().startswith("jb:"):
                coll.remove(existing)
        s = self.ctx.settings

        def add(name: str, source: str, point, world: int, subframes: bool):
            if not source:
                return
            sc = QWebEngineScript()
            sc.setName(name)
            sc.setSourceCode(source)
            sc.setInjectionPoint(point)
            sc.setWorldId(world)
            sc.setRunsOnSubFrames(subframes)
            coll.insert(sc)

        IP = QWebEngineScript.InjectionPoint
        main = QWebEngineScript.ScriptWorldId.MainWorld
        # The only script in the page's own world. Everything else runs in JBrowser's isolated world.
        exempt = list(CHALLENGE_SITES) + list(s.get("privacy.allowlist") or [])
        add("jb:privacy", privacy_js(self._fp_seed, exempt, bool(s.get("privacy.gpc")), bool(s.get("privacy.dnt")),
                                     bool(s.get("privacy.fingerprint_protection"))),
            IP.DocumentCreation, main, True)
        add("jb:guard", GUARD_JS, IP.DocumentCreation, BRIDGE_WORLD, False)
        add("jb:cosmetic", self.ctx.privacy.cosmetic_script(), IP.DocumentCreation, BRIDGE_WORLD, False)
        add("jb:qwebchannel", qwebchannel_js(), IP.DocumentCreation, BRIDGE_WORLD, False)
        add("jb:autofill", AUTOFILL_JS, IP.DocumentReady, BRIDGE_WORLD, False)

    def sync_user_scripts(self) -> None:
        for sid, prof in self._profiles.items():
            self.ctx.userscripts.sync_profile(prof, sid)

    # -------------------------------------------------------------- settings
    def _apply_identity(self, prof: QWebEngineProfile) -> None:
        """The version JBrowser presents (Settings → Advanced): the newest Chrome, or the engine's own."""
        identity.apply(prof, identity.version_for(self.ctx.settings.get("advanced.identity")))

    def _apply_settings(self, prof: QWebEngineProfile) -> None:
        s = self.ctx.settings
        ws = prof.settings()
        ws.setAttribute(WA.FullScreenSupportEnabled, True)
        ws.setAttribute(WA.ScrollAnimatorEnabled, self.ctx.motion.enabled)
        ws.setAttribute(WA.DnsPrefetchEnabled, False)
        ws.setAttribute(WA.HyperlinkAuditingEnabled, False)
        ws.setAttribute(WA.PluginsEnabled, True)
        ws.setAttribute(WA.PdfViewerEnabled, True)
        ws.setAttribute(WA.ScreenCaptureEnabled, True)
        ws.setAttribute(WA.LocalStorageEnabled, True)
        ws.setAttribute(WA.ErrorPageEnabled, True)
        ws.setAttribute(WA.FocusOnNavigationEnabled, False)
        ws.setAttribute(WA.NavigateOnDropEnabled, True)
        ws.setAttribute(WA.JavascriptCanOpenWindows, not s.get("privacy.popup_blocking"))
        ws.setAttribute(WA.WebRTCPublicInterfacesOnly, bool(s.get("privacy.webrtc_public_only")))
        ws.setAttribute(WA.PlaybackRequiresUserGesture, bool(s.get("privacy.block_autoplay")))
        ws.setAttribute(WA.ForceDarkMode, bool(s.get("appearance.force_dark_web")))
        if hasattr(WA, "BackForwardCacheEnabled"):
            ws.setAttribute(WA.BackForwardCacheEnabled, True)
        # Chrome's defaults for local files and mixed content. (Local pages keep loading their own images
        # and style sheets; ProfileInterceptor stops them reading other local files, as Chrome does.)
        ws.setAttribute(WA.LocalContentCanAccessRemoteUrls, False)
        ws.setAttribute(WA.AllowRunningInsecureContent, False)
        ws.setAttribute(WA.AllowGeolocationOnInsecureOrigins, False)

    def _apply_settings_all(self) -> None:
        for prof in self._profiles.values():
            self._apply_settings(prof)

    def reinstall_scripts(self) -> None:
        for prof in self._profiles.values():
            self._install_base_scripts(prof)

    def _on_setting(self, key: str, _value) -> None:
        if key in ("privacy.gpc", "privacy.dnt", "privacy.fingerprint_protection", "privacy.allowlist",
                   "privacy.block_trackers"):
            self.reinstall_scripts()
        elif key.startswith(("privacy.", "appearance.force_dark_web")):
            self._apply_settings_all()
        elif key == "advanced.identity":
            for prof in self._profiles.values():
                if not self.signin.is_firefox(prof):   # a sign-in in progress keeps Firefox until it ends
                    self._apply_identity(prof)

    # --------------------------------------------------------------- data
    def clear_cache(self, space_id: str | None = None) -> None:
        for sid, prof in self._profiles.items():
            if space_id is None or sid == space_id:
                prof.clearHttpCache()

    def clear_cookies(self, space_id: str | None = None) -> None:
        for sid, prof in self._profiles.items():
            if space_id is None or sid == space_id:
                prof.cookieStore().deleteAllCookies()

    def clear_visited_links(self, space_id: str | None = None) -> None:
        for sid, prof in self._profiles.items():
            if space_id is None or sid == space_id:
                prof.clearAllVisitedLinks()
