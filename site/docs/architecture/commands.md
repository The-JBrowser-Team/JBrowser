---
title: Commands and shortcuts
nav_title: Commands
description: The command registry behind shortcuts, menus, the Lazy Toolbar and the shortcut sheet.
---

Every action a user can trigger by name is a **command**: an ID, a title, a category, a handler and optional
shortcuts. The [`CommandRegistry`](api:jbrowser.core.commands.CommandRegistry)
([core/commands.py](source:jbrowser/core/commands.py)) is the single source of truth for them, which gives four
things for free:

- the **keyboard shortcut** (installed on the main window as a `QShortcut`);
- an entry in the **Lazy Toolbar**, found by title and keywords (`>` limits the search to commands);
- a row in the **shortcut sheet** (Ctrl+/ or F1, [ui/hotkeys.py](source:jbrowser/ui/hotkeys.py));
- one code path, whether the user clicks a menu item, presses the keys or types the command.

The generated [commands reference](../reference/commands.md) lists every command of this version, and
[shortcuts](../reference/shortcuts.md) lists every key binding.

## Registering a command

All commands are registered in `register_commands(ctx, ui)` in [ui/actions.py](source:jbrowser/ui/actions.py), when
the main window is built:

```python
c.add("card.duplicate", "Duplicate card", CARDS, lambda: ui.duplicate_tab(),
      shortcuts=["Ctrl+Shift+K"], icon="copy", keywords="clone copy tab")

c.add("perf.throttle", "Throttle cards out of view", PERF, lambda: s.toggle("performance.throttle"),
      icon="speed", state=on_off("performance.throttle"), keywords="cpu gpu background render")
```

| Argument | Meaning |
|---|---|
| `id` | Stable, dotted, lowercase: `area.action`. Other code runs it with `ctx.commands.run(id)`. |
| `title` | What the Lazy Toolbar and the shortcut sheet show. Plain language. |
| `category` | The heading it is grouped under: one of the constants at the top of each block, such as `CARDS` ("Cards"), `LAYOUT`, `NAV`, `PAGE`, `SPACES`, `VIEW`, `TOOLS`, `PRIV`, `NET`, `PERF` and `APP`. |
| handler | A callable with no arguments, usually a `BrowserController` method. |
| `shortcuts` | Qt key sequences such as `"Ctrl+Shift+K"`. Several are allowed. |
| `icon` | A glyph name from `GLYPHS` in [ui/icons.py](source:jbrowser/ui/icons.py). |
| `keywords` | Extra words the Lazy Toolbar matches (synonyms, the words people search for). |
| `state` | A callable returning a short label such as `"On"`, `"Off"` or `"Active"`, shown next to the title. |
| `enabled` | A callable; when it returns `False`, `run()` does nothing. |
| `palette=False` | Keep it out of the Lazy Toolbar (for example `Ctrl+Tab`, which only makes sense as a key). |

Commands generated in a loop (one per window material, DNS mode, memory-saver preset<!-- if >= 1.5.0 -->, colour tint<!-- endif -->,
settings page and developer port) follow the same pattern with f-string IDs.

## Running a command

```python
ctx.commands.run("gallery.toggle")
```

`run()` checks `enabled`, calls the handler and emits `executed(id)`. An unknown ID only logs a warning.

## Shortcuts

`install_shortcuts(window)` creates one `QShortcut` per key sequence with `WindowShortcut` context, so shortcuts work
anywhere in the main window, including while a web page has focus. Navigation keys (`Alt+Left`, `Ctrl+Tab`, zoom and
space switching) auto-repeat when held; everything else fires once.

`set_shortcuts_enabled(False)` switches them all off while a full-window experience owns the keyboard, such as the
welcome tour.

Before adding a shortcut, check the [shortcuts reference](../reference/shortcuts.md) for a clash, and prefer
combinations Chrome and Edge use for the same thing.

## Where the handler logic lives

Keep handlers thin. The real work belongs in [`BrowserController`](api:jbrowser.ui.controller.BrowserController),
where menus, buttons and other commands can call it too. A handler that is more than a line usually means a
controller method is missing.
