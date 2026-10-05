"""Each top-level window's frame: its light/dark mode, rounded corners and first appearance.

JBrowser's windows are opaque and paint their own look (the Frosted picture, ui/frost.py, or the Solid colour);
Windows' see-through materials are never used. What is left for Windows to know is small, and ``Backdrop``
keeps it in step with the theme:

- the window's light/dark mode (DWMWA_USE_IMMERSIVE_DARK_MODE: the outline, and the caption of dialogs with a
  native title bar, whose caption colours are set too). Qt re-applies its own idea of light/dark to every frame
  when the palette changes, so the mode is set again after anything that can reset it; setting the same value
  changes nothing on screen, so nothing can loop;
- rounded corners;
- a new window stays cloaked (invisible, but there for Windows and Qt) until its first frame is painted, so it
  never flashes white or black.
"""
from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PyQt6.QtWidgets import QWidget

from jbrowser.platform import win
from jbrowser.ui.theme import theme

log = logging.getLogger(__name__)

# Events after which Qt (or Windows) may have changed the window's light/dark mode.
_RECHECK = (QEvent.Type.Show, QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange,
            QEvent.Type.WindowStateChange, QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate)


class Backdrop(QObject):
    """Keeps ``window``'s frame in step with the theme. ``kind`` is ``"window"`` (a frameless JBrowser window),
    ``"popup"`` (a borderless popup: only rounded corners) or ``"frame"`` (a dialog with a native title bar:
    the mode and the caption colours)."""

    CLOAK_MS = 90       # a new window stays invisible this long while its first frame is painted

    def __init__(self, window: QWidget, kind: str = "window"):
        super().__init__(window)
        self._w = window
        self._kind = kind
        self._applied: tuple | None = None       # (hwnd, dark) last applied
        self._pending = False
        self._shown_hwnd = 0                      # the native window already shown once (cloaked)
        window.installEventFilter(self)
        theme().changed.connect(self.schedule)

    # ------------------------------------------------------------ triggers
    def eventFilter(self, obj, ev) -> bool:
        if obj is self._w:
            t = ev.type()
            if t == QEvent.Type.WinIdChange:
                self._applied = None              # a new native window: apply everything again
                self.schedule()
            elif t == QEvent.Type.Show and self._kind != "popup" and not ev.spontaneous():
                self._cloak_first_show()
                self.schedule()
            elif t in _RECHECK:
                self.schedule()
        return False

    def schedule(self) -> None:
        """Apply soon, once, after the current event (Qt's own handling of it comes first)."""
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self._run)

    def _run(self) -> None:
        self._pending = False
        try:
            self.apply()
        except RuntimeError:                      # the window was deleted meanwhile
            pass
        except Exception:                         # never let the frame take the app down
            log.exception("Window frame update failed")

    def _cloak_first_show(self) -> None:
        """The Show event comes before Windows shows the window: cloak it there, uncloak once painted."""
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
                win.set_cloak(hwnd, False)        # always (a no-op if the window is gone)

        QTimer.singleShot(self.CLOAK_MS, reveal)

    # ------------------------------------------------------------- applying
    def apply(self, showing: bool = False) -> None:
        w = self._w
        if not win.IS_WINDOWS or not w.testAttribute(Qt.WidgetAttribute.WA_WState_Created) \
                or not (showing or w.isVisible()):
            return                                # no native window yet: Show will bring us back
        th = theme()
        hwnd = int(w.winId())
        win.set_dark_title(hwnd, th.dark)         # cheap and idempotent: Qt may have reset it
        if self._kind == "frame":
            win.set_caption_colors(hwnd, th.c("dialog_solid"), th.c("text"))
        if self._applied is None or self._applied[0] != hwnd:
            win.set_corner_preference(hwnd)
            if self._kind == "window":
                win.refresh_frame(hwnd)           # once per native window: our WM_NCCALCSIZE takes over
        self._applied = (hwnd, th.dark)


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
