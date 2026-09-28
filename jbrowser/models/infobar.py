"""Data describing an in-card info bar (permission prompt, save password, crash, ...)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class InfoAction:
    label: str
    callback: Callable[[], None]
    primary: bool = False


@dataclass
class InfoBarSpec:
    key: str                          # de-duplication key (same key replaces the old bar)
    text: str
    icon: str = "info"                # glyph name
    kind: str = "info"                # info | warning | danger | success
    actions: list[InfoAction] = field(default_factory=list)
    on_dismiss: Callable[[], None] | None = None
    timeout_ms: int = 0               # 0 = sticky
    persist_navigation: bool = False  # keep across page navigations
