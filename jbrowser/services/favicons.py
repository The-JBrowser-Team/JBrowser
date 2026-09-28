"""Persistent favicon cache keyed by host (never written for incognito spaces)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PyQt6.QtCore import QObject, QSize, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap

from jbrowser.core.urls import strip_www


class FaviconCache(QObject):
    updated = pyqtSignal(str)  # host

    def __init__(self, folder: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._folder = folder
        self._mem: dict[str, QIcon] = {}

    @staticmethod
    def _host(url_or_host: str) -> str:
        if "://" in url_or_host:
            return strip_www(QUrl(url_or_host).host())
        return strip_www(url_or_host)

    def _file(self, host: str) -> Path:
        return self._folder / (hashlib.sha1(host.encode("utf-8")).hexdigest()[:20] + ".png")

    def get(self, url_or_host: str) -> QIcon:
        host = self._host(url_or_host)
        if not host:
            return QIcon()
        icon = self._mem.get(host)
        if icon is None:
            f = self._file(host)
            icon = QIcon(str(f)) if f.exists() else QIcon()
            self._mem[host] = icon
        return icon

    def store(self, url: str, icon: QIcon, persist: bool = True) -> None:
        host = self._host(url)
        if not host or icon.isNull():
            return
        self._mem[host] = icon
        if persist:
            pm: QPixmap = icon.pixmap(QSize(32, 32))
            if not pm.isNull():
                pm.save(str(self._file(host)), "PNG")
        self.updated.emit(host)

    def forget(self, host: str) -> None:
        host = strip_www(host)
        for h in [h for h in self._mem if h == host or h.endswith("." + host)]:
            self._mem.pop(h, None)
            try:
                self._file(h).unlink()
            except OSError:
                pass
        try:
            self._file(host).unlink()
        except OSError:
            pass

    def clear(self) -> None:
        self._mem.clear()
        for f in self._folder.glob("*.png"):
            try:
                f.unlink()
            except OSError:
                pass
