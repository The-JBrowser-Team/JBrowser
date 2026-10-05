---
title: Theming, materials and colour tints
nav_title: Theming
description: Dark and light palettes, window materials, colour tints and the incognito look.
---

[`Theme`](api:jbrowser.ui.theme.Theme) ([ui/theme.py](source:jbrowser/ui/theme.py)) turns a few settings into a
palette of named colour **tokens** that every widget paints with. There is one instance, returned by `theme()`.

## Tokens

`DARK` and `LIGHT` map token names to colours, many of them translucent so the backdrop shows through:

| Token | Used for |
|---|---|
| `window`, `sidebar`, `canvas`, `card`, `panel`, `dialog`, `layer` | surfaces (translucent) |
| `*_solid` (`sidebar_solid`, `card_solid`, …) | the same surfaces when the material is *Solid* |
| `text`, `text2`, `text3` | primary, secondary and tertiary text |
| `hover`, `pressed`, `selected`, `card_hover` | interaction states |
| `divider`, `card_border`, `input`, `input_border`, `focus_ring`, `shadow`, `scrim` | lines and effects |
| `danger`, `warning`, `success`, `sleep` | status colours |
| `window_tint` | the wash painted over the backdrop |
<!-- if >= 2.0.3 -->
| `frost_tint` | the dark or light veil over the wallpaper in the Frosted picture |
<!-- endif -->
| `accent` | the Windows accent colour (or JBrowser blue), adjusted for contrast |

```python
th = theme()
p.fillPath(path, th.surface("card"))      # the *_solid variant when the material is Solid
p.setPen(th.c("text2"))
p.setBrush(th.accent_alpha(0.16))
```

`theme().changed` fires after every recalculation; widgets repaint on it. `Theme.apply()` also sets the
application palette and a small style sheet for standard Qt widgets (scroll bars, menus, inputs).
<!-- if >= 2.0.3 -->
[[changed 2.0.3]] Setting the application style sheet makes Qt re-polish every widget of the app, which took a third
of a second with Settings open. So `apply()` only sets it when its text changed, and the style sheet is built from
the colours *without* the colour tint (`_qss_tokens`). Picking a tint, or switching between Frosted and Solid, then
never restyles the app. Widgets that should carry the tint paint it themselves (`JDialog.paintEvent()` fills
`dialog_solid`).
<!-- endif -->

## What decides the colours

`refresh()` runs at start-up, when the Windows colour scheme changes, and when one of `appearance.theme`,
`appearance.use_accent`, `appearance.material`<!-- if >= 1.5.0 -->, `appearance.tint`<!-- endif --> changes:

1. **Dark or light**: `appearance.theme` (`system`, `dark`, `light`); `system` follows Windows.<!-- if >= 1.5.0 --> An incognito space forces dark.<!-- endif -->
2. **Accent**: the Windows accent colour (`appearance.use_accent`), lightened on dark or darkened on light when it
   would lack contrast.
<!-- if >= 2.0.3 -->
3. **Material**: `appearance.material` = `frosted` (default) or `solid`. With *Frosted*, `theme().translucent` is
   `True`: `paint_backdrop()` paints JBrowser's frosted picture of the wallpaper
   ([ui/frost.py](source:jbrowser/ui/frost.py), see [the overview](overview.md#the-window-frame)) and surfaces use
   their partly see-through tokens over it. *Solid* paints the opaque `*_solid` tokens instead. The window itself is
   opaque either way. Settings from before 2.0.3 (`acrylic`, `mica`, `mica_alt`) become `frosted`.
<!-- else -->
3. **Material**: `appearance.material` = `acrylic` (default), `mica`, `mica_alt` or `solid`. With a translucent
   material, `theme().translucent` is `True`: the window paints transparent pixels and DWM draws the system
   backdrop behind them. *Solid* paints the opaque `*_solid` tokens instead.
<!-- endif -->
<!-- if >= 1.5.0 -->
4. **Colour tint** and **incognito** (below).

## Colour tints

[[new 1.5.0]] `TINTS` defines ten colours (rose, coral, amber, lime, mint, teal, sky, indigo, violet, slate);
`appearance.tint` is one of their keys or `"none"`. A tint must stay a tint, never a paint job:

<!-- if >= 2.0.3 -->
- **With Frosted**, the tint becomes `window_tint`, a wash at 15 % opacity (dark) or 10 % (light) (`_WASH_ALPHA`).
  `backdrop_wash()` returns it, and it is baked into the frosted picture (`frost_look()`), so it costs nothing to
  paint.
<!-- else -->
- **Over Acrylic or Mica**, the tint becomes `window_tint`, a wash at 15 % opacity (dark) or 10 % (light)
  (`_WASH_ALPHA`), which `RootWidget` paints over the transparent backdrop. `backdrop_wash()` returns it.
<!-- endif -->
- **With Solid**, each opaque surface is mixed towards the tint by an amount per token (`_SOLID_MIX`: 20 % for the
  window, 24 % for the sidebar, down to 5 % for cards) with `mix()`, so text contrast stays intact.

The picker is `TintPicker` in [ui/widgets.py](source:jbrowser/ui/widgets.py): a keyboard-accessible row of swatches
(arrow keys move, the choice applies live) used by Settings and the welcome's *Look* page.
<!-- if >= 1.5.2 -->

[[new 1.5.2]] **The active card's outline** follows the tint too. `card_outline(alpha)` returns the tint washed 30 %
towards white on dark (12 % on light, `_OUTLINE_WASH`) at 90 % opacity, or grey (`_OUTLINE_GREY`) with *No colour*
and in incognito spaces. `WebCard` draws it 2 px wide around the active card, and at 60 % (and 14 % as the header
fill) for cards selected together. Earlier versions used the accent blue.
<!-- endif -->

## Incognito is black

When the active space is incognito, `MainWindow` calls `theme().set_incognito(True)`. The theme then forces dark,
ignores the tint, and overlays `_INCOGNITO`: near-black solid surfaces and a 62 % black wash over the backdrop<!-- if >= 2.0.3 --> (and a 93 % `frost_tint`, so only a hint of the wallpaper remains)<!-- endif -->, so
an incognito window is unmistakable. Switching to a normal space restores the chosen look.
<!-- endif -->

## Fonts

The UI uses Segoe UI (`UI_FONT`), and the Segoe UI Variable Display family for large text where available. Icons are
Segoe Fluent Icons glyphs (with a Segoe MDL2 Assets fallback), so no image files are needed.

## Changing the look

- New colour: add a token to both `DARK` and `LIGHT` (and a `*_solid` variant if it is a surface), then use
  `th.c("token")`.
- Never hard-code colours in widgets, except fixed brand colours such as space colours.
- Test both themes, <!-- if >= 2.0.3 -->both materials<!-- else -->all four materials<!-- endif --><!-- if >= 1.5.0 -->, a tint and an incognito space<!-- endif -->.
