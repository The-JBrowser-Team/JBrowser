"""BrowserState: the single, centralised store of spaces, cards, focus and selection.

Every UI surface (sidebar, canvases, title bar, Lazy Toolbar) and every engine service
observes this object through signals; none of them talk to each other directly.
"""
from __future__ import annotations

import uuid

from PyQt6.QtCore import QObject, pyqtSignal

from jbrowser.models.space import SPACE_COLORS, Space
from jbrowser.models.tab import Tab, pipeline

MAX_STACK = 3          # cards one above the other in a column


class BrowserState(QObject):
    spaceAdded = pyqtSignal(object, int)            # Space, index
    spaceRemoved = pyqtSignal(object)               # Space
    spaceUpdated = pyqtSignal(object)               # Space
    spacesReordered = pyqtSignal()
    activeSpaceChanged = pyqtSignal(object, object)  # new Space, previous Space | None
    tabAdded = pyqtSignal(object, int, bool)        # Tab, index, activate
    tabRemoved = pyqtSignal(object, object)         # Tab, Space
    tabMoved = pyqtSignal(object, int, int)         # Tab, old index, new index
    activeTabChanged = pyqtSignal(object, object)   # Space, Tab | None
    selectionChanged = pyqtSignal(object)           # Space
    tabArchived = pyqtSignal(dict)                  # a closed card worth remembering (for the Archive)
    dirty = pyqtSignal()                            # session-relevant change

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.spaces: list[Space] = []
        self._tabs: dict[str, Tab] = {}
        self.active_space_id = ""
        pipeline().flushed.connect(self._sync_column_widths)

    # ----------------------------------------------------------------- queries
    def space(self, space_id: str) -> Space | None:
        for s in self.spaces:
            if s.id == space_id:
                return s
        return None

    @property
    def active_space(self) -> Space | None:
        return self.space(self.active_space_id) or (self.spaces[0] if self.spaces else None)

    @property
    def active_tab(self) -> Tab | None:
        sp = self.active_space
        return sp.active_tab() if sp else None

    def tab(self, tab_id: str) -> Tab | None:
        return self._tabs.get(tab_id)

    def space_of(self, tab: Tab | str) -> Space | None:
        t = self._tabs.get(tab) if isinstance(tab, str) else tab
        return self.space(t.space_id) if t else None

    def all_tabs(self) -> list[Tab]:
        return [t for s in self.spaces for t in s.tabs]

    @staticmethod
    def pinned_count(space: Space) -> int:
        n = 0
        for t in space.tabs:
            if not t.pinned:
                break
            n += 1
        return n

    def selected_tabs(self, space: Space | None = None) -> list[Tab]:
        space = space or self.active_space
        if not space:
            return []
        chosen = [t for t in space.tabs if t.id in space.selected]
        if not chosen:
            act = space.active_tab()
            return [act] if act else []
        return chosen

    # ----------------------------------------------------------------- spaces
    def add_space(self, name: str, icon: str = "🏠", color: str | None = None, incognito: bool = False,
                  index: int | None = None, activate: bool = True, space_id: str | None = None,
                  proxy: dict | None = None) -> Space:
        color = color or SPACE_COLORS[len(self.spaces) % len(SPACE_COLORS)]
        space = Space(name=name, icon=icon, color=color, incognito=incognito, proxy=proxy)
        if space_id:
            space.id = space_id
        idx = len(self.spaces) if index is None else max(0, min(index, len(self.spaces)))
        self.spaces.insert(idx, space)
        self.spaceAdded.emit(space, idx)
        if activate or len(self.spaces) == 1:
            self.set_active_space(space.id)
        self.dirty.emit()
        return space

    def remove_space(self, space_id: str) -> None:
        space = self.space(space_id)
        if not space:
            return
        for tab in list(space.tabs):
            self.remove_tab(tab.id, remember=not space.incognito)
        idx = self.spaces.index(space)
        was_active = space.id == self.active_space_id
        self.spaces.remove(space)
        self.spaceRemoved.emit(space)
        if was_active:
            self.active_space_id = ""
            if self.spaces:
                self.set_active_space(self.spaces[min(idx, len(self.spaces) - 1)].id)
        self.dirty.emit()

    def update_space(self, space_id: str, **fields) -> None:
        space = self.space(space_id)
        if not space:
            return
        for k, v in fields.items():
            setattr(space, k, v)
        self.spaceUpdated.emit(space)
        self.dirty.emit()

    def move_space(self, space_id: str, new_index: int) -> None:
        space = self.space(space_id)
        if not space:
            return
        self.spaces.remove(space)
        self.spaces.insert(max(0, min(new_index, len(self.spaces))), space)
        self.spacesReordered.emit()
        self.dirty.emit()

    def set_active_space(self, space_id: str) -> None:
        space = self.space(space_id)
        if not space or space_id == self.active_space_id:
            return
        previous = self.space(self.active_space_id)
        self.active_space_id = space_id
        self.activeSpaceChanged.emit(space, previous)
        act = space.active_tab()
        if act:
            act.touch()
        self.dirty.emit()

    def cycle_space(self, delta: int) -> None:
        if not self.spaces:
            return
        cur = self.active_space
        idx = self.spaces.index(cur) if cur in self.spaces else 0
        self.set_active_space(self.spaces[(idx + delta) % len(self.spaces)].id)

    # ------------------------------------------------------------------- tabs
    def add_tab(self, space_id: str, url: str = "", *, index: int | None = None, activate: bool = True,
                width: float | None = None, title: str = "", tab_id: str | None = None,
                sleeping: bool = False, history: bytes | None = None, zoom: float = 1.0,
                muted: bool = False, pinned: bool = False, favourite_id: str = "", stack: str = "",
                stack_onto: str = "") -> Tab | None:
        """Add a card. ``stack`` restores a saved column; ``stack_onto`` puts the new card just below that
        card, in its column (when there is room)."""
        space = self.space(space_id)
        if not space:
            return None
        onto = self._tabs.get(stack_onto) if stack_onto else None
        if onto is not None and (onto.space_id != space.id or onto.pinned or pinned
                                 or len(self.column_of(onto)) >= MAX_STACK):
            onto = None
        if onto is not None:
            if not onto.stack:
                onto.update(stack=self._new_stack_id())
            stack, width, index = onto.stack, onto.width, space.index_of(onto.id) + 1
        tab = Tab(space.id, url=url, title=title, width=width if width else 0.5, tab_id=tab_id, parent=self)
        tab.sleeping = sleeping
        tab.pending_history = history
        tab.zoom = zoom
        tab.muted = muted
        tab.pinned = pinned
        tab.favourite_id = favourite_id
        tab.stack = stack
        if index is None:
            act = space.index_of(space.active_tab_id)
            index = act + 1 if act >= 0 else len(space.tabs)
        index = max(0, min(index, len(space.tabs)))
        if not stack:
            index = self._outside_columns(space, index)
        # Pinned cards always form a block at the start of the space.
        pins = self.pinned_count(space)
        index = min(index, pins) if pinned else max(index, pins)
        space.tabs.insert(index, tab)
        self._tabs[tab.id] = tab
        self.tabAdded.emit(tab, index, activate)
        if activate or not space.active_tab_id:
            self.set_active_tab(tab.id)
        self.dirty.emit()
        return tab

    def remove_tab(self, tab_id: str, remember: bool = True, history: bytes | None = None) -> None:
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space:
            return
        idx = space.index_of(tab_id)
        if remember and not space.incognito and tab.url and not tab.url.startswith(("about:", "data:")):
            self.tabArchived.emit({"space_id": space.id, "space_name": space.name, "space_icon": space.icon,
                                   "url": tab.url, "title": tab.title, "index": idx, "width": tab.width,
                                   "pinned": tab.pinned, "history": history})
        space.tabs.pop(idx)
        del self._tabs[tab_id]
        space.selected.discard(tab_id)
        was_active = space.active_tab_id == tab_id
        if was_active:
            space.active_tab_id = ""
        tab.disposed = True
        self.normalize_stacks(space)
        self.tabRemoved.emit(tab, space)
        if was_active and space.tabs:
            self.set_active_tab(space.tabs[min(idx, len(space.tabs) - 1)].id)
        elif was_active:
            self.activeTabChanged.emit(space, None)
        self.selectionChanged.emit(space)
        tab.deleteLater()
        self.dirty.emit()

    def move_tab(self, tab_id: str, new_index: int) -> None:
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space:
            return
        old = space.index_of(tab_id)
        pins = self.pinned_count(space)
        if tab.pinned:
            new_index = max(0, min(new_index, pins - 1))
        else:
            new_index = max(pins, min(new_index, len(space.tabs) - 1))
        if old == new_index:
            return
        space.tabs.pop(old)
        space.tabs.insert(new_index, tab)
        self.normalize_stacks(space)       # a card moved out of its column leaves the stack
        self.tabMoved.emit(tab, old, new_index)
        self.dirty.emit()

    def set_pinned(self, tab_id: str, pinned: bool) -> None:
        """Pin (move to the end of the pinned block) or unpin (move just after it)."""
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space or tab.pinned == pinned:
            return
        if tab.stack:
            self.unstack(tab_id)            # pinned cards don't stack
        old = space.index_of(tab_id)
        space.tabs.pop(old)
        tab.pinned = pinned
        new = self.pinned_count(space)          # end of the pinned block / first unpinned slot
        space.tabs.insert(new, tab)
        tab.update(pinned=pinned)
        self.tabMoved.emit(tab, old, new)
        self.dirty.emit()

    def move_tab_to_space(self, tab_id: str, space_id: str) -> Tab | None:
        """Cards cannot share engine state across spaces, so moving re-creates the card."""
        tab = self._tabs.get(tab_id)
        target = self.space(space_id)
        if not tab or not target or tab.space_id == space_id:
            return None
        url, title, width = tab.url, tab.title, tab.width
        self.remove_tab(tab_id, remember=False)
        return self.add_tab(space_id, url, title=title, width=width, index=len(target.tabs), activate=False)

    def set_active_tab(self, tab_id: str, collapse_selection: bool = True) -> None:
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space:
            return
        changed = space.active_tab_id != tab_id
        space.active_tab_id = tab_id
        tab.touch()
        if collapse_selection and space.selected != {tab_id}:
            space.selected = {tab_id}
            space.anchor_tab_id = tab_id
            self.selectionChanged.emit(space)
        if changed:
            self.activeTabChanged.emit(space, tab)
            self.dirty.emit()

    def select_tab(self, tab_id: str, mode: str = "single") -> None:
        """mode: ``single`` | ``toggle`` (Ctrl+Click) | ``range`` (Shift+Click)."""
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space:
            return
        if mode == "toggle":
            if not space.selected and space.active_tab_id:
                space.selected = {space.active_tab_id}
            if tab_id in space.selected and len(space.selected) > 1:
                space.selected.discard(tab_id)
                if space.active_tab_id == tab_id:
                    first = next(t for t in space.tabs if t.id in space.selected)
                    self.set_active_tab(first.id, collapse_selection=False)
            else:
                space.selected.add(tab_id)
                self.set_active_tab(tab_id, collapse_selection=False)
            space.anchor_tab_id = tab_id
        elif mode == "range":
            anchor = space.anchor_tab_id or space.active_tab_id or tab_id
            a, b = space.index_of(anchor), space.index_of(tab_id)
            if a < 0:
                a = b
            lo, hi = min(a, b), max(a, b)
            space.selected = {t.id for t in space.tabs[lo:hi + 1]}
            self.set_active_tab(tab_id, collapse_selection=False)
        else:
            space.selected = {tab_id}
            space.anchor_tab_id = tab_id
            self.set_active_tab(tab_id, collapse_selection=False)
        self.selectionChanged.emit(space)

    def select_all(self, space: Space | None = None) -> None:
        space = space or self.active_space
        if space:
            space.selected = {t.id for t in space.tabs}
            self.selectionChanged.emit(space)

    # ----------------------------------------------------------------- stacks
    # Up to MAX_STACK neighbouring cards can share a column, one above the other: they carry the same
    # Tab.stack id and sit next to each other in space.tabs (top to bottom). A column has one width.
    @staticmethod
    def _new_stack_id() -> str:
        return uuid.uuid4().hex[:8]

    def columns(self, space: Space) -> list[list[Tab]]:
        """The space's cards grouped into columns, left to right (a single card is a column of one)."""
        cols: list[list[Tab]] = []
        for t in space.tabs:
            if t.stack and cols and cols[-1][0].stack == t.stack:
                cols[-1].append(t)
            else:
                cols.append([t])
        return cols

    def column_of(self, tab: Tab | str) -> list[Tab]:
        t = self._tabs.get(tab) if isinstance(tab, str) else tab
        space = self.space_of(t) if t else None
        if not t or not space:
            return []
        if not t.stack:
            return [t]
        return next((c for c in self.columns(space) if t in c), [t])

    def can_stack_onto(self, tab_id: str) -> bool:
        t = self._tabs.get(tab_id)
        return bool(t) and not t.pinned and len(self.column_of(t)) < MAX_STACK

    @staticmethod
    def _outside_columns(space: Space, index: int) -> int:
        """Move an insertion point that falls between two cards of a column to just after the column."""
        while 0 < index < len(space.tabs) and space.tabs[index - 1].stack \
                and space.tabs[index - 1].stack == space.tabs[index].stack:
            index += 1
        return index

    def stack_tab(self, tab_id: str, onto_id: str, above: bool = False) -> bool:
        """Put a card into another card's column, just below it (or above it). Returns False when the
        column is full or either card is pinned."""
        tab, onto = self._tabs.get(tab_id), self._tabs.get(onto_id)
        space = self.space_of(onto) if onto else None
        if not tab or not onto or tab is onto or not space or tab.space_id != onto.space_id \
                or tab.pinned or onto.pinned:
            return False
        column = [t for t in self.column_of(onto) if t is not tab]
        if len(column) >= MAX_STACK:
            return False
        if tab.stack and tab.stack != onto.stack:
            self.unstack(tab_id)
        sid = onto.stack or self._new_stack_id()
        old = space.index_of(tab_id)
        space.tabs.pop(old)
        new = space.index_of(onto_id) + (0 if above else 1)
        space.tabs.insert(new, tab)
        for t in column:
            t.update(stack=sid)
        tab.update(stack=sid, width=onto.width)
        self.normalize_stacks(space)
        self.tabMoved.emit(tab, old, new)
        self.dirty.emit()
        return True

    def unstack(self, tab_id: str) -> None:
        """Take a card out of its column; it becomes a column of its own just to the right."""
        tab = self._tabs.get(tab_id)
        space = self.space_of(tab) if tab else None
        if not tab or not space or not tab.stack:
            return
        column = self.column_of(tab)
        old = space.index_of(tab_id)
        space.tabs.pop(old)
        rest = [t for t in column if t is not tab]
        new = space.index_of(rest[-1].id) + 1 if rest else old
        space.tabs.insert(new, tab)
        tab.update(stack="")
        self.normalize_stacks(space)
        self.tabMoved.emit(tab, old, new)
        self.dirty.emit()

    def normalize_stacks(self, space: Space) -> None:
        """Keep columns tidy after cards move or close: a stack id only counts for its first run of
        neighbouring cards, a column of one is no stack, and a column holds at most MAX_STACK cards."""
        runs: list[tuple[str, list[Tab]]] = []
        for t in space.tabs:
            if t.stack and runs and runs[-1][0] == t.stack:
                runs[-1][1].append(t)
            else:
                runs.append((t.stack, [t]))
        used: set[str] = set()
        for sid, members in runs:
            if not sid:
                continue
            if sid in used or len(members) < 2:
                for m in members:
                    m.update(stack="")
                continue
            used.add(sid)
            for m in members[MAX_STACK:]:
                m.update(stack="")

    def _sync_column_widths(self, summary: dict) -> None:
        """A column has one width: when a card's width changes, its column follows (the first card to
        change in a frame wins)."""
        done: set[str] = set()
        for tab_id, fields in summary.items():
            if "width" not in fields:
                continue
            tab = self._tabs.get(tab_id)
            if tab is None or not tab.stack or tab.stack in done:
                continue
            done.add(tab.stack)
            for t in self.column_of(tab):
                if t is not tab and abs(t.width - tab.width) > 1e-4:
                    t.update(width=tab.width)

