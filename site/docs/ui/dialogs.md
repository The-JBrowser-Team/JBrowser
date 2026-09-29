---
title: Settings and tool windows
nav_title: Settings and dialogs
description: ChromeWindow and JDialog, the Settings window, and the tool windows in ui/dialogs.
---

Two base classes keep every window consistent with the main window:

| Base | For | File |
|---|---|---|
| [`ChromeWindow`](api:jbrowser.ui.chrome_window.ChromeWindow) | tool windows: Settings, History, Bookmarks, Passwords, Downloads, Cookies, Permissions, user scripts, developer hosts | [ui/chrome_window.py](source:jbrowser/ui/chrome_window.py) |
| [`JDialog`](api:jbrowser.ui.dialogs.base.JDialog) | small modal prompts: sign-in, bookmark and space editors, the proxy dialog, the screen picker, the update dialog | [ui/dialogs/base.py](source:jbrowser/ui/dialogs/base.py) |

`ChromeWindow` uses the main window's technique: the whole window is client area, the system backdrop shows through
translucent pixels, and a slim custom caption keeps drag, Snap Layouts and the window buttons. Subclasses fill
`self.root`, optionally with a translucent navigation pane.

## Opening a tool window

```python
ui.open_dialog("history")          # history, bookmarks, downloads, passwords, cookies, permissions, ...
ui.open_settings("privacy")        # a Settings page by key
```

`BrowserController` keeps one instance of each tool window in `_dialogs` and brings it to the front if it is already
open. Dialog modules are imported lazily, the first time they are opened, which keeps start-up fast (the PyInstaller
spec collects them explicitly for the same reason).

## The Settings window

[`SettingsWindow`](api:jbrowser.ui.dialogs.settings.SettingsWindow) ([ui/dialogs/settings.py](source:jbrowser/ui/dialogs/settings.py))
has a navigation pane of `PAGES` (General, Appearance, Search, Privacy and security, Clear browsing data, Passwords,
Performance, Network and DNS, Downloads, Advanced, Reset and About) and, on the right, `SettingCard`s: an icon, a
title, a plain-language description and a control.

- Helpers build the common controls: `_toggle(key)`, `_toggle_card(key, glyph, title, description)` and
  `_combo(key, options)`. Each writes straight into the settings store, so changes apply immediately.
- The search box filters cards by their title and description text across all pages.
- `_listen(signal, slot)` connects to app-wide signals and disconnects them when the window closes, so a closed
  Settings window never receives updates.
- Every setting also has a command page in the Lazy Toolbar (`Settings: <page>`).

## Writing a new dialog

1. Subclass `ChromeWindow` for a tool window or `JDialog` for a prompt.
2. Paint with theme tokens and connect to `theme().changed`; use the reusable widgets.
3. Keep the logic in a service; the dialog only shows and edits it.
4. Add it to `BrowserController.open_dialog()` and give it a command in `ui/actions.py`.
