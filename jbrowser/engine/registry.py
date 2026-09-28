"""EngineRegistry: creates/destroys a TabController for every Tab in the state store."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage

from jbrowser.engine.tab_controller import TabController
from jbrowser.models.space import Space
from jbrowser.models.tab import Tab

if TYPE_CHECKING:
    from jbrowser.context import AppContext


class EngineRegistry(QObject):
    controllerCreated = pyqtSignal(object)

    def __init__(self, ctx: "AppContext", parent: QObject | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._controllers: dict[str, TabController] = {}
        # Connected before any UI so controllers exist when views are built.
        ctx.state.tabAdded.connect(self._on_tab_added)
        ctx.state.tabRemoved.connect(self._on_tab_removed)
        ctx.state.spaceRemoved.connect(self._on_space_removed)

    def controller(self, tab_id: str) -> TabController | None:
        return self._controllers.get(tab_id)

    def controllers(self) -> list[TabController]:
        return list(self._controllers.values())

    def tab_for_page(self, page: QWebEnginePage | None) -> str:
        if page is None:
            return ""
        for tid, ctrl in self._controllers.items():
            if ctrl.page is page:
                return tid
        return ""

    def _on_tab_added(self, tab: Tab, _index: int, _activate: bool) -> None:
        space = self.ctx.state.space_of(tab)
        if space is None:
            return
        profile = self.ctx.profiles.profile_for(space)
        ctrl = TabController(self.ctx, tab, space, profile, self)
        self._controllers[tab.id] = ctrl
        self.controllerCreated.emit(ctrl)

    def _on_tab_removed(self, tab: Tab, _space: Space) -> None:
        ctrl = self._controllers.pop(tab.id, None)
        if ctrl is not None:
            # Deferred so the UI can detach its view first (views are deleted before pages).
            QTimer.singleShot(0, ctrl.dispose)

    def _on_space_removed(self, space: Space) -> None:
        QTimer.singleShot(0, lambda s=space: self.ctx.profiles.release(s))

    def history_for(self, tab: Tab) -> bytes | None:
        ctrl = self._controllers.get(tab.id)
        return ctrl.history_bytes() if ctrl else tab.pending_history

    def dispose_all(self) -> None:
        for ctrl in list(self._controllers.values()):
            ctrl.dispose()
        self._controllers.clear()
