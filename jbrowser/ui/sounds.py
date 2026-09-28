"""Short UI sound effects (welcome screen), played with low latency through QSoundEffect.

The WAV files live in ``assets/sounds``. Sound is optional: if Qt Multimedia or an audio
device is unavailable, playback silently does nothing. ``appearance.sounds`` mutes it.
"""
from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, QUrl

from jbrowser.core.settings import Settings
from jbrowser.paths import resource_path

log = logging.getLogger(__name__)

SOUNDS = {"intro": "intro.wav", "click": "click.wav"}


class Sounds(QObject):
    def __init__(self, settings: Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self._effects: dict = {}
        try:
            from PyQt6.QtMultimedia import QSoundEffect
        except ImportError as exc:          # Qt Multimedia missing: stay silent
            log.info("Sound effects unavailable: %s", exc)
            return
        for name, file in SOUNDS.items():
            path = resource_path("assets", "sounds", file)
            if not os.path.exists(path):
                log.info("Sound file missing: %s", path)
                continue
            eff = QSoundEffect(self)
            eff.statusChanged.connect(lambda e=eff, n=name: self._on_status(e, n))
            eff.setSource(QUrl.fromLocalFile(path))
            eff.setVolume(0.85 if name == "intro" else 0.35)
            self._effects[name] = eff

    @staticmethod
    def _on_status(eff, name: str) -> None:
        try:
            status = eff.status()
        except RuntimeError:
            return
        if status == eff.Status.Error:
            log.warning("Sound effect %s could not be loaded", name)
        elif status == eff.Status.Ready:
            log.debug("Sound effect %s ready", name)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("appearance.sounds"))

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        eff = self._effects.get(name)
        if eff is None:
            return
        try:
            if eff.isPlaying():
                eff.stop()
            eff.play()
        except RuntimeError:
            pass

    def stop(self, name: str | None = None) -> None:
        for key, eff in self._effects.items():
            if name is None or key == name:
                try:
                    eff.stop()
                except RuntimeError:
                    pass
