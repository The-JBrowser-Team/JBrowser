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
stays readable whatever Windows draws behind it.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PyQt6.QtWidgets import QWidget

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

    def __init__(self, window: QWidget, kind: str = "window"):
        super().__init__(window)
        self._w = window
        self._kind = kind
        self._applied: tuple | None = None       # (hwnd, material, dark) last applied
        self._pending = False
        self._reassert = False                    # set the material again (same values) after a restore
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
