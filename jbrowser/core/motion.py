"""Global motion policy: every animation in JBrowser asks this object for its duration.

When "Fluid Animations" is switched off all durations collapse to 0 ms, which makes
every transition instantaneous (for low-spec hardware or reduced-motion preferences).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (QAbstractAnimation, QEasingCurve, QObject, QPropertyAnimation,
                          QVariantAnimation, pyqtSignal)

_instance: "Motion | None" = None


class Motion(QObject):
    changed = pyqtSignal(bool)

    # Canonical durations (ms) used across the UI.
    FAST = 120
    NORMAL = 200
    SLOW = 280

    def __init__(self, enabled: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        global _instance
        self._enabled = enabled
        _instance = self

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self._enabled:
            self._enabled = enabled
            self.changed.emit(enabled)

    def ms(self, duration: int) -> int:
        return duration if self._enabled else 0

    def animate_property(self, target: QObject, prop: bytes, start, end, duration: int = NORMAL,
                         easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
                         on_finished: Callable[[], None] | None = None) -> QPropertyAnimation | None:
        """Animate a Qt property, or jump straight to ``end`` when motion is disabled."""
        d = self.ms(duration)
        if d <= 0:
            target.setProperty(prop.decode(), end)
            if on_finished:
                on_finished()
            return None
        anim = QPropertyAnimation(target, prop, target)
        anim.setDuration(d)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        return anim

    def animate_value(self, parent: QObject, start, end, on_value: Callable[[object], None],
                      duration: int = NORMAL,
                      easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
                      on_finished: Callable[[], None] | None = None) -> QVariantAnimation | None:
        d = self.ms(duration)
        if d <= 0:
            on_value(end)
            if on_finished:
                on_finished()
            return None
        anim = QVariantAnimation(parent)
        anim.setDuration(d)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        anim.valueChanged.connect(on_value)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        return anim


def motion() -> Motion:
    global _instance
    if _instance is None:
        _instance = Motion(True)
    return _instance
