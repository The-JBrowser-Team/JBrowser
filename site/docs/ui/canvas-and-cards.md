---
title: The canvas and cards
nav_title: Canvas and cards
description: How cards are laid out, scrolled, resized, dragged and shown asleep, and how the canvas reports visibility.
---

## `SpaceStack` and `Canvas`

[`SpaceStack`](api:jbrowser.ui.canvas.SpaceStack) ([ui/canvas.py](source:jbrowser/ui/canvas.py)) holds **one
`Canvas` per space** and slides vertically between them when the active space changes (instantly with *Fluid
animations* off). Only the active space's canvas is shown; hidden canvases report all their cards as out of view,
so their pages throttle.

A [`Canvas`](api:jbrowser.ui.canvas.Canvas) lays its space's cards out **left to right** and scrolls horizontally.
It is not a `QScrollArea`: it keeps an `offset` and positions each `WebCard` itself, which is what makes the smooth
animated layout possible.

## Layout

- A card's width is a fraction of the canvas (`tab.width`, 0.1 to 1.0). `px_width()` turns it into pixels so that
  two 50 % cards, three 33 % cards or four 25 % cards exactly fill the view, gaps included (`MARGIN` and `GAP` are
  12 px), with a minimum of `MIN_CARD_W` (120 px).
- `targets()` computes every card's `(x, width)` in content coordinates; `_geo` holds the current, animated values.
- `request_layout(animated=True)` animates `_geo` towards the targets over `LAYOUT_MS` (230 ms). Changes are batched
  with `schedule_layout()`, so ten width changes cause one layout.
- New cards grow in from their centre; removed cards close the gap.

Width presets (Alt+1 … Alt+9, Alt+0), splits (50/50, 33×3, 25×4) and *toggle full width* only change `tab.width`
on the selected cards; the layout follows.

## Scrolling and panning

`scroll_to()`, `scroll_by()` and `ensure_visible(tab_id, align)` move the offset, animated with `motion()`. The
canvas takes horizontal wheel and trackpad input directly, and `MainWindow` routes **Alt + wheel** from anywhere over
the canvas to `pan_from_wheel()`. The **overview strip** (`Minimap`) at the bottom draws every card as a segment and
the viewport as a window; clicking or dragging it scrolls.

## Pull to add a card

Scrolling past either end builds up a "pull" (`PULL_DIST`, 440 px of wheel travel). The cards slide aside by up to
`REVEAL` (88 px), an `EdgePullIndicator` "+" grows in the gap with a ring that fills, and when the ring is full a new
card opens at that end (the Lazy Toolbar opens with the insert position). From the keyboard, **Alt+←** on the first
card or **Alt+→** on the last one shows the "+" (`edge_nudge`), and pressing it again adds the card.

## Visibility and the lifecycle

After every layout or scroll, `_update_visibility()` works out which cards intersect the viewport and reports each
change to `ctx.lifecycle.set_in_view(tab_id, visible, render_visible)`. That is what drives
[throttling and the memory saver](../engine/lifecycle.md), and what makes a lazily restored card load the moment
it appears. A card also knows `on_screen`, so an off-screen card only marks itself stale when its `Tab` changes.

## Dragging cards

<!-- if >= 1.5.0 -->
[[changed 1.5.0]] A card can be dragged by its header (the "ribbon"), or with **Alt** held anywhere on it
(`MainWindow.eventFilter` routes the mouse to the canvas, so the page never sees the click):

1. The card **lifts** (`DRAG_LIFT`, 6 px, with a stronger shadow) and follows the pointer; `_drag_grab` keeps the
   point you grabbed under the pointer.
2. When the card's centre passes a neighbour's midpoint, `BrowserState.move_tab()` reorders the space, and the other
   cards slide aside to show where it will land.
3. Near the canvas edges (48 px) the canvas scrolls, so a card can travel the whole space.
4. Over a **space in the sidebar**, `Sidebar.drop_target_at()` highlights that space; letting go there calls
   `move_tab_to_space()` ([moving re-creates the card](../architecture/state.md)).
5. Otherwise the card settles into its slot from where it was dropped.

The sidebar's card list supports dragging too ([the sidebar](sidebar.md#the-card-list)).
<!-- else -->
Dragging a card's header reorders it: when the card passes a neighbour's midpoint, `BrowserState.move_tab()` moves
it, and the layout animates. (Lifting, dragging to other spaces and Alt + drag came in 1.5.0.)
<!-- endif -->

Double-clicking a header toggles full width; middle-clicking closes the card; right-clicking opens the card menu.

## `WebCard`

A [`WebCard`](api:jbrowser.ui.card.WebCard) ([ui/card.py](source:jbrowser/ui/card.py)) is one card:

```text
WebCard
├── CardHeader        favicon, title, security, blocked count, buttons (compact when the card is narrow)
├── QStackedWidget
│   ├── QSplitter     BrowserView (the QWebEngineView) and, when open, docked DevTools
│   └── SnapshotView  shown while the card sleeps
├── info bars         from TabController.infobar
├── FindBar           Ctrl+F
└── StatusBubble      the hovered link's address
```

- `apply(fields)` updates the header and state from the `Tab`'s changed fields.
- `BrowserView` builds JBrowser's context menu on top of Chromium's standard actions (open link in a new card or
  another space, copy clean link, save image, inspect…).
- `take_snapshot()` grabs the view as a picture while it still renders (before throttling and sleep);
  `enter_sleep()` shows it faded with a moon badge.
<!-- if >= 1.5.0 -->
- A blank grab (a page that hasn't painted yet) is discarded by `is_blank()`, and the sleeping card shows its title
  instead of a white rectangle.
<!-- endif -->
- `teardown()` detaches the view from the page before deletion: Qt WebEngine requires views to go before pages.

## Immersive full screen

When a page requests HTML5 full screen (a video), `set_solo(tab_id)` makes that card fill the canvas and the window
hides its chrome; Escape or the page's own button restores it.
