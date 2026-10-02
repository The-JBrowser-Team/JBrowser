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

<!-- if >= 2.0.0 -->
## Columns: stacked cards

[[new 2.0.0]] Up to `MAX_STACK` (3) cards can stack in one **column** ([models/state.py](source:jbrowser/models/state.py)):

- Cards in a column share a `tab.stack` id and sit next to each other in `space.tabs`. `BrowserState.columns(space)`
  groups contiguous cards with the same id; `column_of()`, `can_stack_onto()`, `stack_tab(tab, onto, above)` and
  `unstack()` work on them, and `normalize_stacks()` repairs a space after a card is closed or moved (a column of one
  is no column; extra cards past the limit leave it).
- Cards in a column always have the same width: `_sync_column_widths()` (on every pipeline flush) gives the whole
  column the width of the card that changed. New cards land outside columns (`_outside_columns()`), never between two
  stacked cards; `add_tab(stack_onto=...)` puts a new card just below a given one.
- The session saves `stack` with each card and restores the columns.
- `targets()` lays the canvas out by columns: each entry is `(x, width, top, height)`, with `top` and `height` as
  fractions of the canvas height, so the cards of a column split it evenly.
- **Dragging:** the lower 45 % of a card (or its top 20 %) under the pointer opens a drop slot, a dashed accent
  outline where the card will go (`_stack_target_at()`, with hysteresis over the slot); letting go there calls
  `stack_tab()`. A dragged card first leaves its own column, and columns reorder as a whole
  (`_reorder_by_columns()`).
- **The stack picker** ([ui/stack_picker.py](source:jbrowser/ui/stack_picker.py)) opens in a slot below the current
  card (the ribbon's stack button, Alt+Shift+S, or the card menu): a new page (search or address, with history
  matches), an open card of the space, a favourite or a bookmark. Choosing one hands the slot's place to the new card,
  which grows out of it. Its footer sets the column's width and opens the layout menu (split views, widths, focus
  view), which is also the stack button's right-click menu.

<!-- endif -->
## Scrolling and panning

`scroll_to()`, `scroll_by()` and `ensure_visible(tab_id, align)` move the offset, animated with `motion()`. The
canvas takes horizontal wheel and trackpad input directly, and `MainWindow` routes **Alt + wheel** from anywhere over
the canvas to `pan_from_wheel()`. The **overview strip** (`Minimap`) at the bottom draws every card as a segment and
the viewport as a window; clicking or dragging it scrolls.
<!-- if >= 1.6.0 -->

[[changed 1.6.0]] **Scrolling at frame rate.** Wheel and trackpad input (`scroll_by()`) only moves the target
offset; a timer ticking twice per screen refresh (`_smooth_step()`) moves the canvas towards it, once per tick:

- mouse-wheel notches ease by time (`SMOOTH_TAU`, 55 ms: 95 % of the way in about 0.17 s), so a new notch continues
  the motion instead of restarting an animation, and a slower PC takes bigger steps instead of falling behind;
- trackpad deltas are followed exactly, but however many arrive between two ticks, the canvas lays out once.

`scroll_to()` (keyboard, minimap, `ensure_visible`) keeps its eased animation and stops the smoother.
<!-- endif -->
<!-- if >= 1.6.1 -->

[[changed 1.6.1]] **Only sideways input moves the canvas.** A page passes the rest of a wheel or touchpad scroll on
to its parent when it reaches its top or bottom, and the canvas used to turn that vertical rest into sideways
movement, sliding to the next card. `horizontal_delta()` now takes only input that is mostly sideways (`|x| > |y|`,
so a vertical swipe with a little wobble doesn't count), or the wheel with Shift held (Windows' usual horizontal
scroll); everything else is ignored. **Alt + wheel** (`pan_from_wheel()`, routed by `MainWindow`) still pans with the
vertical wheel on purpose.
<!-- endif -->
<!-- if >= 1.6.0 -->

Two painting changes halve the work of each frame on large or high-DPI screens:

- **Card shadows** come from a small nine-slice image (`_shadow_tile()`, cached per colour and pixel ratio) instead
  of three large anti-aliased shapes per card; only the edges are drawn, since the card covers the middle.
- **The canvas paints every pixel** (`WA_OpaquePaintEvent`) with one colour, `_background()`: the window's tint wash
  with the canvas tint over it, worked out once. Qt then skips repainting the window underneath on every frame.
<!-- endif -->

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
  another space, copy clean link, save image, inspect…).<!-- if >= 1.6.0 --> [[changed 1.6.0]] Back, Forward, Reload and Stop are left out (every card has them in its header), and the standard items get JBrowser's own glyphs instead of Qt's icons.<!-- endif -->
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
