---
title: The sidebar
description: Favourites, spaces, the card list, the header and hiding with peek.
---

The [`Sidebar`](api:jbrowser.ui.sidebar.Sidebar) ([ui/sidebar.py](source:jbrowser/ui/sidebar.py)) is the vertical
column on the left, `EXPANDED_W` (256 px) wide. From top to bottom:

```text
SidebarHeader     logo (opens Settings) · clock · hide button
FavouritesGrid    up to 16 favourites, 4 per row
SpaceSection      one SpaceRow per space, then "New space"
TabListView       the active space's cards, pinned first, then "New card"
tools row         downloads, history, bookmarks, passwords · the Archive
```

## The header

`LogoButton` draws the JBrowser mark and opens Settings. `ClockLabel` is a 12-hour clock that re-aligns itself to
every minute boundary, so it never lags.
<!-- if >= 1.5.0 -->
[[changed 1.5.0]] `SidebarHeader.resizeEvent()` places the clock by hand at the exact centre of the header (between
equal 44 px side areas), so it stays centred whatever the widths of the logo and the hide button.
<!-- endif -->

## Favourites

`FavouritesGrid` shows the sites in `FavouritesService` ([services/favourites.py](source:jbrowser/services/favourites.py))
as icon tiles. A favourite works in every space: clicking it focuses the card that was opened from it in the current
space (`tab.favourite_id`), or opens a new one. Tiles can be dragged to reorder.

## Spaces

Each `SpaceRow` shows the space's icon, colour, name and card count. Click switches space; double-click edits it;
right-click opens the space menu. The `SpaceSection` container is focusable: **↑ / ↓** switch spaces
(Ctrl+Shift+E focuses it).
<!-- if >= 1.5.0 -->
While a card is dragged over a row, the row is highlighted as a drop target (an accent outline), set through
`Sidebar.drop_target_at(global_pos, exclude)`, which the canvas, the card list and the Gallery all use.
<!-- endif -->

## The card list

`TabListView` is a `QListView` over `TabListModel`, painted by `TabDelegate`: favicon, title, sleeping and audio
state, a close button on hover. Pinned cards come first. The last row is **New card**, which opens the Lazy Toolbar.

<!-- if >= 1.5.0 -->
[[new 1.5.0]] `sidebar.new_card_always` (on by default) keeps the *New card* row even in a space with no cards;
turned off, an empty space shows no rows. The list rebuilds when the setting changes.

[[new 1.5.0]] Cards in the list can be **dragged**. After the pointer moves `DRAG_START` (6 px):

- inside the list, a line shows where the card will be inserted (`_drop_row`), and releasing calls
  `BrowserState.move_tab()`;
- over a space row, that space is highlighted and releasing moves the card there.
<!-- endif -->

Ctrl+Click and Shift+Click select several cards, as on the canvas.

## Hiding and peeking

`set_collapsed(True)` (Ctrl+B, the hide button, or *Hide sidebar* in its menu) animates the sidebar's width to 0 and
stores `appearance.sidebar_collapsed`. While hidden, `MainWindow` watches the pointer: resting within `PEEK_EDGE`
(10 px) of the window's left edge for 140 ms calls `peek()`, which floats the sidebar over the canvas; it tucks itself
away when the pointer leaves. The hide button in a peeking sidebar pins it open again.
