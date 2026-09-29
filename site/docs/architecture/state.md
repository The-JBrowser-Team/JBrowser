---
title: Browser state and the update pipeline
nav_title: Browser state
description: BrowserState, Space and Tab, and how thousands of engine events a second reach the widgets once per frame.
---

## One store for everything

[`BrowserState`](api:jbrowser.models.state.BrowserState) ([models/state.py](source:jbrowser/models/state.py)) is
the single source of truth for **spaces, cards, the active space, the active card of each space and the
selection**. It holds plain Python objects and emits Qt signals when they change. It never touches a widget or the
web engine.

| Signal | Emitted when |
|---|---|
| `spaceAdded(space, index)`, `spaceRemoved(space)`, `spaceUpdated(space)`, `spacesReordered()` | spaces are created, deleted, renamed or recoloured, reordered |
| `activeSpaceChanged(space, previous)` | the user switches space |
| `tabAdded(tab, index, activate)`, `tabRemoved(tab, space)`, `tabMoved(tab, old, new)` | cards are opened, closed, reordered |
| `activeTabChanged(space, tab)` | a card gets focus (`tab` is `None` when the space becomes empty) |
| `selectionChanged(space)` | the multi-selection changes (Ctrl+Click, Shift+Click, Ctrl+Shift+A) |
| `tabArchived(dict)` | a card is closed with `remember=True`: the Archive stores it |
| `dirty()` | anything that belongs in the session changed |

Every mutation goes through a `BrowserState` method (`add_tab`, `remove_tab`, `move_tab`, `set_pinned`,
`move_tab_to_space`, `set_active_tab`, `select_tab`, `add_space`, `set_active_space`, …), which keeps the invariants
in one place: pinned cards stay at the start of their space, the selection never contains closed cards, closing the
active card focuses its neighbour.

!!! note "Moving a card to another space re-creates it"
    Each space has its own Chromium profile, and a page cannot move between profiles. `move_tab_to_space()` removes
    the card (without archiving it) and adds a new one with the same address, title and width to the target space.

### `Space`

[`Space`](api:jbrowser.models.space.Space) is a dataclass: `id`, `name`, `icon` (an emoji), `color`, `incognito`,
an optional per-space `proxy`, the ordered `tabs` list, `active_tab_id`, the `selected` set and the canvas `scroll`
position. `SPACE_COLORS` and `SPACE_ICONS` are the choices the space editor offers.

### `Tab`

[`Tab`](api:jbrowser.models.tab.Tab) is the pure state of one card: `url`, `title`, `icon`, `loading`, `progress`,
`can_back`/`can_forward`, `audible`/`muted`, `sleeping`, `throttled`, `crashed`, `width` (a fraction of the
canvas), `zoom`, `blocked` (requests blocked on this page), `pinned`, `devtools`, `secure` and more.

Write to a `Tab` only through `tab.update(**fields)`. It compares each field, and only real changes are passed on.

## The coalescing update pipeline

A loading page fires title, icon, progress and URL signals many times a second, for cards the user may not even see.
Pushing each one into widgets would repaint the sidebar, the canvas and the title bar dozens of times per frame.

Instead, [`TabUpdatePipeline`](api:jbrowser.models.tab.TabUpdatePipeline) batches them:

```text
TabController ──tab.update(title=…)──► Tab ──mark(tab, {"title"})──► TabUpdatePipeline
                                                                        │ (16 ms timer, once per frame)
                                                                        ▼
                                          tab.changed(frozenset(fields)) + flushed({tab_id: fields})
```

1. `Tab.update()` records the changed field names with `pipeline().mark()`.
2. The pipeline starts a 16 ms single-shot timer if it isn't running, and merges further changes into the same batch.
3. `flush()` emits each tab's `changed(fields)` once, then `flushed(summary)` for everyone who cares about many tabs
   (the session only schedules a save when a session field such as `url`, `title` or `width` changed).

Views connect to `tab.changed` and decide what to do with the field set. A card that is off screen, or in a hidden
space, only remembers that it is stale, and repaints when it becomes visible.

## Who listens to what

| Listener | Signals | Does |
|---|---|---|
| `EngineRegistry` | `tabAdded`, `tabRemoved`, `spaceRemoved` | creates and disposes `TabController`s and profiles |
| `SpaceStack` / `Canvas` | space and tab signals | one canvas per space, one `WebCard` per tab |
| `Sidebar` | space, tab, selection signals | the space rows and the card list |
| `TitleBar` | `activeTabChanged`, `tab.changed` | the address pill, security state, buttons |
| `SessionManager` | `dirty`, `pipeline.flushed` | saves `session.json` (2.5 s debounce, 15 s autosave) |
| `ArchiveService` | `tabArchived`, `spaceRemoved` | keeps closed cards for 48 hours |
| `AppContext` | `activeSpaceChanged`, `spaceUpdated` | applies the space's proxy |
