"""One owner for a top-level window's Windows 11 look: the system material behind it and its light/dark mode.

Windows keeps that state per native window, and more than one party touches it: JBrowser, and Qt, which
re-applies its own idea of light/dark to every window frame when the application palette or colour scheme
changes. Earlier versions applied the state from several places, read it back, rebuilt the material when
it looked wrong and changed JBrowser's whole look when Windows reported a failure. On some PCs those
reactions fed each other: pale windows behind dark text, a stale rectangle after maximising, a caption
that stopped dragging, a window that flashed black or white and stopped responding.

So, per window, one ``Backdrop``:

- applies the material and the mode when they change (once for each new native window, and with the
  same values again when the window comes back from the taskbar), and never reads anything back from
  Windows;
- after anything that can reset the mode (palette or theme changes, activation, window state changes,
  Windows settings broadcasts), sets the mode again. Setting the same value is free and changes nothing
  on screen, so nothing can loop;
- never rebuilds the material, never forces a frame refresh and never restyles the application.

JBrowser also paints its own base colour under its content (``Theme.backdrop_layers``), so the window
stays readable whatever Windows draws behind it. When Windows isn't drawing the material at all, or draws
the wrong one, ``LookGuard`` makes that base opaque (``Theme.see_through``).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from jbrowser.platform import win
from jbrowser.ui.theme import theme

log = logging.getLogger(__name__)

# Events after which Qt (or Windows) may have changed the window's light/dark mode.
_RECHECK = (QEvent.Type.Show, QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange,
            QEvent.Type.WindowStateChange, QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate)


class Backdrop(QObject):
    """Keeps ``window``'s system backdrop and light/dark mode in step with the theme.

    ``kind`` is ``"window"`` (a frameless JBrowser window with a material), ``"popup"`` (a borderless
    popup: Acrylic over the whole window) or ``"frame"`` (a dialog with a native title bar: only the
    mode and the caption colours)."""

    CLOAK_MS = 120      # a new window stays invisible this long: its material and first frame get ready

    def __init__(self, window: QWidget, kind: str = "window"):
        super().__init__(window)
        self._w = window
        self._kind = kind
        self._applied: tuple | None = None       # (hwnd, material, dark) last applied
        self._pending = False
        self._reassert = False                    # set the material again (same values) after a restore
        self._shown_hwnd = 0                      # the native window already shown once (cloaked)
        self.active = False                       # True while a translucent material is in use
        window.installEventFilter(self)
        theme().changed.connect(self.schedule)

    # ------------------------------------------------------------ triggers
    def eventFilter(self, obj, ev) -> bool:
        if obj is self._w:
            t = ev.type()
            if t == QEvent.Type.WinIdChange:
                self._applied = None              # a new native window: apply everything again
                self.schedule()
            elif t == QEvent.Type.Show and self._kind == "popup":
                self._run(showing=True)           # menus and popups: material from their very first frame
            elif t == QEvent.Type.Show and not ev.spontaneous():
                self._cloak_first_show()
                self.schedule()
            elif t == QEvent.Type.WindowStateChange:
                # Back from the taskbar: some drivers drop a minimised window's material. Setting the same
                # values again is harmless, so do it (no frame refresh, nothing read back).
                if ev.oldState() & Qt.WindowState.WindowMinimized and not obj.isMinimized():
                    self._reassert = True
                self.schedule()
            elif t in _RECHECK:
                self.schedule()
        return False

    def schedule(self) -> None:
        """Apply soon, once, after the current event (Qt's own handling of it comes first)."""
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self._run)

    def _run(self, showing: bool = False) -> None:
        self._pending = False
        try:
            self.apply(showing)
        except RuntimeError:                      # the window was deleted meanwhile
            pass
        except Exception:                         # never let the look take the app down
            log.exception("Backdrop update failed")

    def _cloak_first_show(self) -> None:
        """Keep a new window invisible (cloaked: still there for Windows and Qt) from just before it first
        appears until its material, light/dark mode and first frame are in place. Before its first frame,
        Windows shows a new window as a white or black rectangle. (The Show event comes before the window
        is shown on screen.)"""
        w = self._w
        if not win.IS_WINDOWS or os.environ.get("JBROWSER_NO_CLOAK") == "1" \
                or not w.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return
        hwnd = int(w.winId())
        if hwnd == self._shown_hwnd:
            return
        self._shown_hwnd = hwnd
        if not win.set_cloak(hwnd, True):
            return

        def uncloak() -> None:
            win.set_cloak(hwnd, False)            # always, even if the window is gone (then it's a no-op)
            for delay in (0, 100):                # fresh frames now that Windows composites the window
                QTimer.singleShot(delay, self._safe_update)

        def reveal() -> None:
            try:
                self.apply(showing=True)
                if w.isVisible():
                    w.repaint()                   # the first frame, painted before anyone sees the window
            except RuntimeError:
                pass
            except Exception:
                log.exception("First frame failed")
            finally:
                QTimer.singleShot(30, uncloak)

        QTimer.singleShot(self.CLOAK_MS, reveal)

    def _safe_update(self) -> None:
        try:
            self._w.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------- applying
    def apply(self, showing: bool = False) -> None:
        w = self._w
        if not win.IS_WINDOWS or not w.testAttribute(Qt.WidgetAttribute.WA_WState_Created) \
                or not (showing or w.isVisible()):
            return                                # no native window yet: Show will bring us back
        th = theme()
        hwnd = int(w.winId())
        if self._kind == "frame":
            win.set_dark_title(hwnd, th.dark)
            win.set_caption_colors(hwnd, th.c("dialog_solid"), th.c("text"))
            return
        material = th.settings.get("appearance.material") if th.translucent else "solid"
        state = (hwnd, material, th.dark)
        reassert, self._reassert = self._reassert, False
        if state == self._applied and not reassert:
            win.set_dark_title(hwnd, th.dark)     # Qt may have reset it; the same value changes nothing
            return
        new_window = self._applied is None or self._applied[0] != hwnd
        if self._kind == "popup":
            self.active = th.translucent and win.apply_popup_backdrop(hwnd, th.dark)
            win.set_corner_preference(hwnd)
        else:
            self.active = win.apply_backdrop(hwnd, material, th.dark) and material != "solid"
            if new_window:
                win.refresh_frame(hwnd)           # once per native window: our WM_NCCALCSIZE takes over
        self._applied = state
        log.debug("Backdrop %s for %s: material=%s dark=%s active=%s", "set" if new_window else "updated",
                  type(w).__name__, material, th.dark, self.active)
        w.update()


class WindowTransitions(QObject):
    """Minimise, maximise and restore without the colour warp.

    Windows animates these with a snapshot of the window. On some PCs the see-through parts of that
    snapshot come out in the wrong colours (pale, dark or tinted) until something repaints. So the
    window paints itself opaque just before the change (``Theme.hold_opaque``), stays opaque while
    Windows animates, then repaints normally. Commands from Windows itself (taskbar, Win+arrow keys,
    double-clicking the caption) arrive as WM_SYSCOMMAND: the window takes them over, paints, and sends
    them again (NativeFrame.on_transition)."""

    PAINT_MS = 40       # time for the opaque frame to reach the screen before Windows animates
    HOLD_MS = 420       # Windows' minimise / maximise animations take about 250 ms

    def __init__(self, window: QWidget, native: "win.NativeFrame", repaint=None):
        super().__init__(window)
        self._w = window
        self._native = native
        self._repaint = repaint or window.update
        native.on_transition = self._on_native
        self._release = QTimer(self)
        self._release.setSingleShot(True)
        self._release.setInterval(self.HOLD_MS)
        self._release.timeout.connect(self._end)
        window.installEventFilter(self)

    def run(self, action) -> None:
        w = self._w
        if not (win.IS_WINDOWS and theme().translucent and w.isVisible() and not w.isMinimized()):
            action()
            return
        theme().hold_opaque = True
        self._release.stop()
        w.repaint()                       # now, so the snapshot Windows takes is the opaque one
        QTimer.singleShot(self.PAINT_MS, action)
        QTimer.singleShot(2000, self._end)    # in case the window's state didn't change after all

    def _on_native(self, command: int) -> bool:
        """Inside the window procedure: only schedule work here."""
        if not theme().translucent or self._w.isMinimized():
            return False                  # restoring from the taskbar: the snapshot was taken on minimise

        def send(hwnd=int(self._w.winId())):
            self._native.passing = command
            win.post_syscommand(hwnd, command)
        QTimer.singleShot(0, lambda: self.run(send))
        return True

    def eventFilter(self, obj, ev) -> bool:
        if obj is self._w and ev.type() == QEvent.Type.WindowStateChange:
            self._release.start()         # the opaque hold ends once Windows has finished animating
            if not obj.isMinimized():
                # Back on screen: repaint (a stale or wrongly coloured first frame never stays).
                for delay in (0, 120):
                    QTimer.singleShot(delay, self._safe_repaint)
        return False

    def _safe_repaint(self) -> None:
        try:
            if not self._w.isMinimized():
                self._repaint()
        except RuntimeError:
            pass

    def _end(self) -> None:
        th = theme()
        if th.hold_opaque:
            th.hold_opaque = False
            self._safe_repaint()


# ------------------------------------------------------------------ is the material really there?
_graphics_failure: str | None = None        # a Qt message saying windows can't have see-through pixels
_FAILURE_WORDS = ("fail", "unable", "unsupported", "not supported", "cannot", "could not")


def note_qt_message(text: str) -> None:
    """Called with every Qt message (app.py). Remembers one saying that the graphics driver can't give
    windows see-through pixels (no Direct Composition): Windows would show them black."""
    global _graphics_failure
    low = text.lower()
    if _graphics_failure is None and any(w in low for w in _FAILURE_WORDS) and (
            "composition" in low or "dcomp" in low
            or ("alpha" in low and ("swapchain" in low or "swap chain" in low))):
        _graphics_failure = text.strip()[:200]


def paint_probe_hole(p: QPainter, widget: QWidget) -> None:
    """Leave LookGuard's probe spot unpainted (call last in the paintEvent that draws ``widget``'s backdrop
    layers). Only for the one frame LookGuard reads back; otherwise does nothing."""
    g = LookGuard._instance
    hole = g._hole if g is not None else None
    if hole is not None and hole[0] is widget:
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(hole[1], Qt.GlobalColor.transparent)
        p.restore()


class LookGuard(QObject):
    """Decides whether Windows is really drawing Mica / Acrylic behind JBrowser (``Theme.see_through``).

    When it isn't, the see-through parts of JBrowser's windows show whatever Windows draws instead: a
    flat grey, white or black fill that needn't match the theme. JBrowser then paints an opaque base of
    its own, so its windows look like the Solid material, and goes back to see-through when it can.
    It learns this from:

    - Windows settings that turn materials off (transparency effects, energy saver, high contrast,
      Remote Desktop): checked every few seconds and whenever Windows broadcasts a change;
    - Qt saying that the graphics driver can't give windows see-through pixels (note_qt_message);
    - the screen itself. After a window appears, the theme changes, Windows changes a setting, or now and
      then on activation, JBrowser leaves a tiny spot at the top edge of the active window unpainted for
      one frame and reads what Windows composited there: the bare material. Black means see-through
      pixels don't work on this PC; a light material behind a dark JBrowser (or a dark one behind a
      light JBrowser) means Windows draws the wrong one. Two readings in a row must agree.
    """

    POLL_MS = 3000          # Windows settings
    SETTLE_MS = 160         # from painting the probe spot to reading it back (a few composited frames)
    CONFIRM_MS = 450        # between the two readings that must agree

    _instance: "LookGuard | None" = None

    @classmethod
    def instance(cls) -> "LookGuard":
        if cls._instance is None:
            cls._instance = cls(QApplication.instance())
        return cls._instance

    def __init__(self, parent: QObject | None):
        super().__init__(parent)
        self.blockers: list[str] = []
        self.verdict = "ok"                       # what the screen showed: "ok", "black" or "wrong"
        self._reading: str | None = None          # a reading that differs from the verdict, to be confirmed
        self._windows: list[tuple[QWidget, QWidget, Callable[[], QPoint | None]]] = []
        self._hole: tuple[QWidget, QRect] | None = None
        self._probing = False
        self._last_probe = 0.0
        self._simulate = os.environ.get("JBROWSER_NO_MATERIAL") == "1"     # testing: as if Windows had none
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._probe)
        self._poll = QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self.check)
        self._key = self._theme_key()
        theme().changed.connect(self._on_theme)
        if win.IS_WINDOWS:
            self.check()
            self._poll.start()

    # ---------------------------------------------------------------- windows
    def watch(self, window: QWidget, background: QWidget, spot: Callable[[], QPoint | None]) -> None:
        """Probe ``window`` when it's the active window. ``background`` paints its backdrop layers (and
        calls paint_probe_hole); ``spot()`` is a point in ``background`` where nothing else paints, or None
        when there is none right now."""
        self._windows.append((window, background, spot))
        window.installEventFilter(self)
        window.destroyed.connect(lambda *_a, w=window: self._forget(w))

    def _forget(self, window: QWidget) -> None:
        self._windows = [e for e in self._windows if e[0] is not window]
        if self._hole is not None and not any(e[1] is self._hole[0] for e in self._windows):
            self._hole = None

    def eventFilter(self, obj, ev) -> bool:
        t = ev.type()
        if t == QEvent.Type.Show and not ev.spontaneous():
            self.probe_soon(700)
        elif t == QEvent.Type.WindowActivate:
            if time.monotonic() - self._last_probe > (10 if self.verdict != "ok" else 30):
                self.probe_soon(500)
        elif t == QEvent.Type.WindowStateChange and ev.oldState() & Qt.WindowState.WindowMinimized \
                and not obj.isMinimized():
            self.probe_soon(700)
        return False

    def system_changed(self) -> None:
        """Windows broadcast a settings, theme, power or display change (NativeFrame.on_system_change)."""
        self.check()
        QTimer.singleShot(700, self.check)        # some settings reach the registry after the broadcast
        self.probe_soon(1200)

    # ---------------------------------------------------------------- decision
    @staticmethod
    def _theme_key() -> tuple:
        th = theme()
        return th.dark, th.translucent, th.settings.get("appearance.material")

    def _on_theme(self) -> None:
        key = self._theme_key()
        if key != self._key:                      # not for see_through itself: that changes no key
            self._key = key
            self._reading = None
            self.probe_soon(700)

    def check(self) -> None:
        """Windows settings that turn materials off, and Qt's graphics messages."""
        try:
            blockers = win.material_blockers()
        except Exception:
            log.exception("Couldn't read Windows' transparency settings")
            blockers = list(self.blockers)
        if self._simulate:
            blockers.append("JBROWSER_NO_MATERIAL")
        if _graphics_failure:
            blockers.append("no see-through windows with this graphics driver")
        if blockers != self.blockers:
            was = self.blockers
            self.blockers = blockers
            if blockers:
                log.info("Windows isn't drawing materials (%s): JBrowser paints its own base", "; ".join(blockers))
                if _graphics_failure and not any("graphics driver" in b for b in was):
                    log.info("Qt said: %s", _graphics_failure)
            else:
                log.info("Windows is drawing materials again")
                self.probe_soon(900)
        self._update()

    def _update(self) -> None:
        theme().set_see_through(not self.blockers and self.verdict == "ok")

    # ---------------------------------------------------------------- the screen
    def probe_soon(self, ms: int) -> None:
        if win.IS_WINDOWS:
            self._probe_timer.start(ms)

    def _target(self) -> tuple[QWidget, QWidget, Callable[[], QPoint | None]] | None:
        """The watched window that has the focus, on screen and not full screen."""
        fg = win.foreground_window()
        for entry in self._windows:
            w = entry[0]
            try:
                if w.isVisible() and not w.isMinimized() and not w.isFullScreen() and int(w.winId()) == fg:
                    return entry
            except RuntimeError:
                continue
        return None

    def _probe(self) -> None:
        th = theme()
        if self._probing or not th.translucent or th.hold_opaque or self.blockers:
            return
        target = self._target()
        if target is None:
            return
        window, background, spot = target
        try:
            pt = spot()
            if pt is None:
                return
            rect = QRect(pt.x() - 1, pt.y() - 1, 3, 3)
            self._probing = True
            self._last_probe = time.monotonic()
            self._hole = (background, rect)
            background.repaint(rect)              # the spot, unpainted, on its way to the screen
        except RuntimeError:
            self._hole, self._probing = None, False
            return
        QTimer.singleShot(self.SETTLE_MS, lambda: self._read(window, background, pt, rect))

    def _read(self, window: QWidget, background: QWidget, pt: QPoint, rect: QRect) -> None:
        self._probing = False
        self._hole = None
        try:
            background.update(rect)
            if not window.isVisible() or window.isMinimized():
                return
            dpr = window.devicePixelRatioF()
            at = background.mapTo(window, pt)
            rgb = win.sample_own_pixel(int(window.winId()), int((at.x() + 0.5) * dpr), int((at.y() + 0.5) * dpr))
        except RuntimeError:
            return
        if rgb is None or theme().hold_opaque:    # covered by another window, or mid-animation: no answer
            return
        reading = self._judge(rgb)
        log.debug("Material probe: rgb%s -> %s", rgb, reading)
        if reading == self.verdict:
            self._reading = None
            return
        if reading != self._reading:
            self._reading = reading               # once could be a passing frame: look again
            self.probe_soon(self.CONFIRM_MS)
            return
        self._reading = None
        self.verdict = reading
        if reading == "ok":
            log.info("Windows is drawing the material behind JBrowser again")
        else:
            log.info("Windows %s behind JBrowser (rgb%s): JBrowser paints its own base",
                     "draws black" if reading == "black" else "draws the wrong material", rgb)
        self._update()

    @staticmethod
    def _judge(rgb: tuple[int, int, int]) -> str:
        r, g, b = rgb
        if max(rgb) <= 3:
            return "black"                        # no see-through pixels: no material is that black
        if not win.IS_WIN11:
            return "ok"                           # Windows 10's blur is untinted: it shows what's behind
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        dark = theme().dark
        # Measured on Windows 11: dark Mica about 32; dark Acrylic 54 over black, 146 over white. Light
        # Mica about 244; light Acrylic 135 over black, 227 over white. In between, it can't be told apart.
        if (dark and luma > 170) or (not dark and luma < 110):
            return "wrong"
        return "ok"


def look_guard() -> LookGuard:
    return LookGuard.instance()


def caption_hit(window: QWidget, local: QPoint, max_button: QWidget | None) -> int:
    """The hit-test code for a point in a frameless JBrowser window: the caption (drag), the maximise
    button (Snap Layouts) or ordinary client area. Never raises: an error here used to make the window
    procedure fall back to "client area", and the window stopped dragging."""
    try:
        w = window.childAt(local)
        while w is not None and w.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents):
            w = w.parentWidget()
        if w is None:
            return win.HTCLIENT
        if max_button is not None and w is max_button:
            return win.HTMAXBUTTON
        if w.property("dragRegion"):
            return win.HTCAPTION
        return win.HTCLIENT
    except Exception:
        log.exception("Hit test failed")
        return win.HTCLIENT
