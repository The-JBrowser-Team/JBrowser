"""Windows 11 integration via the Win32 / DWM APIs (ctypes).

* Mica / Mica Alt / Acrylic system backdrops (DWMWA_SYSTEMBACKDROP_TYPE)
* Custom-drawn title bar that keeps native behaviour: the top caption is removed in
  WM_NCCALCSIZE while the invisible side/bottom resize borders, drop shadow, rounded
  corners, Aero Snap and the Windows 11 Snap Layouts flyout (HTMAXBUTTON) all remain.
* DPAPI for protecting local secrets, system accent colour, AppUserModelID.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
WIN_BUILD = sys.getwindowsversion().build if IS_WINDOWS else 0
IS_WIN11 = WIN_BUILD >= 22000

# Window messages / hit-test codes
WM_NCACTIVATE = 0x0086
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCRBUTTONDOWN = 0x00A4
WM_NCRBUTTONUP = 0x00A5
WM_NCMOUSELEAVE = 0x02A2
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE = 0xF020, 0xF030, 0xF120
WM_SETTINGCHANGE = 0x001A
WM_DWMCOLORIZATIONCOLORCHANGED = 0x0320
WM_THEMECHANGED = 0x031A
WM_DWMCOMPOSITIONCHANGED = 0x031E
WM_POWERBROADCAST = 0x0218          # energy saver, sleep and resume
WM_DISPLAYCHANGE = 0x007E
_SYSTEM_CHANGE_MESSAGES = (WM_SETTINGCHANGE, WM_THEMECHANGED, WM_DWMCOMPOSITIONCHANGED, WM_DWMCOLORIZATIONCOLORCHANGED,
                           WM_POWERBROADCAST, WM_DISPLAYCHANGE)

HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
_BORDER_HITS = {HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT}

DWMWA_CLOAK = 13
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT_LEGACY = 1029
DWMWCP_ROUND = 2
BACKDROPS = {"solid": 1, "mica": 2, "acrylic": 3, "mica_alt": 4}

SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92
SWP_FRAMECHANGED_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED


class MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


class HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD), ("lpszDefaultScheme", wintypes.LPWSTR)]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _shell32 = ctypes.windll.shell32
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32

    _user32.DefWindowProcW.restype = wintypes.LPARAM
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    _user32.GetDpiForWindow.restype = wintypes.UINT
    _user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwm.DwmSetWindowAttribute.restype = ctypes.c_long
    _dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
    _dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
    _shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
    _shell32.SHAppBarMessage.restype = ctypes.c_size_t
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(DATA_BLOB)]
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(DATA_BLOB),
                                            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.POINTER(DATA_BLOB)]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.WindowFromPoint.argtypes = [wintypes.POINT]
    _user32.WindowFromPoint.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _gdi32 = ctypes.windll.gdi32
    _gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.GetPixel.restype = wintypes.DWORD


def _set_dword_attr(hwnd: int, attr: int, value: int) -> bool:
    v = ctypes.c_int(value)
    return _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0


def set_dark_title(hwnd: int, dark: bool) -> None:
    if not IS_WINDOWS:
        return
    if not _set_dword_attr(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark)):
        _set_dword_attr(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, int(dark))


_backdrop_supported: bool | None = None


def backdrop_supported() -> bool:
    """Whether this Windows can draw a system backdrop (Mica / Acrylic) behind a window: Windows 11, or
    Windows 10 with pywinstyles' blur. Decided once; JBrowser's look never depends on a single call."""
    global _backdrop_supported
    if _backdrop_supported is None:
        if not IS_WINDOWS:
            _backdrop_supported = False
        elif WIN_BUILD >= 22000:
            _backdrop_supported = True
        else:
            import importlib.util
            _backdrop_supported = importlib.util.find_spec("pywinstyles") is not None
    return _backdrop_supported


def _colorref(c: QColor) -> int:
    return (c.blue() << 16) | (c.green() << 8) | c.red()


def set_caption_colors(hwnd: int, background: QColor, text: QColor) -> None:
    """Tint a native title bar (Windows 11) so it matches the window content."""
    if not IS_WINDOWS or WIN_BUILD < 22000:
        return
    _set_dword_attr(hwnd, 35, _colorref(background))   # DWMWA_CAPTION_COLOR
    _set_dword_attr(hwnd, 36, _colorref(text))         # DWMWA_TEXT_COLOR


def set_corner_preference(hwnd: int, preference: int = DWMWCP_ROUND) -> None:
    """Rounded corners (2 = round, 3 = small) — used for popups, menus and tooltips."""
    if IS_WINDOWS and WIN_BUILD >= 22000:
        _set_dword_attr(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, preference)


def apply_backdrop(hwnd: int, material: str, dark: bool) -> bool:
    """Apply a Windows 11 system backdrop. Returns True when a translucent material is active.
    (ui/backdrop.py decides when; the result is only logged, never used to change the look.)"""
    if not IS_WINDOWS:
        return False
    set_dark_title(hwnd, dark)
    _set_dword_attr(hwnd, 2, 2)  # DWMWA_NCRENDERING_POLICY = DWMNCRP_ENABLED (full screen may disable it)
    _set_dword_attr(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    margins = MARGINS(0, 0, 0, 0)
    _dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    if material == "solid":
        _set_dword_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, BACKDROPS["solid"])
        return False
    if WIN_BUILD >= 22523:
        return _set_dword_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, BACKDROPS.get(material, 2))
    if WIN_BUILD >= 22000:
        return _set_dword_attr(hwnd, DWMWA_MICA_EFFECT_LEGACY, 1)
    # Windows 10: fall back to pywinstyles' acrylic blur-behind if available.
    try:
        import pywinstyles  # type: ignore

        pywinstyles.apply_style(int(hwnd), "acrylic")  # accepts a raw HWND
        return True
    except Exception as exc:  # pragma: no cover - depends on OS build
        log.info("No system backdrop available: %s", exc)
        return False


def apply_popup_backdrop(hwnd: int, dark: bool) -> bool:
    """Acrylic behind a borderless popup (Windows 11 22H2 and later). Returns True when active."""
    if not IS_WINDOWS or WIN_BUILD < 22523:
        return False
    set_dark_title(hwnd, dark)
    margins = MARGINS(-1, -1, -1, -1)        # a popup has no frame: the whole window is backdrop
    _dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    return _set_dword_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, BACKDROPS["acrylic"])


def refresh_frame(hwnd: int) -> None:
    if IS_WINDOWS:
        _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FRAMECHANGED_FLAGS)


def set_transitions(hwnd: int, enabled: bool) -> None:
    """Windows' minimise / maximise / restore animations for this window (DWMWA_TRANSITIONS_FORCEDISABLED)."""
    if IS_WINDOWS:
        _set_dword_attr(hwnd, 3, 0 if enabled else 1)


def set_cloak(hwnd: int, cloaked: bool) -> bool:
    """Hide (or show again) a window from the screen without hiding it from Windows: a new window is
    cloaked until its material and first frame are ready, so it never flashes white or black."""
    return IS_WINDOWS and _set_dword_attr(hwnd, DWMWA_CLOAK, int(cloaked))


# ---------------------------------------------------------------------------- can Windows show a material?
# Mica and Acrylic only appear when Windows draws them. With transparency effects off, energy saver on,
# high contrast or over Remote Desktop, Windows draws a plain fill instead, and JBrowser's see-through
# layers would sit on top of whatever that fill is. ui/backdrop.py (LookGuard) paints JBrowser's own
# opaque base in those cases.
def transparency_effects_on() -> bool:
    """Settings → Personalisation → Colours → Transparency effects."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "EnableTransparency")
        return bool(value)
    except OSError:
        return True                       # never written: Windows' default (on)


def high_contrast_on() -> bool:
    if not IS_WINDOWS:
        return False
    hc = HIGHCONTRASTW()
    hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
    if _user32.SystemParametersInfoW(0x0042, hc.cbSize, ctypes.byref(hc), 0):     # SPI_GETHIGHCONTRAST
        return bool(hc.dwFlags & 0x1)                                              # HCF_HIGHCONTRASTON
    return False


def energy_saver_on() -> bool:
    """Battery saver / energy saver, which turns Windows' transparency effects off while it's on."""
    if not IS_WINDOWS:
        return False
    status = SYSTEM_POWER_STATUS()
    if _kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return status.SystemStatusFlag == 1
    return False


def remote_session() -> bool:
    return IS_WINDOWS and bool(_user32.GetSystemMetrics(0x1000))                 # SM_REMOTESESSION


def material_blockers() -> list[str]:
    """Why Windows won't draw Mica or Acrylic right now (empty when it will)."""
    if not IS_WINDOWS:
        return ["not Windows"]
    out = []
    if not transparency_effects_on():
        out.append("transparency effects are off")
    if energy_saver_on():
        out.append("energy saver is on")
    if high_contrast_on():
        out.append("a high contrast theme is on")
    if remote_session():
        out.append("Remote Desktop")
    return out


def sample_own_pixel(hwnd: int, x: int, y: int) -> tuple[int, int, int] | None:
    """The colour on screen at client pixel (x, y) of ``hwnd``, as Windows composited it, or None when
    another window covers that point (then it says nothing about ``hwnd``)."""
    if not IS_WINDOWS:
        return None
    pt = wintypes.POINT(x, y)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    top = _user32.WindowFromPoint(pt)
    if not top or int(_user32.GetAncestor(top, 2) or 0) != int(hwnd):              # GA_ROOT
        return None
    dc = _user32.GetDC(None)
    if not dc:
        return None
    try:
        c = _gdi32.GetPixel(dc, pt.x, pt.y)
    finally:
        _user32.ReleaseDC(None, dc)
    if c == 0xFFFFFFFF:                                                            # CLR_INVALID
        return None
    return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF


def foreground_window() -> int:
    return int(_user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def post_syscommand(hwnd: int, command: int) -> None:
    if IS_WINDOWS:
        _user32.PostMessageW(hwnd, WM_SYSCOMMAND, command, 0)


def is_maximized(hwnd: int) -> bool:
    return bool(IS_WINDOWS and _user32.IsZoomed(hwnd))


def _frame_thickness(hwnd: int) -> tuple[int, int]:
    dpi = _user32.GetDpiForWindow(hwnd) or 96
    pad = _user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
    return (_user32.GetSystemMetricsForDpi(SM_CXSIZEFRAME, dpi) + pad,
            _user32.GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi) + pad)


def _autohide_taskbar_edge() -> int | None:
    """Return the ABE_* edge of an auto-hiding taskbar, or None."""
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    state = _shell32.SHAppBarMessage(4, ctypes.byref(abd))  # ABM_GETSTATE
    if not state & 0x1:  # ABS_AUTOHIDE
        return None
    abd2 = APPBARDATA()
    abd2.cbSize = ctypes.sizeof(APPBARDATA)
    _shell32.SHAppBarMessage(5, ctypes.byref(abd2))  # ABM_GETTASKBARPOS
    return int(abd2.uEdge)


class NativeFrame:
    """Implements the non-client behaviour for a custom-titlebar top-level window.

    ``hit_test(local_logical_point) -> int`` is supplied by the window and returns
    HTCAPTION for drag regions, HTMAXBUTTON over the maximise button, else HTCLIENT.
    """

    RESIZE_BORDER = 6   # logical px inside each edge that resize the window
    CORNER = 14         # logical px of the diagonal corner grips

    def __init__(self, hwnd_getter: Callable[[], int], dpr_getter: Callable[[], float],
                 hit_test: Callable[[QPoint], int],
                 on_max_hover: Callable[[bool], None], on_max_press: Callable[[bool], None],
                 on_max_click: Callable[[], None]):
        self._hwnd = hwnd_getter
        self._dpr = dpr_getter
        self._hit_test = hit_test
        self._on_max_hover = on_max_hover
        self._on_max_press = on_max_press
        self._on_max_click = on_max_click
        self._max_hover = False
        self.enabled = IS_WINDOWS
        self.resizable: Callable[[], bool] = lambda: True
        # Right-click on a drag region: show the app's own menu instead of the system menu.
        self.on_caption_menu: Callable[[], None] | None = None
        # Windows changed a setting that can reset a window's light/dark state (ui/backdrop.py).
        self.on_system_change: Callable[[], None] | None = None
        # Minimise / maximise / restore asked for by Windows (taskbar, Win+arrow keys, caption double-click).
        # Returns True when the window takes it over and sends the command again itself (MainWindow.transition).
        self.on_transition: Callable[[int], bool] | None = None
        self.passing: int | None = None     # a command sent again by the window: let Windows carry it out
        # Windows draws Mica and Acrylic as a flat grey or white fill while a window is inactive. JBrowser
        # keeps its frame in the active state instead, so the window looks the same whether or not it has
        # the focus. (Qt still learns about activation from WM_ACTIVATE.)
        self.keep_active_look = os.environ.get("JBROWSER_INACTIVE_LOOK") != "1"

    def _set_hover(self, value: bool) -> None:
        if value != self._max_hover:
            self._max_hover = value
            self._on_max_hover(value)

    def handle(self, msg_ptr: int) -> tuple[bool, int]:
        if not self.enabled:
            return False, 0
        msg = wintypes.MSG.from_address(msg_ptr)
        m = msg.message
        hwnd = msg.hWnd
        if m == WM_NCCALCSIZE and msg.wParam:
            # The whole window becomes client area. (Keeping DefWindowProc's invisible side
            # borders makes DWM composite the Direct3D swap chain over an opaque white
            # redirection surface, which defeats Mica.) Resizing is handled in WM_NCHITTEST.
            if _user32.IsZoomed(hwnd):
                params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                fx, fy = _frame_thickness(hwnd)
                rc = params.rgrc[0]
                rc.left += fx
                rc.top += fy
                rc.right -= fx
                rc.bottom -= fy
                edge = _autohide_taskbar_edge()
                if edge is not None:  # leave a sliver so an auto-hidden taskbar can be revealed
                    if edge == 3:
                        rc.bottom -= 2
                    elif edge == 1:
                        rc.top += 2
                    elif edge == 0:
                        rc.left += 2
                    elif edge == 2:
                        rc.right -= 2
            return True, 0
        if m == WM_NCHITTEST:
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            origin = wintypes.POINT(0, 0)
            _user32.ClientToScreen(hwnd, ctypes.byref(origin))
            dpr = self._dpr() or 1.0
            local = QPoint(int((x - origin.x) / dpr), int((y - origin.y) / dpr))
            if not _user32.IsZoomed(hwnd) and self.resizable():
                rect = wintypes.RECT()
                _user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = (rect.right - rect.left) / dpr
                h = (rect.bottom - rect.top) / dpr
                b, c = self.RESIZE_BORDER, self.CORNER
                lx, ly = local.x(), local.y()
                left, right = lx < b, lx >= w - b
                top, bottom = ly < b, ly >= h - b
                near_l, near_r = lx < c, lx >= w - c
                near_t, near_b = ly < c, ly >= h - c
                code = 0
                if (top and near_l) or (left and near_t):
                    code = HTTOPLEFT
                elif (top and near_r) or (right and near_t):
                    code = HTTOPRIGHT
                elif (bottom and near_l) or (left and near_b):
                    code = HTBOTTOMLEFT
                elif (bottom and near_r) or (right and near_b):
                    code = HTBOTTOMRIGHT
                elif top:
                    code = HTTOP
                elif bottom:
                    code = HTBOTTOM
                elif left:
                    code = HTLEFT
                elif right:
                    code = HTRIGHT
                if code:
                    self._set_hover(False)
                    return True, code
            code = self._hit_test(local)
            self._set_hover(code == HTMAXBUTTON)
            if code in (HTCAPTION, HTMAXBUTTON):
                return True, code
            return True, HTCLIENT
        if m == WM_NCACTIVATE:
            # lParam = -1 stops DefWindowProc from painting a classic caption over the client. wParam TRUE
            # keeps the frame, and the material behind the window, in their active look (see above);
            # the result is TRUE either way, so the window is still allowed to lose the focus.
            active = 1 if self.keep_active_look else msg.wParam
            return True, _user32.DefWindowProcW(hwnd, m, active, -1)
        if m == WM_NCMOUSELEAVE:
            self._set_hover(False)
            return False, 0
        if m in (WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK) and msg.wParam == HTMAXBUTTON:
            self._on_max_press(True)
            return True, 0
        if m == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            self._on_max_press(False)
            self._on_max_click()
            return True, 0
        if m in (WM_NCRBUTTONDOWN, WM_NCRBUTTONUP) and msg.wParam == HTCAPTION and self.on_caption_menu:
            if m == WM_NCRBUTTONUP:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self.on_caption_menu)   # never run a menu inside the window procedure
            return True, 0
        if m == WM_SYSCOMMAND and self.on_transition is not None:
            cmd = msg.wParam & 0xFFF0
            if cmd in (SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE):
                if self.passing == cmd:
                    self.passing = None
                    return False, 0
                if self.on_transition(cmd):
                    return True, 0
            return False, 0
        if m in _SYSTEM_CHANGE_MESSAGES and self.on_system_change:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.on_system_change)      # after Qt has handled the message too
        return False, 0


# ---------------------------------------------------------------------------- misc
def set_app_user_model_id(app_id: str) -> None:
    if IS_WINDOWS:
        try:
            _shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
        except Exception:
            pass


def system_accent_color() -> QColor | None:
    if not IS_WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "AccentColor")
        value = int(value) & 0xFFFFFFFF
        r, g, b = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
        return QColor(r, g, b)
    except OSError:
        return None


def system_animations_enabled() -> bool:
    if not IS_WINDOWS:
        return True
    enabled = wintypes.BOOL(True)
    SPI_GETCLIENTAREAANIMATION = 0x1042
    if _user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0):
        return bool(enabled.value)
    return True


def dpapi_protect(data: bytes, entropy: bytes = b"JBrowser") -> bytes:
    if not IS_WINDOWS:
        raise OSError("DPAPI is only available on Windows")
    buf_in = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    ent = ctypes.create_string_buffer(entropy, len(entropy))
    blob_ent = DATA_BLOB(len(entropy), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not _crypt32.CryptProtectData(ctypes.byref(blob_in), "JBrowser", ctypes.byref(blob_ent), None, None,
                                     CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def dpapi_unprotect(data: bytes, entropy: bytes = b"JBrowser") -> bytes:
    if not IS_WINDOWS:
        raise OSError("DPAPI is only available on Windows")
    buf_in = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    ent = ctypes.create_string_buffer(entropy, len(entropy))
    blob_ent = DATA_BLOB(len(entropy), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not _crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None,
                                       0x1, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


# ---------------------------------------------------------------------------- default apps
# The installer registers JBrowser with Windows (installer/JBrowser.iss, "Register JBrowser as a web browser
# and PDF viewer"): links open with the JBrowserURL handler, PDF files with JBrowserPDF. Windows only lets the
# user choose defaults, in Settings → Apps → Default apps; JBrowser reads the choice and links there.
DEFAULT_HANDLERS = {"browser": ("https", "JBrowserURL"), "pdf": (".pdf", "JBrowserPDF")}


def _reg_value(root, path: str, name: str) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return str(value)
    except OSError:
        return None


def registered_with_windows() -> str | None:
    """Where the installer registered JBrowser for "Default apps": "user", "machine", or None."""
    if not IS_WINDOWS:
        return None
    import winreg
    for root, where in ((winreg.HKEY_CURRENT_USER, "user"), (winreg.HKEY_LOCAL_MACHINE, "machine")):
        if _reg_value(root, r"Software\RegisteredApplications", "JBrowser"):
            return where
    return None


def handles_pdf() -> bool:
    """Whether this installation offers JBrowser for PDF files (installed by 2.0.1 or later)."""
    if not IS_WINDOWS:
        return False
    import winreg
    caps = r"Software\Clients\StartMenuInternet\JBrowser\Capabilities\FileAssociations"
    return any(_reg_value(root, caps, ".pdf") for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE))


def default_handler(kind: str) -> str | None:
    """The handler Windows uses for links ("browser") or PDF files ("pdf"), or None if unknown. Newer Windows
    11 builds keep the user's choice in UserChoiceLatest, older ones in UserChoice."""
    if not IS_WINDOWS or kind not in DEFAULT_HANDLERS:
        return None
    import winreg
    what = DEFAULT_HANDLERS[kind][0]
    base = (rf"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{what}" if kind == "browser"
            else rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{what}")
    hkcu = winreg.HKEY_CURRENT_USER
    return (_reg_value(hkcu, base + r"\UserChoiceLatest\ProgId", "ProgId")
            or _reg_value(hkcu, base + r"\UserChoice", "ProgId"))


def is_default(kind: str) -> bool:
    return default_handler(kind) == DEFAULT_HANDLERS[kind][1]


def open_default_apps() -> None:
    """Windows Settings → Default apps, on JBrowser's own page when Windows knows about it."""
    if not IS_WINDOWS:
        return
    where = registered_with_windows()
    uri = "ms-settings:defaultapps"
    if where:
        uri += f"?registeredApp{'User' if where == 'user' else 'Machine'}=JBrowser"
    try:
        os.startfile(uri)  # type: ignore[attr-defined]
    except OSError:
        log.warning("Couldn't open Windows Default apps settings")


def running_as_admin() -> bool:
    """True when this process runs elevated (as administrator)."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def authenticode(path: str) -> tuple[str, str]:
    """The Authenticode signature of a file: (status, signer subject), e.g. ("Valid", "CN=…") or
    ("NotSigned", ""). ("Unknown", "") when it can't be checked. Takes about half a second."""
    if not IS_WINDOWS or not os.path.exists(path):
        return "Unknown", ""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:JB_SIG_PATH; "
              "[string]$s.Status + '|' + [string]$s.SignerCertificate.Subject")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=30, env={**os.environ, "JB_SIG_PATH": path},
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        status, _, subject = out.stdout.strip().partition("|")
        return (status or "Unknown"), subject
    except (OSError, subprocess.SubprocessError):
        return "Unknown", ""


def reveal_in_explorer(path: str) -> None:
    path = os.path.normpath(path)
    if IS_WINDOWS:
        if os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            folder = os.path.dirname(path)
            if os.path.isdir(folder):
                os.startfile(folder)  # type: ignore[attr-defined]
