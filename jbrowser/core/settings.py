"""Centralised, observable settings store backed by a JSON file."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_json, read_json

SLEEP_PRESETS = {
    # preset id: (label, minutes of inactivity or None when disabled)
    "off": ("Off", None),
    "minimal": ("After 30 minutes", 30),
    "moderate": ("After 20 minutes", 20),
    "maximum": ("After 10 minutes", 10),
}

DEFAULT_SEARCH_KEYWORDS = [
    {"keyword": "g", "name": "Google", "url": "https://www.google.com/search?q={query}"},
    {"keyword": "ddg", "name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
    {"keyword": "yt", "name": "YouTube", "url": "https://www.youtube.com/results?search_query={query}"},
    {"keyword": "w", "name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Special:Search?search={query}"},
    {"keyword": "gh", "name": "GitHub", "url": "https://github.com/search?q={query}"},
    {"keyword": "maps", "name": "Google Maps", "url": "https://www.google.com/maps/search/{query}"},
    {"keyword": "mdn", "name": "MDN Web Docs", "url": "https://developer.mozilla.org/en-US/search?q={query}"},
    {"keyword": "py", "name": "Python Docs", "url": "https://docs.python.org/3/search.html?q={query}"},
    {"keyword": "so", "name": "Stack Overflow", "url": "https://stackoverflow.com/search?q={query}"},
    {"keyword": "pypi", "name": "PyPI", "url": "https://pypi.org/search/?q={query}"},
    {"keyword": "npm", "name": "npm", "url": "https://www.npmjs.com/search?q={query}"},
    {"keyword": "r", "name": "Reddit", "url": "https://www.reddit.com/search/?q={query}"},
]

SETTINGS_VERSION = 2

DEFAULTS: dict[str, Any] = {
    "settings.version": SETTINGS_VERSION,
    # Appearance
    "appearance.theme": "system",            # system | dark | light
    "appearance.material": "acrylic",        # acrylic | mica | mica_alt | solid
    "appearance.use_accent": True,
    "appearance.animations": True,
    "appearance.sidebar_collapsed": False,
    "appearance.favorites_bar": True,
    "appearance.force_dark_web": False,
    "appearance.sounds": True,               # welcome-screen sound effects
    "appearance.tint": "none",               # a colour tint from ui/theme.py TINTS, or "none"
    "sidebar.new_card_always": True,         # "New card" row even when a space has no cards
    "gallery.all_spaces": False,             # the Gallery shows every space, not just the current one
    # Ribbon (title bar)
    "toolbar.home_button": False,
    "toolbar.home_mode": "lazy",             # lazy (open the Lazy Toolbar) | url
    "toolbar.home_url": "",
    # First-run welcome and guided tour (shown again when the version increases)
    "onboarding.version": 0,
    # Automatic updates from GitHub Releases (see services/updater.py)
    "updates.auto_check": True,
    "updates.last_check": 0,
    "updates.skipped": "",                   # a version the user chose to skip
    # Canvas
    "canvas.default_width": 0.5,
    "canvas.show_minimap": True,
    # Startup / window
    "startup.restore_session": True,
    "window.geometry": None,
    "window.maximized": False,
    # Search
    "search.engine": "google",
    "search.suggestions": True,
    "search.keywords": DEFAULT_SEARCH_KEYWORDS,
    "search.recent": [],
    # Privacy
    "privacy.block_trackers": True,
    "privacy.block_third_party_cookies": True,
    "privacy.gpc": True,
    "privacy.dnt": True,
    "privacy.https_upgrade": False,
    "privacy.popup_blocking": True,
    "privacy.webrtc_public_only": True,
    "privacy.block_autoplay": False,
    "privacy.allowlist": [],
    "privacy.blocklist_updated": 0,
    "privacy.blocklist_auto": True,          # weekly background refresh of tracker lists
    "privacy.threat_protection": True,
    "privacy.threatlist_updated": 0,
    "privacy.strip_tracking": True,
    "privacy.fingerprint_protection": True,
    "privacy.clear_on_exit": [],              # any of: history, cookies, cache, downloads
    # Performance
    "performance.sleep_preset": "moderate",
    "performance.throttle": True,
    "performance.never_sleep": [],
    # Network
    "network.dns_mode": "quad9",             # system | quad9 | cloudflare
    "network.dns_fallback": False,
    "network.proxy": {"mode": "direct", "type": "http", "host": "", "port": 8080,
                      "username": "", "password": ""},
    "network.dev_hosts": [
        {"host": "app.test", "target": "127.0.0.1:3000", "enabled": True},
        {"host": "vite.test", "target": "127.0.0.1:5173", "enabled": True},
    ],
    # Passwords
    "passwords.offer_save": True,
    "passwords.autofill": True,
    "passwords.warn_insecure": True,
    # Downloads
    "downloads.directory": "",
    "downloads.ask": False,
    "downloads.protect": True,
    # Advanced
    "advanced.media_notice": False,           # explain videos in formats the engine can't play (H.264, AAC)
    "advanced.gpu_mode": "auto",              # auto | compatible | off  (applied at start-up)
    "advanced.identity": "current",           # current: newest Chrome · engine: the engine's own version
    # Zoom
    "zoom.sites": {},
    # Profiles scheduled for deletion on next start
    "profiles.pending_wipe": [],
}


class Settings(QObject):
    """Key/value settings with change notifications and debounced persistence."""

    changed = pyqtSignal(str, object)

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        stored = read_json(path, {})
        self._values: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.first_run = not isinstance(stored, dict) or not stored
        # Version the stored file came from (0 = brand new install, 1 = before versioning).
        self.migrated_from = SETTINGS_VERSION
        if isinstance(stored, dict) and stored:
            for k, v in stored.items():
                self._values[k] = v
            self.migrated_from = int(stored.get("settings.version", 1))
            self._migrate(self.migrated_from)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_now)

    def _migrate(self, version: int) -> None:
        if version < 2:
            # 1.1 defaults: Acrylic material.
            self._values["appearance.material"] = "acrylic"
        self._values["settings.version"] = SETTINGS_VERSION

    def reset_to_defaults(self) -> None:
        """Restore every preference to its default (keeps window placement and pending wipes)."""
        keep = {"window.geometry", "window.maximized", "profiles.pending_wipe", "settings.version",
                "privacy.blocklist_updated", "privacy.threatlist_updated", "search.recent",
                "onboarding.version", "updates.last_check"}
        for key, value in DEFAULTS.items():
            if key not in keep:
                self.set(key, copy.deepcopy(value))
        for key in [k for k in self._values if k not in DEFAULTS]:
            del self._values[key]
        self.save_now()

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._values:
            return copy.deepcopy(self._values[key])
        if key in DEFAULTS:
            return copy.deepcopy(DEFAULTS[key])
        return default

    def set(self, key: str, value: Any) -> None:
        if self._values.get(key) == value:
            return
        self._values[key] = copy.deepcopy(value)
        self._save_timer.start()
        self.changed.emit(key, copy.deepcopy(value))

    def toggle(self, key: str) -> bool:
        new = not bool(self.get(key))
        self.set(key, new)
        return new

    def save_now(self) -> None:
        self._save_timer.stop()
        atomic_write_json(self._path, self._values)
