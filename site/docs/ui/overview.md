---
title: User interface overview
nav_title: Overview
description: How the main window is assembled, how widgets talk to the rest of the app, and the conventions every widget follows.
---

Every pixel JBrowser draws is a Qt widget, most of them custom-painted in `paintEvent` with `QPainter` rather than
styled with style sheets. That is what gives JBrowser its Windows 11 look<!-- if >= 2.0.3 -->, over its own frosted backdrop<!-- else --> over a translucent backdrop<!-- endif -->.

## The main window

[`MainWindow`](api:jbrowser.ui.window.MainWindow) ([ui/window.py](source:jbrowser/ui/window.py)):

```text
MainWindow (QMainWindow, <!-- if >= 2.0.3 -->opaque<!-- else -->translucent<!-- endif -->, custom frame)
└── RootWidget                      <!-- if >= 2.0.3 -->paints the Frosted picture (tint included) or the Solid colour<!-- else -->paints the backdrop<!-- endif --><!-- if >= 1.5.0 and < 2.0.3 --> wash (colour tint or incognito black)<!-- endif -->
    ├── Sidebar                     favourites, spaces, the space's cards, tools
    └── right column
        ├── TitleBar                navigation, the address pill, tools, window buttons
        ├── FavoritesBar            the bookmarks bar (Ctrl+Shift+B)
        └── SpaceStack              one Canvas per space, sliding between them
            └── Canvas → WebCard    one card per tab: header, web view, info bars, find bar
<!-- if >= 1.5.0 -->
            └── Gallery             the overlay grid of every card (Ctrl+Shift+G)
<!-- endif -->
    overlays: LazyToolbar · HotkeySheet · ToastManager · Onboarding
```

The constructor also creates the `BrowserController`, installs `WindowHooks` as `ctx.hooks`, registers every
command and installs the shortcuts, and connects the lifecycle signals to the cards.

### The window frame

The window has no native title bar but keeps every native behaviour. `NativeFrame` in
[platform/win.py](source:jbrowser/platform/win.py) handles `WM_NCCALCSIZE` (the whole window is client area),
`WM_NCHITTEST` (resize edges, the caption, and `HTMAXBUTTON` over the maximise button so Windows 11 shows the Snap
Layouts flyout), rounded corners and the drop shadow.
<!-- if < 2.0.3 -->
`apply_backdrop()` asks DWM for Mica, Mica Alt or Acrylic
(`DWMWA_SYSTEMBACKDROP_TYPE`); translucent pixels in the window then show the backdrop.
<!-- endif -->
<!-- if >= 2.0.3 -->
To keep the hit test cheap, `NativeFrame.handle()` reads only the message number from the `MSG` and returns at once
for every message it doesn't handle, which is almost all of them.

[[changed 2.0.3]] **Opaque windows, JBrowser's own frosted look.** Every JBrowser window is opaque: none sets
`WA_TranslucentBackground`, and DWM materials (Mica, Mica Alt, Acrylic) are not used at all. Earlier versions asked
DWM for a material and left the window's pixels see-through. On some PCs, DWM drew no material, the wrong one, or a
stale one over part of the window, and no amount of detecting and repainting made that reliable. Now nothing that
Windows draws can show through a JBrowser window.

The look is painted by JBrowser itself, in [ui/frost.py](source:jbrowser/ui/frost.py):

- **The picture.** `Frost` reads the desktop wallpaper (`win.wallpaper_path()`, `SPI_GETDESKWALLPAPER`; or the
  desktop's solid colour, `win.desktop_color()`), reduces it to 64 pixels wide in halving steps, saturates it ×1.35,
  lays the theme's `frost_tint` over it (plus the colour tint's wash), and enlarges it to 1024 pixels wide in
  doubling steps. Each bilinear step softens the last, so the result is a smooth blur without seams. The 64-pixel
  copy is cached on disk (`frost-<hash>.png` in the cache folder), so starting up never decodes the wallpaper again.
  The wallpaper never leaves the PC.
- **One pixmap per window size.** For a window of a given size, the smooth picture is cover-fitted, cropped, given
  a 2.8 % grain (so soft gradients don't band) and, for the canvas, the `canvas` layer baked in. Up to four of these
  are kept (`CACHE_SIZES`). Painting is a 1:1 `drawPixmap` of the dirty rectangle, as cheap as a colour fill. The
  picture is fitted to the window, not to the screen, so moving a window never repaints anything.
- **Resizing.** A window's first picture is built at once. While a window is being resized, it gets the nearest
  picture already made, stretched, and only the size it rests at is built, 140 ms later (`Frost.changed` then
  repaints the windows).
- **A new wallpaper.** `Frost.check()` compares the wallpaper's path, size and date when Windows broadcasts a
  settings change and when JBrowser is activated, and emits `changed` if it differs.
- `Theme.paint_backdrop(p, widget, rect, layer=None)` paints either the frosted picture or, with Solid, the
  layer's `_solid` colour. `RootWidget`, the canvas and `ChromeWindow` paint every pixel of their area
  (`WA_OpaquePaintEvent`), so Qt never fills a background first. The title bar, the bookmarks bar and the sidebar
  have no base of their own. They draw over the root's picture, in the same opaque window (the sidebar adds its
  partly see-through `sidebar` surface).
- For screenshots and tests, `JBROWSER_WALLPAPER` points `Frost` at another picture.

What is left for Windows is small. [ui/backdrop.py](source:jbrowser/ui/backdrop.py):

- **`Backdrop(window, kind)`** keeps one top-level window's frame in step with the theme: `"window"` (frameless
  windows: the main window and `ChromeWindow`s), `"popup"` (the Archive: rounded corners only) or `"frame"` (dialogs
  with a native title bar: the mode and the caption colours). After anything that can disturb the light/dark mode
  (palette changes, activation, window state changes, `WinIdChange`, Windows settings broadcasts), it **sets the
  mode again** in one deferred call. Setting the same value changes nothing on screen, so nothing can loop. It
  refreshes the frame once per native window, so `WM_NCCALCSIZE` takes over.
- It cloaks a new window (`DWMWA_CLOAK`) from its first `Show` event until its first frame is painted
  (`Backdrop.CLOAK_MS`), so it never appears as a white or black rectangle. `JBROWSER_NO_CLOAK=1` turns that off.
- `caption_hit()` does the caption hit test for both window kinds and never raises. An exception there used to make
  the window procedure fall back to "client area", and the window stopped dragging.
- **`Theme.refresh()`** applies the new palette before telling Qt the colour scheme (`_request_scheme()`), so Qt's
  re-application finds the matching palette.
- Menu actions (`menu_action()`) run after the menu has closed, outside `QMenu.exec()`'s event loop. Menus are
  opaque, and Windows rounds their corners.
<!-- elif >= 1.6.2 -->

[[changed 1.6.2]] **One owner for each window's look.** DWM draws the material light or dark according to the
window's `DWMWA_USE_IMMERSIVE_DARK_MODE`, and more than one party sets it: JBrowser, and Qt, which re-applies its own
idea of light/dark to every window frame when the application palette or colour scheme changes
(`QWindowsWindow::windowEvent`, `ApplicationPaletteChange`; Qt judges by the colour scheme *and* the palette at that
moment). 1.6.0 reacted to that by reading the attribute back, rebuilding the material and refreshing the frame on
activation, and the main window switched JBrowser between its translucent and solid look whenever a DWM call failed.
On some PCs those reactions fed each other: pale windows, a stale rectangle over the title bar, a caption that
stopped dragging (a frame refresh during activation interrupts a drag), black or white flashes and a frozen app (a
restyle loop). [ui/backdrop.py](source:jbrowser/ui/backdrop.py) replaces all of it:

- **`Backdrop(window, kind)`** owns one top-level window: `"window"` (frameless windows with a material: the main
  window and `ChromeWindow`s), `"popup"` (the Archive and every `QMenu`: Acrylic over the whole window) or `"frame"`
  (dialogs with a native title bar: the mode and the caption colours). It applies the material and the mode when
  they change, and refreshes the frame once per native window so `WM_NCCALCSIZE` takes over.
- After anything that can disturb the mode (palette changes, activation, window state changes, `WinIdChange`, and
  Windows settings broadcasts that `NativeFrame` reports through `on_system_change`), it **sets the mode again**,
  coalesced into one deferred call. Setting the same value changes nothing on screen, so nothing can loop. It never
  reads the state back, never rebuilds the material and never restyles the app.
- **`Theme.translucent`** depends only on the setting and `win.backdrop_supported()` (Windows 11, or Windows 10 with
  pywinstyles), never on a single DWM call.
- **`Theme.backdrop_layers()`**: translucent windows paint JBrowser's own base colour (`backdrop_base`, about 55–60 %
  opaque) and then the tint over the backdrop, so a window stays dark or light whatever DWM draws behind it.
- **`Theme.refresh()`** applies the new palette before telling Qt the colour scheme (`_request_scheme()`), so Qt's
  re-application finds the matching palette.
- `caption_hit()` does the caption hit test for both window kinds and never raises: an exception there used to make
  the window procedure fall back to "client area", and the window stopped dragging.
- Menu actions (`menu_action()`) run after the menu has closed, outside `QMenu.exec()`'s event loop.
<!-- elif >= 1.6.0 -->

[[new 1.6.0]] **Keeping the backdrop's light/dark state.** DWM draws the material light or dark according to the
window's `DWMWA_USE_IMMERSIVE_DARK_MODE`. Qt sets that attribute itself whenever the application palette changes
(`QWindowsWindow::windowEvent`, `ApplicationPaletteChange`), using *its* colour scheme, which follows Windows. With
Windows in light mode and JBrowser in dark mode, a routine Windows settings broadcast (an accent colour, energy
saver) turned the Acrylic light behind light text, and maximising re-darkened only the newly exposed area. So:

- `Theme._request_scheme()` tells Qt JBrowser's scheme (`QStyleHints.setColorScheme`; `unsetColorScheme()` when the
  theme follows Windows), so Qt's own updates agree with JBrowser's.
- `MainWindow` and `ChromeWindow` check the attribute after palette changes, activation and maximise/restore
  (`win.dark_frame()`), restore it if anything else changed it, and rebuild the material
  (`apply_backdrop(rebuild=True)`: none, then the material again) so no part of the window keeps the wrong one.
<!-- endif -->
<!-- if >= 2.0.1 and < 2.0.3 -->

[[new 2.0.1]] **When Windows draws no material, or the wrong one.** With transparency effects or energy saver off, a
high-contrast theme, over Remote Desktop, or with a graphics driver that can't give windows see-through pixels, DWM
draws a flat fill (or black) behind the window instead of Mica or Acrylic. `LookGuard` in
[ui/backdrop.py](source:jbrowser/ui/backdrop.py) decides `Theme.see_through` from three sources:

- `win.material_blockers()` (the *Transparency effects* setting, `SPI_GETHIGHCONTRAST`, `GetSystemPowerStatus`,
  `SM_REMOTESESSION`), every 3 seconds and whenever `NativeFrame.on_system_change` reports a broadcast;
- Qt's own warnings about Direct Composition (`note_qt_message()`, fed by the message handler in
  [app.py](source:jbrowser/app.py), which also writes Qt's warnings to the log);
- the screen. After a window appears, a theme change or a system change, and now and then on activation, the active
  window leaves a 3 × 3 spot at the top edge of its title bar unpainted for one frame (`paint_probe_hole()`) and
  `win.sample_own_pixel()` reads what DWM composited there: the bare material. Black means no see-through pixels; a
  light material behind a dark theme (luma above 170) or a dark one behind a light theme (below 110) means the wrong
  material. (Measured on Windows 11: dark Acrylic reads 54 over black and 146 over white, light Acrylic 135 and 227,
  Mica about 32 and 244.) Two readings in a row must agree.

While `see_through` is off, `backdrop_layers()` puts the opaque `TRANSITION_BASE` under everything and menus and glass
popups get opaque backgrounds, so the window looks like the Solid material until the material is back.

Two more things keep the look steady:

- `NativeFrame` answers `WM_NCACTIVATE` with `wParam = TRUE`, so DWM keeps the active material when the window loses
  the focus, instead of its flat grey or white inactive fill. Qt still learns about activation from `WM_ACTIVATE`.
- `Backdrop` cloaks a new `"window"` or `"frame"` window (`DWMWA_CLOAK`) from its first `Show` event until its
  material, mode and first frame are ready (`Backdrop.CLOAK_MS`), so it never appears as a white or black rectangle.

For testing: `JBROWSER_NO_MATERIAL=1` behaves as if Windows drew no materials, `JBROWSER_INACTIVE_LOOK=1` restores
Windows' inactive look and `JBROWSER_NO_CLOAK=1` turns the cloak off.
<!-- endif -->
<!-- if >= 2.0.2 and < 2.0.3 -->

[[new 2.0.2]] **Every bar paints its own base.** On some PCs a rectangle at the top right of the window (over the
ribbon's buttons and the bookmarks bar) showed the bare backdrop until the window was minimised: those pixels had
been redrawn without the window background (`RootWidget`) underneath. Now the title bar, the bookmarks bar and the
sidebar start their `paintEvent` with `Theme.paint_base()`, which paints `Theme.backdrop_color()` (the backdrop layers
flattened into one colour, or the Solid window colour) with `CompositionMode_Source`, exactly as the canvas does.
What they show no longer depends on anything being repainted underneath them. LookGuard's probe spot is painted by
the title bar for the same reason. As a safety net, `MainWindow` repaints the whole window (`_heal`, debounced) when
it gains or loses the focus, when a menu or tooltip hides, and on Windows settings broadcasts; `ChromeWindow`
repaints on focus changes.
<!-- endif -->

### The window's event filter

`MainWindow.eventFilter()` sees events for the whole application. It implements the behaviours that cut across
widgets: Alt + mouse wheel pans the canvas from anywhere, pointing at the left edge peeks the hidden sidebar, mouse
back/forward buttons navigate the card under the pointer, and clicking inside a card focuses it.
<!-- if >= 1.5.0 -->
Alt + drag anywhere on a card moves it.
<!-- endif -->
It also gives menus and tooltips native rounded corners.
<!-- if >= 2.0.3 -->
Because it sees every event, it starts by checking the event type against `_WATCHED_EVENTS` (a frozenset) and
returns at once for everything else, such as paints, timers and layout requests.
<!-- endif -->

## How widgets talk

- **Read** from `ctx.state`, `Tab` models and `ctx.settings`, and connect to their signals.
- **Act** through `ui` (the `BrowserController`) or `ctx.commands.run(id)`. Never call another widget.
- **Draw** with the theme's tokens (`theme().c("text2")`, `theme().surface("card")`), never hard-coded colours,
  and repaint on `theme().changed`.
- **Animate** with `motion()` ([motion](motion.md)).

## Overlays

Full-window modal layers derive from `Overlay` in [ui/widgets.py](source:jbrowser/ui/widgets.py): a scrim over the
window, a panel from `panel_rect()`, Escape and clicks outside close it, focus returns where it was. The Lazy Toolbar
and the shortcut sheet are overlays. Transient messages use `ToastManager.show(text, glyph, duration_ms)`.

## Reusable widgets

[ui/widgets.py](source:jbrowser/ui/widgets.py) holds the custom-painted controls: `IconButton` (with badge and
progress ring), `ToggleSwitch`, `Spinner`, `ProgressLine`, `ElidedLabel`, `InfoBarWidget`, `Toast`, helpers such
as `menu_action()`<!-- if >= 1.5.0 -->, and the colour-tint picker `TintPicker`<!-- endif -->. Icons are glyphs from the Segoe Fluent Icons font
([ui/icons.py](source:jbrowser/ui/icons.py)): `icon("settings")` returns a `QIcon` whose colour follows the theme,
and `draw_glyph()` paints one directly.

## Accessibility

- Custom widgets set accessible names and descriptions (`setAccessibleName`), and keyboard focus is always visible.
- Everything is reachable from the keyboard; the command registry makes every action searchable.
- *Fluid animations* off removes every animation; on first run it follows the Windows "Animation effects" setting.

## Read next

[Theming](theming.md), [the canvas and cards](canvas-and-cards.md), [the sidebar](sidebar.md),
[the Lazy Toolbar](lazy-toolbar.md)<!-- if >= 1.5.0 -->, [the Gallery](gallery.md)<!-- endif -->.
