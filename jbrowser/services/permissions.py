"""Human-readable descriptions for web permission types."""
from __future__ import annotations

from PyQt6.QtWebEngineCore import QWebEnginePermission

PT = QWebEnginePermission.PermissionType

PERMISSION_INFO: dict[PT, tuple[str, str, str]] = {
    # type: (short name, "wants to ..." phrase, glyph)
    PT.MediaAudioCapture: ("Microphone", "use your microphone", "mic"),
    PT.MediaVideoCapture: ("Camera", "use your camera", "camera"),
    PT.MediaAudioVideoCapture: ("Camera & microphone", "use your camera and microphone", "camera"),
    PT.DesktopVideoCapture: ("Screen sharing", "share your screen", "tv"),
    PT.DesktopAudioVideoCapture: ("Screen & audio sharing", "share your screen and system audio", "tv"),
    PT.MouseLock: ("Pointer lock", "lock and hide your mouse pointer", "mouse"),
    PT.Notifications: ("Notifications", "show notifications", "ringer"),
    PT.Geolocation: ("Location", "know your location", "mappin"),
    PT.ClipboardReadWrite: ("Clipboard", "read and write your clipboard", "paste"),
    PT.LocalFontsAccess: ("Local fonts", "use fonts installed on this device", "font"),
}

STATE_NAMES = {
    QWebEnginePermission.State.Ask: "Ask",
    QWebEnginePermission.State.Granted: "Allowed",
    QWebEnginePermission.State.Denied: "Blocked",
    QWebEnginePermission.State.Invalid: "Not set",
}


def describe(ptype: PT) -> tuple[str, str, str]:
    return PERMISSION_INFO.get(ptype, ("Device access", "access a device feature", "permissions"))
