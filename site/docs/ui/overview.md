---
title: User interface overview
nav_title: Overview
description: How the main window is assembled, how widgets talk to the rest of the app, and the conventions every widget follows.
---

Every pixel JBrowser draws is a Qt widget, most of them custom-painted in `paintEvent` with `QPainter` rather than
styled with style sheets. That is what gives JBrowser its Windows 11 look over a translucent backdrop.

## The main window

[`MainWindow`](api:jbrowser.ui.window.MainWindow) ([ui/window.py](source:jbrowser/ui/window.py)):

```text
MainWindow (QMainWindow, translucent, custom frame)
└── RootWidget                      paints the backdrop<!-- if >= 1.5.0 --> wash (colour tint or incognito black)<!-- endif -->
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
Layouts flyout), rounded corners and the drop shadow. `apply_backdrop()` asks DWM for Mica, Mica Alt or Acrylic
(`DWMWA_SYSTEMBACKDROP_TYPE`); translucent pixels in the window then show the backdrop.

### The window's event filter

`MainWindow.eventFilter()` sees events for the whole application. It implements the behaviours that cut across
widgets: Alt + mouse wheel pans the canvas from anywhere, pointing at the left edge peeks the hidden sidebar, mouse
back/forward buttons navigate the card under the pointer, and clicking inside a card focuses it.
<!-- if >= 1.5.0 -->
Alt + drag anywhere on a card moves it.
<!-- endif -->
It also gives menus and tooltips native rounded corners.

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
