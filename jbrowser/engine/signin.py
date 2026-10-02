"""Signing in to Google: the space presents Firefox while one of its pages is on the sign-in server.

Google refuses to sign in browsers it takes for web views embedded in other apps ("Couldn't sign you
in. This browser or app may not be secure"). Sending a Firefox user agent to accounts.google.com only
(services/privacy.py, since 1.5.1) is enough on most PCs. Where Google looks closer, it also sees the
rest of the page still saying Chromium (``navigator.userAgent``, ``navigator.userAgentData`` and the
``Sec-CH-UA`` headers) and refuses anyway; switching DevTools' user agent to Firefox fixed it.

So while any page of a space (a card or a sign-in popup) is on Google's sign-in server, the space's
profile presents Firefox everywhere a site can look (identity.apply_firefox), and a few seconds after
the last one leaves it goes back to Chrome. The switch happens before the navigation is sent, so the
sign-in page itself loads with the consistent identity.

Where even that fails, "Fix and sign in again" (TabController._offer_signin_fix) presents Firefox to
every site until the sign-in has worked: ``signedIn`` fires once Google has handed out its session
cookies and the last sign-in page has been left, and ProfileManager then goes back to Chrome.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

from jbrowser.engine import identity

log = logging.getLogger(__name__)

# Google's sign-in servers, including the country ones (accounts.google.co.uk, ...) and the YouTube hop
# that finishes every sign-in (accounts.youtube.com/accounts/SetSID).
SIGNIN_HOST = re.compile(r"^accounts\.(?:google\.[a-z]{2,3}(?:\.[a-z]{2})?|youtube\.com)$")
# After the last sign-in page Google still bounces through a few servers to hand the sign-in to its
# other sites. Presenting Chrome again in the middle of that hand-off could undo the sign-in.
RESTORE_DELAY_MS = 12000
RENAVIGATE_GAP = 30.0        # s: load a sign-in page again at most this often (see _on_url)
# Google's session cookies: set on .google.com only once the password (and any second step) was accepted.
SESSION_COOKIES = {b"SID", b"__Secure-1PSID", b"__Secure-3PSID", b"SAPISID"}
# Pages Google only shows after a successful sign-in (the hand-off to its other sites).
SUCCESS_PATH = re.compile(r"/(?:accounts/)?(?:SetSID|CheckCookie)\b", re.IGNORECASE)


def is_signin_url(url: QUrl) -> bool:
    return url.scheme() in ("https", "http") and bool(SIGNIN_HOST.match(url.host().lower()))


def is_rejection_url(url: QUrl) -> bool:
    """Google's "Couldn't sign you in. This browser or app may not be secure" page."""
    return is_signin_url(url) and "rejected" in url.path().lower()


def is_success_url(url: QUrl) -> bool:
    return is_signin_url(url) and bool(SUCCESS_PATH.search(url.path()))


def is_session_cookie(cookie: QNetworkCookie) -> bool:
    domain = cookie.domain().lower().lstrip(".")
    return bytes(cookie.name()) in SESSION_COOKIES and (domain == "google.com" or domain.endswith(".google.com"))


class SigninIdentity(QObject):
    """Keeps track of which pages are on a sign-in server and switches their profiles' identity."""

    signedIn = pyqtSignal()     # a Google sign-in worked and its last page was left a while ago

    def __init__(self, restore: Callable[[QWebEngineProfile], None], parent: QObject | None = None,
                 always_firefox: Callable[[], bool] = lambda: False):
        super().__init__(parent)
        self._restore_profile = restore          # applies the normal (Chrome) identity again
        self._always_firefox = always_firefox    # Settings → Advanced: every space presents Firefox anyway
        self._on_signin: dict[int, QWebEngineProfile] = {}    # id(page) -> its profile
        self._firefox: dict[int, QWebEngineProfile] = {}      # id(profile) -> profile presenting Firefox
        self._renavigated: dict[int, float] = {}
        self._visited: set[int] = set()          # id(profile): a page of it is signing in right now
        self._succeeded = False                  # Google accepted a sign-in since the last signedIn
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(RESTORE_DELAY_MS)
        self._timer.timeout.connect(self._restore_idle)

    def is_firefox(self, profile: QWebEngineProfile) -> bool:
        return id(profile) in self._firefox

    def watch(self, page: QWebEnginePage) -> None:
        pid = id(page)
        page.urlChanged.connect(lambda url, p=page: self._on_url(p, url))
        page.destroyed.connect(lambda *_a, k=pid: self._forget(k))

    def before_navigation(self, page: QWebEnginePage, url: QUrl, is_main: bool) -> bool:
        """Called from acceptNavigationRequest (also for redirects), before the request is sent.
        Returns False when the navigation has to wait: Chromium can't change a page's identity from
        inside that callback, so the space switches to Firefox a moment later and then the page
        loads ``url`` again. Google never sees a request from the half-switched browser."""
        if not (is_main and is_signin_url(url)):
            return True
        profile = page.profile()
        self._on_signin[id(page)] = profile
        self._visited.add(id(profile))
        if is_success_url(url):
            self._succeeded = True
        if id(profile) in self._firefox or self._always_firefox():
            return True
        QTimer.singleShot(0, lambda p=page, u=QUrl(url): self._switch_and_load(p, u))
        return False

    # ------------------------------------------------------------ internals
    def _switch_and_load(self, page: QWebEnginePage, url: QUrl) -> None:
        try:
            self._enter(page)
            page.setUrl(url)
        except RuntimeError:          # the card or popup was closed meanwhile
            pass

    def _on_url(self, page: QWebEnginePage, url: QUrl) -> None:
        if not is_signin_url(url):
            self._leave(id(page))
            return
        self._on_signin[id(page)] = page.profile()
        self._visited.add(id(page.profile()))
        if is_success_url(url):
            self._succeeded = True
        if self._always_firefox() or id(page.profile()) in self._firefox:
            return
        # The page got there without passing acceptNavigationRequest first, so it may have loaded as
        # Chrome: switch, and load it again (once). Deferred: this signal comes from inside Chromium.
        now = time.monotonic()
        if now - self._renavigated.get(id(page), 0.0) > RENAVIGATE_GAP:
            self._renavigated[id(page)] = now
            log.info("Loading the sign-in page again with the sign-in identity")
            QTimer.singleShot(0, lambda p=page, u=QUrl(url): self._switch_and_load(p, u))

    def _enter(self, page: QWebEnginePage) -> None:
        profile = page.profile()
        self._on_signin[id(page)] = profile
        if id(profile) not in self._firefox:
            self._firefox[id(profile)] = profile
            identity.apply_firefox(profile)
            log.info("A page is signing in to Google: its space presents Firefox for now")

    def _leave(self, pid: int) -> None:
        if self._on_signin.pop(pid, None) is not None:
            self._timer.start()

    def _forget(self, pid: int) -> None:
        self._renavigated.pop(pid, None)
        self._leave(pid)

    def on_cookie(self, profile: QWebEngineProfile, cookie: QNetworkCookie) -> None:
        """Every cookie a profile receives (cheap check). Google's session cookies arriving while one of the
        profile's pages is signing in mean the sign-in worked. (Cookies loaded from disk at start-up don't
        count: no page is signing in then.)"""
        if id(profile) in self._visited and is_session_cookie(cookie):
            self._succeeded = True

    def _restore_idle(self) -> None:
        busy = {id(p) for p in self._on_signin.values()}
        for key, profile in list(self._firefox.items()):
            if key not in busy:
                del self._firefox[key]
                try:
                    self._restore_profile(profile)
                except RuntimeError:          # the profile was deleted meanwhile
                    continue
                log.info("Sign-in finished: the space presents Chrome again")
        self._visited &= busy
        if not busy and self._succeeded:
            self._succeeded = False
            log.info("Google sign-in succeeded")
            self.signedIn.emit()

    def forget_profile(self, profile: QWebEngineProfile) -> None:
        """The profile is going away (its space was closed)."""
        self._firefox.pop(id(profile), None)
        self._visited.discard(id(profile))
        for pid, prof in list(self._on_signin.items()):
            if prof is profile:
                del self._on_signin[pid]
