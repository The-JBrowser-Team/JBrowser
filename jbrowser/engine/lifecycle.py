"""Tab lifecycle: out-of-sight render throttling and the smart memory saver (tab sleeping).

Throttle  — exactly 5 s after a card leaves the viewport (or its space is hidden) the page
            is marked hidden (Chromium stops producing frames, rAF halts, timers are
            throttled) and, when safe, frozen (JS tasks & timers paused). Entering the
            viewport restores full throughput immediately.
Sleep     — after the preset inactivity period a background card is hibernated
            (renderer discarded, static snapshot shown) unless the smart-protection guard
            finds playing media, WebSockets/WebRTC, unsaved edits, beforeunload handlers,
            downloads or DevTools.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal

from jbrowser.core.settings import SLEEP_PRESETS
from jbrowser.core.urls import strip_www
from jbrowser.models.tab import Tab

if TYPE_CHECKING:
    from jbrowser.context import AppContext

log = logging.getLogger(__name__)

THROTTLE_DELAY_MS = 5000
SCAN_INTERVAL_MS = 20000


class LifecycleManager(QObject):
    aboutToThrottle = pyqtSignal(str)   # tab id — views take a snapshot while still rendered
    aboutToSleep = pyqtSignal(str)      # tab id — views swap the live view for the snapshot
    woke = pyqtSignal(str)              # tab id
    sleepBlocked = pyqtSignal(str, str)  # tab id, human-readable reason

    def __init__(self, ctx: "AppContext", parent: QObject | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._in_view: set[str] = set()
        self._render_visible: dict[str, bool] = {}
        self._timers: dict[str, QTimer] = {}
        self._busy: set[str] = set()
        self._scan = QTimer(self)
        self._scan.setInterval(SCAN_INTERVAL_MS)
        self._scan.timeout.connect(self.scan)
        self._scan.start()
        ctx.settings.changed.connect(self._on_setting)
        ctx.state.tabRemoved.connect(lambda tab, _s: self._forget(tab.id))

    # ------------------------------------------------------------- settings
    @property
    def throttle_enabled(self) -> bool:
        return bool(self.ctx.settings.get("performance.throttle"))

    def sleep_minutes(self) -> int | None:
        return SLEEP_PRESETS.get(self.ctx.settings.get("performance.sleep_preset"), SLEEP_PRESETS["moderate"])[1]

    def _on_setting(self, key: str, value) -> None:
        if key == "performance.throttle" and not value:
            for tid in list(self._timers):
                self._cancel(tid)
            for ctrl in self.ctx.engine.controllers():
                if ctrl.tab.throttled:
                    ctrl.unthrottle(self._render_visible.get(ctrl.tab.id, False))

    def _forget(self, tab_id: str) -> None:
        self._cancel(tab_id)
        self._in_view.discard(tab_id)
        self._render_visible.pop(tab_id, None)
        self._busy.discard(tab_id)

    # ----------------------------------------------------------- visibility
    def is_in_view(self, tab_id: str) -> bool:
        return tab_id in self._in_view

    def set_in_view(self, tab_id: str, visible: bool, render_visible: bool) -> None:
        """Reported by canvases whenever a card enters/leaves the visible viewport."""
        self._render_visible[tab_id] = render_visible
        ctrl = self.ctx.engine.controller(tab_id)
        if ctrl is None:
            return
        if visible:
            self._in_view.add(tab_id)
            self._cancel(tab_id)
            ctrl.tab.touch()
            if ctrl.tab.throttled or not ctrl.page.isVisible():
                ctrl.unthrottle(render_visible)
            return
        was = tab_id in self._in_view
        self._in_view.discard(tab_id)
        if was:
            ctrl.tab.touch()  # inactivity is measured from when the card left sight
        if self.throttle_enabled and ctrl.tab.loaded and not ctrl.tab.sleeping and tab_id not in self._timers:
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(THROTTLE_DELAY_MS)
            t.timeout.connect(lambda tid=tab_id: self._throttle_now(tid))
            self._timers[tab_id] = t
            t.start()

    def _cancel(self, tab_id: str) -> None:
        t = self._timers.pop(tab_id, None)
        if t is not None:
            t.stop()
            t.deleteLater()

    def _throttle_now(self, tab_id: str) -> None:
        self._cancel(tab_id)
        ctrl = self.ctx.engine.controller(tab_id)
        if ctrl is None or tab_id in self._in_view or ctrl.tab.sleeping or not ctrl.tab.loaded:
            return
        self.aboutToThrottle.emit(tab_id)

        def decided(data: dict | None, was_frozen: bool, c=ctrl):
            if c.disposed or c.tab.id in self._in_view:
                return
            freeze = data is not None and not (data.get("media") or data.get("ws") or data.get("rtc")
                                               or data.get("fullscreen"))
            c.throttle(freeze=freeze)

        ctrl.probe(decided)

    # ---------------------------------------------------------------- sleep
    def _is_protected_sync(self, tab: Tab) -> str | None:
        ctrl = self.ctx.engine.controller(tab.id)
        if ctrl is None:
            return "no engine"
        space = self.ctx.state.space_of(tab)
        if ctrl.page.recentlyAudible() or tab.audible:
            return "it is playing audio"
        if self.ctx.downloads.active_for_tab(tab.id):
            return "it has a download in progress"
        if tab.devtools:
            return "Developer Tools are open"
        if space and space.id == self.ctx.state.active_space_id and space.active_tab_id == tab.id:
            return "it is the focused card"
        if tab.id in self._in_view:
            return "it is visible"
        host = strip_www(QUrl(tab.url).host())
        never = {strip_www(h) for h in self.ctx.settings.get("performance.never_sleep") or []}
        if host and host in never:
            return "the site is on the never-sleep list"
        return None

    @staticmethod
    def _reason_from_probe(data: dict | None) -> str | None:
        if data is None:
            return "the page did not respond"
        if data.get("media"):
            return "it is playing media"
        if data.get("rtc"):
            return "it has an active call (WebRTC)"
        if data.get("ws"):
            return "it has an open WebSocket connection"
        if data.get("dirty"):
            return "it has unsaved form input"
        if data.get("beforeunload"):
            return "the page may have unsaved work"
        if data.get("fullscreen"):
            return "it is in full screen"
        return None

    def scan(self) -> None:
        minutes = self.sleep_minutes()
        if not minutes:
            return
        now = time.monotonic()
        for tab in self.ctx.state.all_tabs():
            if tab.sleeping or not tab.loaded or tab.crashed or tab.id in self._busy:
                continue
            if now - tab.last_active < minutes * 60:
                continue
            if self._is_protected_sync(tab):
                continue
            self.try_sleep(tab, manual=False)

    def try_sleep(self, tab: Tab, manual: bool = True) -> None:
        reason = self._is_protected_sync(tab)
        if reason and not (manual and reason in ("it is the focused card", "it is visible")):
            if manual:
                self.sleepBlocked.emit(tab.id, reason)
            return
        ctrl = self.ctx.engine.controller(tab.id)
        if ctrl is None or tab.sleeping:
            return
        if not tab.loaded:
            tab.update(sleeping=True)
            return
        self._busy.add(tab.id)

        def decided(data: dict | None, was_frozen: bool, c=ctrl, t=tab):
            self._busy.discard(t.id)
            if c.disposed:
                return
            why = self._reason_from_probe(data)
            if not why and not manual:
                why = self._is_protected_sync(t)  # state may have changed while probing
            if why:
                if was_frozen:
                    c.refreeze()
                if manual:
                    self.sleepBlocked.emit(t.id, why)
                return
            self.aboutToSleep.emit(t.id)  # UI swaps in the snapshot and hides the live view
            if not c.discard():
                if manual:
                    self.sleepBlocked.emit(t.id, "the engine reports the page is still in use")
                self.woke.emit(t.id)
                return
            self._cancel(t.id)
            log.info("Card slept: %s", t.url)

        ctrl.probe(decided)

    def wake(self, tab_id: str) -> None:
        ctrl = self.ctx.engine.controller(tab_id)
        if ctrl is None:
            return
        tab = ctrl.tab
        if not tab.sleeping and tab.loaded:
            return
        tab.touch()
        ctrl.wake()
        self.woke.emit(tab_id)

    def sleep_inactive_now(self) -> int:
        count = 0
        for tab in self.ctx.state.all_tabs():
            if not tab.sleeping and tab.loaded and not self._is_protected_sync(tab):
                self.try_sleep(tab, manual=False)
                count += 1
        return count

    def wake_all(self, space_id: str | None = None) -> None:
        for tab in self.ctx.state.all_tabs():
            if tab.sleeping and (space_id is None or tab.space_id == space_id):
                self.wake(tab.id)
