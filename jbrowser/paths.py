"""Filesystem layout for JBrowser's persistent state."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from jbrowser import APP_NAME


def resource_path(*parts: str) -> str:
    """Absolute path of a bundled read-only resource (``assets/...``), from source or the frozen exe."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class AppPaths:
    """Resolves every on-disk location JBrowser uses.

    Roaming data (settings, session, history, vault) lives under %APPDATA%\\JBrowser.
    Disposable caches live under %LOCALAPPDATA%\\JBrowser\\Cache so they never roam.
    A custom root (``--profile-dir``) keeps everything in one portable folder.
    """

    # Everything JBrowser itself writes into its data folder (used by the portable-mode reset,
    # where the folder may be shared with the user's own files).
    OWNED = ("Profiles", "Logs", "Cache", "JBrowser", "settings.json", "session.json", "history.sqlite3",
             "history.sqlite3-wal", "history.sqlite3-shm", "history.sqlite3-journal", "bookmarks.json",
             "vault.bin", "downloads.json", "userscripts.json", "blocklist.txt", "threats.txt", ".factory-reset",
             "archive.json", "favourites.json")

    def __init__(self, root: str | os.PathLike | None = None):
        self.portable = bool(root)
        if root:
            self.data = Path(root).resolve()
            self.cache = self.data / "Cache"
        else:
            appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            self.data = Path(appdata) / APP_NAME
            self.cache = Path(local) / APP_NAME / "Cache"
        self.profiles = self.data / "Profiles"
        self.profile_cache = self.cache / "Profiles"
        self.favicons = self.cache / "Favicons"
        self.logs = self.data / "Logs"
        self.settings_file = self.data / "settings.json"
        self.session_file = self.data / "session.json"
        self.history_db = self.data / "history.sqlite3"
        self.bookmarks_file = self.data / "bookmarks.json"
        self.vault_file = self.data / "vault.bin"
        self.downloads_file = self.data / "downloads.json"
        self.userscripts_file = self.data / "userscripts.json"
        self.blocklist_file = self.data / "blocklist.txt"
        self.threatlist_file = self.data / "threats.txt"
        self.reset_marker = self.data / ".factory-reset"
        self.archive_file = self.data / "archive.json"
        self.favourites_file = self.data / "favourites.json"

    def ensure(self) -> None:
        for d in (self.data, self.cache, self.profiles, self.profile_cache, self.favicons, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def profile_storage(self, space_id: str) -> Path:
        return self.profiles / space_id

    def profile_cache_dir(self, space_id: str) -> Path:
        return self.profile_cache / space_id

    def wipe_profile(self, space_id: str) -> None:
        for d in (self.profile_storage(space_id), self.profile_cache_dir(space_id)):
            shutil.rmtree(d, ignore_errors=True)

    def clear_profile_cookies_and_cache(self, cookies: bool = True, cache: bool = True) -> None:
        """Delete cookie databases and/or HTTP caches of every space (profiles must not be running)."""
        if cookies and self.profiles.is_dir():
            for prof in self.profiles.iterdir():
                for name in ("Cookies", "Cookies-journal", os.path.join("Network", "Cookies"),
                             os.path.join("Network", "Cookies-journal")):
                    try:
                        (prof / name).unlink()
                    except OSError:
                        pass
        if cache:
            shutil.rmtree(self.profile_cache, ignore_errors=True)
            self.profile_cache.mkdir(parents=True, exist_ok=True)

    def factory_reset(self) -> None:
        """Erase every file JBrowser has written (called at start-up, before anything is opened)."""
        import time

        if self.portable:
            targets = [self.data / name for name in self.OWNED]
            if self.data.is_dir():
                targets += list(self.data.glob("*.tmp"))
        else:
            # %APPDATA%\JBrowser and %LOCALAPPDATA%\JBrowser belong to JBrowser alone.
            targets = [self.data, self.cache.parent]
        for target in targets:
            for _attempt in range(10):   # renderer processes of the old instance may still hold locks
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    try:
                        target.unlink()
                    except OSError:
                        pass
                if not target.exists():
                    break
                time.sleep(0.3)
        try:
            self.reset_marker.unlink()
        except OSError:
            pass
        self.ensure()
