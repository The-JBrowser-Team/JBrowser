---
title: The Gallery
since: 1.5.0
description: The overlay that shows every card of a space, or of all spaces, as an animated, accessible grid.
---

[[new 1.5.0]] The Gallery ([ui/gallery.py](source:jbrowser/ui/gallery.py)) shows every card of the current space, or
of all spaces, as a grid of thumbnails. It opens with **Ctrl+Shift+G** (`gallery.toggle`), the *Gallery* button on
the ribbon (`GalleryButton` in [ui/titlebar.py](source:jbrowser/ui/titlebar.py)), the main menu, or
*Gallery of all spaces* (`gallery.all`).

## Structure

```text
Gallery (QWidget overlay, child of SpaceStack, stays_on_top)
├── header: title, subtitle, filter box (QLineEdit), ScopeToggle "This space | All spaces", close button
├── hint line
└── QScrollArea
    └── GalleryGrid     custom-painted tiles, section headers, drag and keyboard handling
```

- [`Gallery`](api:jbrowser.ui.gallery.Gallery) owns opening, closing, thumbnails and the canvases behind it.
- [`GalleryGrid`](api:jbrowser.ui.gallery.GalleryGrid) is one widget that paints every tile itself. With dozens of
  cards that is far cheaper than a widget per tile, and it keeps hover and pop-in animations smooth.
- [`ScopeToggle`](api:jbrowser.ui.gallery.ScopeToggle) is a two-segment switch with a sliding highlight; its state is
  remembered in `gallery.all_spaces`.

`BrowserController.toggle_gallery(all_spaces=None)` opens or closes it. It does nothing during the welcome, and
closes the Lazy Toolbar first.

## Layout

`rebuild()` collects `Section`s (one per space in *All spaces*, otherwise one) of `Item`s (a card, or the *New card*
tile at the end of each section). `GalleryGrid.relayout()` fits as many columns as possible with tiles between
`MIN_TILE_W` (210 px) and `MAX_TILE_W` (330 px), `GAP` 18 px apart; a tile is a thumbnail (`THUMB_RATIO` 0.62 of its
width) above a footer with favicon, title and host. In *All spaces* each section gets a header with the space's
icon and a gradient in its colour.

## Opening and closing

1. `open_gallery()` takes fresh thumbnails of the visible cards (`capture_visible()`), shows the overlay over the
   `SpaceStack` and **hides the canvases** (below).
2. `_play_intro()` fades the overlay in while tiles **pop in** one after another: each starts `STAGGER_MS` (26 ms)
   after the previous one and takes `POP_MS` (420 ms) with an overshooting ease (`_out_back`), rising and scaling up
   from 82 %.
3. Choosing a card (`_open_card`) activates it on the canvas first, then zooms the chosen tile while the others fade,
   and the overlay disappears to reveal the card already in view.

With *Fluid animations* off, all of this is instant.

### Why the canvases are hidden

The main window is translucent (Acrylic or Mica). Windows composites live web views, which are GPU surfaces, into
the window in a way that bleeds through translucent widgets painted above them, tinting the Gallery with whatever
page is behind it. Hiding the canvases while the Gallery is open avoids that and also stops hidden pages drawing
frames. They are re-hidden after a space switch (the incoming canvas is shown by `SpaceStack`) and shown again on
close. `stays_on_top` makes `SpaceStack._raise_overlays()` keep the Gallery above a newly shown canvas.

## Thumbnails

`thumbnail(tab)` returns, in order of preference:

1. a fresh grab of the card if it was visible when the Gallery opened (`capture_visible`, scaled to 900 px);
2. the card's snapshot, taken when it last left view, went to sleep or its space was switched away (a newer snapshot
   replaces an older picture, tracked by `QPixmap.cacheKey()`);
3. otherwise a placeholder: a gradient in the space's colour with the site's icon and host.

Blank grabs (a page that hasn't painted yet) are discarded with `is_blank()` from
[ui/card.py](source:jbrowser/ui/card.py). Scaled pictures are cached per size.

## Interaction

| Input | Does |
|---|---|
| click a tile | open that card |
| hover | the tile lifts; a close button appears |
| type | filters by title or address (typing goes to the filter box from anywhere) |
| ←, →, ↑, ↓, Home, End | move the focus ring (↑/↓ pick the nearest tile in the next row) |
| Enter or Space | open the focused card (or add a card on a *New card* tile) |
| Delete | close the focused card |
| Menu key or Shift+F10 | the card menu |
| drag a tile (after 8 px) | reorder; in *All spaces*, drop into another section to move the card to that space |
| Esc, the Gallery button, the close button | close |

While dragging near the top or bottom, the grid auto-scrolls. Moving to another space uses
`move_tab_to_space()`, like every other way of moving a card.

## Accessibility

The grid is a focusable widget with an accessible name. Every focus change updates its accessible description to
"*n* of *m*: *title* (pinned, sleeping, playing sound), *host*, *space*" (`_announce` and `_describe`), so screen
readers read the focused card and its state. The focus ring is
drawn in the accent colour, and every action has a keyboard equivalent.

## Painting notes

- Each section header is painted inside `QPainter.save()` / `restore()`: a brush left set by a header would fill the
  outline of every tile drawn after it (the tile border is drawn with `drawPath`).
- Animations stored on the Gallery are stopped with `_stop()`, because `motion()` animations delete themselves when
  they finish and a stale reference raises `RuntimeError`.
