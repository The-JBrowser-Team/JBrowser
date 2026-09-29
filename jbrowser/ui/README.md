# `jbrowser/ui/`: widgets and windows

Everything on screen. Widgets observe `BrowserState` and settings, and send user intents to `BrowserController`
or the command registry. They never call each other directly.

| File | Purpose |
|---|---|
| `window.py` | `MainWindow`: the Windows 11 window that holds the sidebar, title bar and canvases, and wires them together |
| `controller.py` | `BrowserController`: **what every click, shortcut and command actually does** |
| `actions.py` | Registers every command with its shortcut, Lazy Toolbar keywords and live state |
| `titlebar.py` | The ribbon: navigation, the address pill, tools (including the *Gallery* and *Update* buttons) and window controls |
| `sidebar.py` | Favourites, spaces, the current space's cards (drag to reorder or move), the centred clock, peek-to-show and the tools row |
| `canvas.py` | The infinite horizontal canvas and the `SpaceStack` (panning, resizing, dragging cards, pull to add a card, the overview strip) |
| `gallery.py` | The Gallery (Ctrl+Shift+G): every card of a space, or of all spaces, as an animated, keyboard-accessible grid of thumbnails |
| `card.py` | `WebCard`: one web page on the canvas (header, info bars, find bar, sleep snapshot) |
| `lazy_toolbar.py` | The Lazy Toolbar command overlay (Ctrl+T / Ctrl+K) |
| `onboarding.py` | The first-run welcome: animated intro, story slides, setup pages and the guided tour |
| `sounds.py` | Low-latency UI sound effects (welcome screen) |
| `archive.py` | The Archive popup (cards closed in the last 48 hours) |
| `site_info.py` | The site information panel behind the lock icon |
| `favorites_bar.py` | The bookmarks bar (Ctrl+Shift+B). The file name predates the rename. |
| `hotkeys.py` | The shortcut sheet (Ctrl+/), generated from the command registry |
| `chrome_window.py` | `ChromeWindow`: the translucent base for Settings and the other tool windows |
| `theme.py` | Palettes, fonts and style sheets for dark and light over Mica / Acrylic, the colour tints and the incognito black |
| `icons.py` | Icons drawn from the Segoe Fluent Icons font |
| `widgets.py` | Reusable custom-painted controls (toggles, chips, toasts, the colour-tint picker and so on) |

[`dialogs/`](dialogs/README.md) holds Settings and the tool windows.
