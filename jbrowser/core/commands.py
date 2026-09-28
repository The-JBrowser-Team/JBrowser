"""Command registry: single source of truth for actions, shortcuts and the cheat sheet."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)


@dataclass
class Command:
    id: str
    title: str
    category: str
    handler: Callable[[], None]
    shortcuts: list[str] = field(default_factory=list)
    keywords: str = ""
    icon: str = ""
    palette: bool = True                      # listed in the Lazy Toolbar
    state: Callable[[], str | None] | None = None   # e.g. returns "On"/"Off" for toggles
    enabled: Callable[[], bool] | None = None

    def shortcut_text(self) -> str:
        return "  /  ".join(QKeySequence(s).toString(QKeySequence.SequenceFormat.NativeText)
                            for s in self.shortcuts)


class CommandRegistry(QObject):
    executed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._commands: dict[str, Command] = {}
        self._shortcuts: list[QShortcut] = []

    def register(self, cmd: Command) -> Command:
        self._commands[cmd.id] = cmd
        return cmd

    def add(self, id: str, title: str, category: str, handler: Callable[[], None], **kw) -> Command:
        return self.register(Command(id, title, category, handler, **kw))

    def get(self, id: str) -> Command | None:
        return self._commands.get(id)

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def run(self, id: str) -> None:
        cmd = self._commands.get(id)
        if cmd is None:
            log.warning("Unknown command %s", id)
            return
        if cmd.enabled and not cmd.enabled():
            return
        cmd.handler()
        self.executed.emit(id)

    def install_shortcuts(self, window: QWidget) -> None:
        for sc in self._shortcuts:
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()
        for cmd in self._commands.values():
            for seq in cmd.shortcuts:
                sc = QShortcut(QKeySequence(seq), window)
                sc.setContext(Qt.ShortcutContext.WindowShortcut)
                sc.setAutoRepeat(seq.startswith(("Alt+Left", "Alt+Right", "Ctrl+Tab", "Ctrl+Shift+Tab",
                                                 "Ctrl+=", "Ctrl++", "Ctrl+-", "Alt+Up", "Alt+Down")))
                sc.activated.connect(lambda cid=cmd.id: self.run(cid))
                self._shortcuts.append(sc)

    def set_shortcuts_enabled(self, enabled: bool) -> None:
        """Used while a full-window experience (the welcome tour) owns the keyboard."""
        for sc in self._shortcuts:
            sc.setEnabled(enabled)

    def categories(self) -> dict[str, list[Command]]:
        out: dict[str, list[Command]] = {}
        for cmd in self._commands.values():
            out.setdefault(cmd.category, []).append(cmd)
        return out
