---
title: Settings
description: The observable settings store, how to add a setting, and how changes apply immediately.
---

All preferences live in one key/value store, [`Settings`](api:jbrowser.core.settings.Settings)
([core/settings.py](source:jbrowser/core/settings.py)), saved as `settings.json` in the data folder. Every key and
its default is listed in the [settings reference](../reference/settings.md).

## Reading and writing

```python
s = ctx.settings
s.get("privacy.gpc")                 # the stored value, or the default from DEFAULTS
s.set("appearance.tint", "violet")   # stores, emits changed(key, value), saves 0.4 s later
s.toggle("performance.throttle")     # flips a bool and returns the new value
s.changed.connect(on_setting)        # def on_setting(key: str, value) -> None
```

- `get()` and `set()` deep-copy values, so changing a list you got back never changes the store by accident.
- `set()` with the value already stored does nothing and emits nothing.
- Saving is debounced: `set()` restarts a 400 ms timer, then `save_now()` writes the whole file atomically
  ([persistence](persistence.md)). `ctx.save_all()` calls `save_now()` on shutdown.

## Changes apply immediately

Nothing in JBrowser reads a setting once and caches it forever. A component that depends on a setting reads it when
it needs it, or subscribes to `changed` and filters by key:

```python
ctx.settings.changed.connect(lambda key, _v: self.refresh() if key == "canvas.show_minimap" else None)
```

Examples: `Theme` recomputes its colours on `appearance.theme`, `appearance.use_accent`,
`appearance.material`<!-- if >= 1.5.0 --> and `appearance.tint`<!-- endif -->, `ProfileManager` reinstalls page scripts on `privacy.gpc`,
`privacy.dnt`, `privacy.fingerprint_protection`<!-- if >= 1.5.0 -->, `privacy.block_trackers`<!-- endif --> and
`privacy.allowlist`, `AppContext` re-applies DNS on `network.dns_mode`, and the lifecycle manager un-throttles every
card when `performance.throttle` is switched off.

## Adding a setting

1. Add the key and default to `DEFAULTS` in `core/settings.py`, in the right group, with a trailing comment when the
   values aren't obvious (`# system | dark | light`). The comment appears in the
   [settings reference](../reference/settings.md).
2. Read it where it matters with `ctx.settings.get(...)`, and react to `changed` if it must apply live.
3. Add a control to [ui/dialogs/settings.py](source:jbrowser/ui/dialogs/settings.py), usually with
   `_toggle_card(key, glyph, title, description)` or a combo box, and write the description for users: what it does
   and when you would change it. The settings search box searches those descriptions.
4. If it deserves a quick toggle, register a [command](commands.md) with `state=on_off(key)` so the Lazy Toolbar
   shows *On* or *Off*.

Keys are `area.name` in lowercase with underscores. Existing areas: `appearance`, `sidebar`, `gallery`, `toolbar`,
`onboarding`, `updates`, `canvas`, `startup`, `window`, `search`, `privacy`, `performance`, `network`, `passwords`,
`downloads`, `zoom`, `profiles`.

## Versions and migration

`settings.version` records the format of the stored file. When JBrowser reads an older file, `_migrate()` adjusts
it (version 2 switched the default material to Acrylic) and `migrated_from` tells the rest of start-up where the
data came from. Raise `SETTINGS_VERSION` only when stored values need converting; new keys need no migration because
missing keys fall back to `DEFAULTS`.

## Reset

*Settings → Reset → Restore default settings* calls `reset_to_defaults()`: every key goes back to its default
except window placement, pending profile deletions, list-update times, recent searches, `onboarding.version` and
`updates.last_check`. Keys that are no longer in `DEFAULTS` are dropped. A *factory reset* instead deletes the whole
data folder at the next start ([start-up and shutdown](startup-shutdown.md#restart-and-factory-reset)).
