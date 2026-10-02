"""TabController: owns one card's QWebEnginePage and translates engine events into
Tab-model updates (via the coalescing pipeline), info bars and lifecycle operations."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QByteArray, QDataStream, QIODevice, QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (QWebEngineCertificateError, QWebEnginePage, QWebEnginePermission,
                                   QWebEngineProfile)

from jbrowser.core.urls import is_local_host, strip_www
from jbrowser.engine import reader
from jbrowser.engine.js import BRIDGE_WORLD, CLEAR_SITE_STORAGE_JS
from jbrowser.engine.page import BrowserPage, PageBridge
from jbrowser.engine.signin import is_rejection_url
from jbrowser.models.infobar import InfoAction, InfoBarSpec
from jbrowser.models.space import Space
from jbrowser.models.tab import Tab
from jbrowser.services.permissions import describe
from jbrowser.services.privacy import PageInterceptor

if TYPE_CHECKING:
    from jbrowser.context import AppContext

log = logging.getLogger(__name__)

LS = QWebEnginePage.LifecycleState
ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]


class TabController(QObject):
    infobar = pyqtSignal(object)            # InfoBarSpec
    infobarClosed = pyqtSignal(str)         # key
    findResult = pyqtSignal(int, int)       # active match, total matches
    linkHovered = pyqtSignal(str)
    fullscreenRequested = pyqtSignal(object)
    closeRequested = pyqtSignal()
    printRequested = pyqtSignal()
    desktopMediaRequested = pyqtSignal(object)
    navigated = pyqtSignal()                # a new main-frame navigation started

    def __init__(self, ctx: "AppContext", tab: Tab, space: Space, profile: QWebEngineProfile,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.tab = tab
        self.space = space
        self.disposed = False
        self.page = BrowserPage(profile, self)
        self._interceptor = PageInterceptor(ctx.privacy, self._on_blocked, self, on_websocket=self._on_websocket)
        self.page.setUrlRequestInterceptor(self._interceptor)
        # Hibernation guards that don't need anything inside the page (see engine/js.py GUARD_JS).
        self._websocket = False          # the current page opened a WebSocket (chat, live updates)
        self._capturing = False          # the page was allowed the camera, microphone or screen
        self._channel = QWebChannel(self)
        self._bridge = PageBridge(self)
        self._channel.registerObject("jbBridge", self._bridge)
        self.page.setWebChannel(self._channel, BRIDGE_WORLD)
        self.page.setAudioMuted(tab.muted)
        self._host = ""
        self._autofilled = False
        self._last_recorded = ""
        self._blocked_url = ""          # set while the dangerous-site interstitial is showing
        self._fallback_host = ""        # http page being opened after its https version failed
        self._fallback_shown = ""       # host whose "not encrypted" warning is showing
        self._pending: list[object] = []   # keeps deferred engine requests alive
        self._spa_timer = QTimer(self)
        self._spa_timer.setSingleShot(True)
        self._spa_timer.setInterval(900)
        self._spa_timer.timeout.connect(self._record_visit)
        # Reading mode: is the page an article? Checked once it has settled (engine/reader.py).
        self._reader_timer = QTimer(self)
        self._reader_timer.setSingleShot(True)
        self._reader_timer.setInterval(700)
        self._reader_timer.timeout.connect(self._check_readable)
        self._reader_url = ""
        self._connect()
        if tab.url and not tab.sleeping:
            self.ensure_loaded()

    # ------------------------------------------------------------------ wiring
    def _connect(self) -> None:
        p = self.page
        p.urlChanged.connect(self._on_url)
        self.ctx.profiles.signin.watch(p)
        p.titleChanged.connect(self._on_title)
        p.iconChanged.connect(self._on_icon)
        p.loadStarted.connect(self._on_load_started)
        p.loadProgress.connect(lambda v: self.tab.update(progress=int(v)))
        p.loadFinished.connect(self._on_load_finished)
        p.recentlyAudibleChanged.connect(lambda a: self.tab.update(audible=bool(a)))
        p.audioMutedChanged.connect(lambda m: self.tab.update(muted=bool(m)))
        p.lifecycleStateChanged.connect(self._on_lifecycle)
        p.renderProcessTerminated.connect(self._on_render_terminated)
        p.linkHovered.connect(lambda url: self.linkHovered.emit(url))
        p.fullScreenRequested.connect(lambda req: self.fullscreenRequested.emit(req))
        p.windowCloseRequested.connect(lambda: self.closeRequested.emit())
        p.printRequested.connect(lambda: self.printRequested.emit())
        p.findTextFinished.connect(lambda r: self.findResult.emit(r.activeMatch(), r.numberOfMatches()))
        p.zoomFactorChanged.connect(lambda z: self.tab.update(zoom=round(float(z), 3)))
        p.permissionRequested.connect(self._on_permission)
        p.certificateError.connect(self._on_certificate_error)
        p.authenticationRequired.connect(self._on_auth)
        p.proxyAuthenticationRequired.connect(self._on_proxy_auth)
        p.desktopMediaRequested.connect(lambda req: self.desktopMediaRequested.emit(req))

    # -------------------------------------------------------------- navigation
    def ensure_loaded(self) -> None:
        if self.tab.loaded or self.disposed:
            return
        self.tab.loaded = True
        hist = self.tab.pending_history
        self.tab.pending_history = None
        if hist:
            stream = QDataStream(QByteArray(hist), QIODevice.OpenModeFlag.ReadOnly)
            stream >> self.page.history()
            QTimer.singleShot(400, self._verify_restore)
        elif self.tab.url:
            self.page.load(QUrl(self.tab.url))

    def _verify_restore(self) -> None:
        if not self.disposed and self.page.history().count() == 0 and self.page.url().isEmpty() and self.tab.url:
            self.page.load(QUrl(self.tab.url))

    def load(self, url: QUrl | str) -> None:
        q = url if isinstance(url, QUrl) else QUrl(url)
        self.tab.loaded = True
        if self.tab.sleeping:
            self.tab.update(sleeping=False)
            if self.page.lifecycleState() != LS.Active:
                self.page.setLifecycleState(LS.Active)
        self.tab.update(url=q.toString())
        self.page.load(q)

    def back(self) -> None:
        self.page.triggerAction(QWebEnginePage.WebAction.Back)

    def forward(self) -> None:
        self.page.triggerAction(QWebEnginePage.WebAction.Forward)

    def reload(self, bypass_cache: bool = False) -> None:
        if self.tab.crashed:
            self.tab.update(crashed=False)
            self.infobarClosed.emit("crashed")
        if not self.tab.loaded:
            self.ensure_loaded()
            return
        self.page.triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache if bypass_cache
                                else QWebEnginePage.WebAction.Reload)

    def stop(self) -> None:
        self.page.triggerAction(QWebEnginePage.WebAction.Stop)

    def find(self, text: str, backward: bool = False, case_sensitive: bool = False) -> None:
        flags = QWebEnginePage.FindFlag(0)
        if backward:
            flags |= QWebEnginePage.FindFlag.FindBackward
        if case_sensitive:
            flags |= QWebEnginePage.FindFlag.FindCaseSensitively
        self.page.findText(text, flags)

    def stop_find(self) -> None:
        self.page.findText("")

    def toggle_mute(self) -> None:
        self.page.setAudioMuted(not self.page.isAudioMuted())

    # ------------------------------------------------------------------- zoom
    def _site_zoom(self) -> float:
        host = QUrl(self.tab.url).host()
        try:
            return float((self.ctx.settings.get("zoom.sites") or {}).get(host, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def set_zoom(self, factor: float) -> None:
        factor = max(0.25, min(5.0, round(factor, 3)))
        self.page.setZoomFactor(factor)
        self.tab.update(zoom=factor)
        host = QUrl(self.tab.url).host()
        if host and not self.space.incognito:
            sites = dict(self.ctx.settings.get("zoom.sites") or {})
            if abs(factor - 1.0) < 0.001:
                sites.pop(host, None)
            else:
                sites[host] = factor
            self.ctx.settings.set("zoom.sites", sites)

    def zoom_step(self, direction: int) -> None:
        cur = self.page.zoomFactor()
        if direction > 0:
            nxt = next((z for z in ZOOM_STEPS if z > cur + 0.001), ZOOM_STEPS[-1])
        else:
            nxt = next((z for z in reversed(ZOOM_STEPS) if z < cur - 0.001), ZOOM_STEPS[0])
        self.set_zoom(nxt)

    # --------------------------------------------------------- engine events
    def _on_url(self, url: QUrl) -> None:
        if self._blocked_url:
            if url.scheme() in ("http", "https", "file"):
                self._blocked_url = ""
                self.infobarClosed.emit("threat")
            else:  # the interstitial (about:blank) is showing — keep displaying the blocked address
                self.tab.update(url=self._blocked_url, title="Dangerous site blocked", secure=False)
                return
        self._track_fallback(url)
        s = url.toString()
        self.tab.update(url=s, secure=url.scheme() == "https",
                        can_back=self.page.history().canGoBack(), can_forward=self.page.history().canGoForward())
        host = url.host()
        if host != self._host:
            self._host = host
            self._autofilled = False
            z = self._site_zoom()
            if abs(self.page.zoomFactor() - z) > 0.001:
                self.page.setZoomFactor(z)
            self.refresh_login_count()
        if not self.page.isLoading():
            self._spa_timer.start()
        if url.adjusted(QUrl.UrlFormattingOption.RemoveFragment).toString() != self._reader_url:
            # A different page (also in single-page sites, which change the address without loading).
            self._reader_url = ""
            if self.tab.readable or self.tab.reading:
                self.tab.update(readable=False, reading=False)
            if not self.page.isLoading():
                self._reader_timer.setInterval(1500)
                self._reader_timer.start()
        if is_rejection_url(url) and self.ctx.settings.get("advanced.identity") != "firefox":
            self._offer_signin_fix()

    def _offer_signin_fix(self) -> None:
        """Google still refused the sign-in ("This browser or app may not be secure"). Offer the fix that
        works when nothing else does (Firefox to every site, see engine/signin.py) and try again. It undoes
        itself once the sign-in has worked."""
        def fix():
            self.ctx.profiles.start_signin_fix()
            QTimer.singleShot(0, restart)

        def restart():
            if not self.disposed:
                self.page.setUrl(QUrl("https://accounts.google.com/"))

        self.infobar.emit(InfoBarSpec(
            "google-rejected",
            "Google couldn't sign you in with this browser. JBrowser can fix this: press the button and sign "
            "in again.",
            icon="warning", kind="warning",
            actions=[InfoAction("Fix and sign in again", fix, primary=True)]))

    def _on_title(self, title: str) -> None:
        if self._blocked_url:
            return
        self.tab.update(title=title)
        if not self.space.incognito and title:
            self.ctx.history.update_title(self.page.url().toString(), title)

    def _on_icon(self, icon) -> None:
        self.tab.update(icon=icon)
        if not icon.isNull() and self.tab.url:
            self.ctx.favicons.store(self.tab.url, icon, persist=not self.space.incognito)

    def _on_load_started(self) -> None:
        self.tab.loaded = True
        self._websocket = False
        self._capturing = False
        self.tab.update(loading=True, progress=5, crashed=False, blocked=0)
        self.navigated.emit()

    def _on_websocket(self) -> None:
        self._websocket = True

    def _on_load_finished(self, ok: bool) -> None:
        h = self.page.history()
        self.tab.update(loading=False, progress=100, can_back=h.canGoBack(), can_forward=h.canGoForward())
        if ok:
            self._record_visit()
            self._reader_timer.setInterval(700)
            self._reader_timer.start()
        elif not self.disposed:
            # page.url() holds the upgraded https address; requestedUrl() is still the original http one.
            self._https_fallback(self.page.url())

    # ----------------------------------------------------------- reading mode
    def url_interceptor(self) -> PageInterceptor:
        return self._interceptor

    def _check_readable(self) -> None:
        url = self.page.url()
        if self.disposed or self.page.isLoading() or url.scheme() not in ("http", "https") or self._blocked_url \
                or self.tab.sleeping or not reader.available():
            return
        key = url.adjusted(QUrl.UrlFormattingOption.RemoveFragment).toString()

        def done(result, key=key):
            if self.disposed or self.page.url().adjusted(QUrl.UrlFormattingOption.RemoveFragment).toString() != key:
                return
            self._reader_url = key
            self.tab.update(readable=result is True)
        self.page.runJavaScript(reader.readerable_js(), BRIDGE_WORLD, done)

    def extract_article(self, callback: Callable[[dict | None], None]) -> None:
        """Pull the article out of the page for reading mode. ``callback(article | None)``."""
        if self.disposed or self.tab.sleeping or not reader.available():
            callback(None)
            return
        self.page.runJavaScript(reader.extract_js(), BRIDGE_WORLD,
                                lambda result: None if self.disposed else callback(reader.parse_result(result)))

    def _track_fallback(self, url: QUrl) -> None:
        """Warn once the http version of a failed https upgrade commits; retract on leaving the site."""
        host = url.host()
        if self._fallback_host and url.scheme() == "http" and host == self._fallback_host:
            self._fallback_host = ""
            self._fallback_shown = host
            self.infobar.emit(InfoBarSpec(
                "https-fallback", f"{host} does not support a secure connection, so this page is not encrypted. "
                                  "Avoid entering passwords or payment details here.",
                icon="unlock", kind="warning", timeout_ms=20000, persist_navigation=True))
        elif self._fallback_shown and host != self._fallback_shown:
            self._fallback_shown = ""
            self.infobarClosed.emit("https-fallback")

    def _https_fallback(self, url: QUrl) -> bool:
        """The secure version of an upgraded address failed: open the original http page."""
        plain = self.ctx.privacy.upgrade_fallback(url)
        if plain is None:
            return False
        self._fallback_host = plain.host()   # the warning appears once the http page has loaded
        QTimer.singleShot(0, lambda u=plain: None if self.disposed else self.page.load(u))
        return True

    def _record_visit(self) -> None:
        if self.space.incognito or self.disposed:
            return
        url = self.page.url().toString()
        if not url or url == self._last_recorded or not url.startswith(("http://", "https://", "file:")):
            return
        self._last_recorded = url
        self.ctx.history.add_visit(url, self.page.title(), self.space.id)

    def _on_lifecycle(self, state: LS) -> None:
        if state == LS.Discarded:
            self.tab.update(sleeping=True, throttled=False, audible=False, loading=False)
        elif state == LS.Frozen:
            self.tab.update(throttled=True)
        else:
            self.tab.update(throttled=False, sleeping=False)

    def _on_render_terminated(self, status, code: int) -> None:
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus or self.disposed:
            return
        reason = {QWebEnginePage.RenderProcessTerminationStatus.AbnormalTerminationStatus: "stopped unexpectedly",
                  QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus: "crashed",
                  QWebEnginePage.RenderProcessTerminationStatus.KilledTerminationStatus: "was killed"}.get(status, "failed")
        self.tab.update(crashed=True, loading=False)
        self.infobar.emit(InfoBarSpec("crashed", f"This page {reason} (code {code}).", icon="error", kind="danger",
                                      actions=[InfoAction("Reload", lambda: self.reload(), primary=True)],
                                      persist_navigation=False))

    def _on_blocked(self, host: str) -> None:
        self.tab.update(blocked=self.tab.blocked + 1)
        self.ctx.stats["blocked"] = self.ctx.stats.get("blocked", 0) + 1

    # --------------------------------------------------------------- windows
    def create_window(self, window_type: QWebEnginePage.WebWindowType) -> QWebEnginePage | None:
        WT = QWebEnginePage.WebWindowType
        if window_type == WT.WebDialog:
            return self.ctx.hooks.create_popup(self.page.profile(), self.space)
        index = self.space.index_of(self.tab.id) + 1
        new_tab = self.ctx.state.add_tab(self.space.id, "", index=index,
                                         activate=window_type != WT.WebBrowserBackgroundTab,
                                         width=self.ctx.settings.get("canvas.default_width"))
        if new_tab is None:
            return None
        ctrl = self.ctx.engine.controller(new_tab.id)
        if ctrl is None:
            return None
        ctrl.tab.loaded = True
        return ctrl.page

    def show_threat(self, url: QUrl) -> None:
        """Replace a navigation to a known phishing / malware host with an interstitial."""
        import html as _html

        from jbrowser.engine.js import INTERSTITIAL_HTML

        host = url.host()
        self._blocked_url = url.toString()
        self.ctx.stats["threats"] = self.ctx.stats.get("threats", 0) + 1
        page_html = INTERSTITIAL_HTML.replace("__HOST__", _html.escape(host)).replace("__KIND__", "phishing or malware")
        self.page.setHtml(page_html, QUrl("about:blank"))
        self.tab.update(url=self._blocked_url, title="Dangerous site blocked", secure=False, loading=False)

        def go_back():
            self._blocked_url = ""
            if self.page.history().canGoBack():
                self.page.history().back()
            else:
                self.closeRequested.emit()

        def proceed(u=QUrl(url), h=host):
            self.ctx.threats.allow_for_session(h)
            self._blocked_url = ""
            self.load(u)

        self.infobar.emit(InfoBarSpec(
            "threat", f"{host} is on a list of phishing and malware sites. JBrowser blocked it to keep you safe.",
            icon="shield", kind="danger",
            actions=[InfoAction("Go back to safety", go_back, primary=True),
                     InfoAction("Continue anyway (unsafe)", proceed)],
            persist_navigation=True))

    def external_protocol(self, url: QUrl) -> None:
        scheme = url.scheme()
        self.infobar.emit(InfoBarSpec(
            f"external-{scheme}", f"Open this “{scheme}:” link with an external application?", icon="newwindow",
            actions=[InfoAction("Open", lambda u=QUrl(url): QDesktopServices.openUrl(u), primary=True)],
            timeout_ms=20000))

    # ------------------------------------------------------------ permissions
    def _on_permission(self, permission: QWebEnginePermission) -> None:
        # The signal argument is a temporary; keep an owned copy (it shares the request state).
        permission = QWebEnginePermission(permission)
        name, phrase, glyph = describe(permission.permissionType())
        origin = permission.origin()
        host = origin.host() or origin.toString()
        self._pending.append(permission)

        PT = QWebEnginePermission.PermissionType
        capture = permission.permissionType() in (PT.MediaAudioCapture, PT.MediaVideoCapture,
                                                  PT.MediaAudioVideoCapture, PT.DesktopVideoCapture,
                                                  PT.DesktopAudioVideoCapture)

        def decide(grant: bool, perm=permission):
            if grant:
                perm.grant()
                if capture:
                    self._capturing = True     # a call or screen share: never hibernate this card
            else:
                perm.deny()
            if perm in self._pending:
                self._pending.remove(perm)

        self.infobar.emit(InfoBarSpec(
            f"perm-{permission.permissionType().value}-{host}", f"{host} wants to {phrase}.", icon=glyph,
            actions=[InfoAction("Allow", lambda: decide(True), primary=True), InfoAction("Block", lambda: decide(False))],
            on_dismiss=lambda: decide(False)))

    def _on_certificate_error(self, error: QWebEngineCertificateError) -> None:
        host = error.url().host()
        if self.ctx.privacy.was_upgraded(error.url()):
            # JBrowser, not the site, chose https here: quietly go back to the http page.
            error.rejectCertificate()
            self._https_fallback(QUrl(error.url()))
            return
        if not error.isOverridable():
            error.rejectCertificate()
            return
        error.defer()
        error = QWebEngineCertificateError(error)  # owned copy; the signal argument is a temporary
        self._pending.append(error)

        def finish(accept: bool, err=error):
            try:
                err.acceptCertificate() if accept else err.rejectCertificate()
            except RuntimeError:
                pass
            if err in self._pending:
                self._pending.remove(err)

        self.infobar.emit(InfoBarSpec(
            f"cert-{host}", f"Your connection to {host} is not private: {error.description()}", icon="warning",
            kind="danger",
            actions=[InfoAction("Back to safety", lambda: finish(False), primary=True),
                     InfoAction("Proceed anyway (unsafe)", lambda: finish(True))],
            on_dismiss=lambda: finish(False)))

    def _on_auth(self, url: QUrl, auth) -> None:
        creds = self.ctx.hooks.ask_credentials(f"Sign in to {url.host()}",
                                               f"{url.host()} requires a username and password."
                                               + (f"\nRealm: {auth.realm()}" if auth.realm() else ""))
        if creds:
            auth.setUser(creds[0])
            auth.setPassword(creds[1])

    def _on_proxy_auth(self, url: QUrl, auth, proxy_host: str) -> None:
        creds = self.ctx.proxy.credentials_for(proxy_host, self.space.proxy) or \
            self.ctx.hooks.ask_credentials("Proxy authentication", f"The proxy {proxy_host} requires sign-in.")
        if creds:
            auth.setUser(creds[0])
            auth.setPassword(creds[1])

    # --------------------------------------------------------------- passwords
    def credentials(self) -> list:
        vault = self.ctx.vault
        if vault.mode == "master" and vault.is_locked:
            return []
        return vault.find_for_url(self.page.url(), self.space.id)

    def refresh_login_count(self) -> None:
        try:
            self.tab.update(saved_logins=len(self.credentials()))
        except Exception:  # vault errors must never break navigation
            log.exception("Vault lookup failed")

    def on_login_form(self, count: int) -> None:
        if count <= 0 or self.disposed:
            return
        creds = self.credentials()
        self.tab.update(saved_logins=len(creds))
        if creds and not self._autofilled and self.ctx.settings.get("passwords.autofill") and len(creds) == 1:
            self.fill(creds[0])

    def on_media_unsupported(self, kind: str) -> None:
        """A video or sound on the page is in a format Qt WebEngine can't play (H.264, AAC). The notice is
        off by default (Settings → Advanced), as it can be intrusive."""
        if self.disposed or not self.ctx.settings.get("advanced.media_notice"):
            return
        url = self.page.url().toString()
        self.infobar.emit(InfoBarSpec(
            "media-unsupported", f"This {kind} uses a format JBrowser can't play yet (such as H.264 or AAC). "
                                 "To watch it, open the page in another browser.",
            icon="info", kind="info", timeout_ms=30000,
            actions=[InfoAction("Copy link", lambda u=url: QGuiApplication.clipboard().setText(u), primary=True)]))

    def fill(self, cred) -> None:
        js = (f"window.__jbFill && window.__jbFill({json.dumps(cred.username)}, {json.dumps(cred.password)})")
        self.page.runJavaScript(js, BRIDGE_WORLD)
        self._autofilled = True
        self.ctx.vault.mark_used(cred.id)

    def on_credentials(self, username: str, password: str) -> None:
        url = self.page.url()
        host = strip_www(url.host())
        if password and url.scheme() == "http" and host and not is_local_host(host) \
                and self.ctx.settings.get("passwords.warn_insecure"):
            self.infobar.emit(InfoBarSpec(
                "insecure-password", f"{host} is not secure (HTTP). The password you just entered was sent "
                                     "without encryption and could be read by others on this network.",
                icon="warning", kind="warning", persist_navigation=True, timeout_ms=60000))
        if self.space.incognito or not password or not self.ctx.settings.get("passwords.offer_save"):
            return
        if not host:
            return
        vault = self.ctx.vault
        locked = vault.mode == "master" and vault.is_locked
        if not locked:
            if vault.is_never(host) or vault.has_exact(url, username, password, self.space.id):
                return
            existing = any(c.username == username for c in vault.find_for_url(url, self.space.id))
        else:
            existing = False
        who = username or "this account"
        text = f"Update the saved password for {who} on {host}?" if existing else f"Save password for {who} on {host}?"

        def save(u=QUrl(url)):
            if vault.mode == "master" and vault.is_locked and not self.ctx.hooks.unlock_vault():
                return
            vault.save_credential(u, username, password, self.space.id)
            self.refresh_login_count()
            self.ctx.hooks.toast("Password saved", "key")

        def never():
            if vault.mode == "master" and vault.is_locked and not self.ctx.hooks.unlock_vault():
                return
            vault.add_never(host)

        self.infobar.emit(InfoBarSpec(
            "save-password", text, icon="key",
            actions=[InfoAction("Update" if existing else "Save", save, primary=True),
                     InfoAction("Never for this site", never)],
            timeout_ms=90000, persist_navigation=True))

    # --------------------------------------------------------------- lifecycle
    def probe(self, callback: Callable[[dict | None, bool], None]) -> None:
        """Run the smart-protection guard probe. ``callback(data | None, was_frozen)``.

        ``None`` means the page did not answer in time and must be treated as protected.
        """
        page = self.page
        state = page.lifecycleState()
        if self.disposed or state == LS.Discarded or not self.tab.loaded:
            callback({}, False)
            return
        was_frozen = state == LS.Frozen
        if was_frozen:
            page.setLifecycleState(LS.Active)
        done = {"v": False}

        def finish(result):
            if done["v"] or self.disposed:
                return
            done["v"] = True
            if result == "__timeout__":
                callback(None, was_frozen)
                return
            data: dict = {}
            if isinstance(result, str) and result:
                try:
                    data = json.loads(result)
                except ValueError:
                    data = {}
            data["ws"] = self._websocket
            data["rtc"] = self._capturing
            callback(data, was_frozen)

        QTimer.singleShot(2000, lambda: finish("__timeout__"))
        page.runJavaScript("window.__jbGuardProbe ? window.__jbGuardProbe() : ''", BRIDGE_WORLD, finish)

    def throttle(self, freeze: bool) -> None:
        """Out of sight: stop rendering (and optionally freeze JS timers/tasks)."""
        if self.disposed or self.tab.sleeping or not self.tab.loaded:
            return
        page = self.page
        if page.isVisible():
            page.setVisible(False)
        if freeze and page.lifecycleState() == LS.Active and page.recommendedState() != LS.Active \
                and not page.recentlyAudible():
            page.setLifecycleState(LS.Frozen)
        self.tab.update(throttled=True)

    def unthrottle(self, render_visible: bool) -> None:
        if self.disposed:
            return
        page = self.page
        if page.lifecycleState() == LS.Frozen:
            page.setLifecycleState(LS.Active)
        if render_visible and not self.tab.sleeping and not page.isVisible():
            page.setVisible(True)
        if self.tab.throttled:
            self.tab.update(throttled=False)

    def refreeze(self) -> None:
        page = self.page
        if not page.isVisible() and page.lifecycleState() == LS.Active and page.recommendedState() != LS.Active:
            page.setLifecycleState(LS.Frozen)

    def discard(self) -> bool:
        """Hibernate: free the renderer. Only succeeds when Qt agrees the page is expendable."""
        page = self.page
        if self.disposed:
            return False
        if page.isVisible():
            page.setVisible(False)
        if page.lifecycleState() == LS.Active:
            if page.recommendedState() == LS.Active:
                return False
            page.setLifecycleState(LS.Frozen)
        if page.recommendedState() != LS.Discarded:
            return False
        page.setLifecycleState(LS.Discarded)
        self.tab.update(sleeping=True, throttled=False, audible=False, loading=False)
        return True

    def wake(self) -> None:
        if self.disposed:
            return
        if not self.tab.loaded:
            self.tab.update(sleeping=False)
            self.ensure_loaded()
            return
        if self.page.lifecycleState() != LS.Active:
            self.page.setLifecycleState(LS.Active)
        self.tab.update(sleeping=False, throttled=False)

    # ------------------------------------------------------------------ data
    def history_bytes(self) -> bytes | None:
        if self.disposed:
            return None
        if not self.tab.loaded:
            return self.tab.pending_history
        h = self.page.history()
        if h.count() == 0:
            return None
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.OpenModeFlag.WriteOnly)
        stream << h
        return bytes(ba)

    def clear_site_storage(self) -> None:
        self.page.runJavaScript(CLEAR_SITE_STORAGE_JS, 0)
        host = self.page.url().host()
        store = self.page.profile().cookieStore()
        cookies = self.ctx.cookies.cookies_for_host(self.space.id, host)
        for c in cookies:
            store.deleteCookie(c)

    def dispose(self) -> None:
        if self.disposed:
            return
        self.disposed = True
        self._spa_timer.stop()
        self._reader_timer.stop()
        for req in self._pending:
            try:
                if isinstance(req, QWebEngineCertificateError):
                    req.rejectCertificate()
                elif isinstance(req, QWebEnginePermission):
                    req.deny()
            except RuntimeError:
                pass
        self._pending.clear()
        self.page.deleteLater()
        self.deleteLater()
