# `jbrowser/core/`: building blocks

Small modules with no widgets and no knowledge of the rest of JBrowser. Anything may import them.

| File | Purpose |
|---|---|
| `settings.py` | The observable settings store. **`DEFAULTS` lists every setting and its default.** Changes are saved to `settings.json` and announced to subscribers. |
| `commands.py` | `CommandRegistry`: the one list of actions with their shortcuts and Lazy Toolbar keywords (filled by `ui/actions.py`) |
| `motion.py` | The global motion policy. Every animation asks it for a duration, so *Fluid animations* off makes them all instant. |
| `fuzzy.py` | The fast fuzzy matcher behind Lazy Toolbar search |
| `urls.py` | Tells addresses from searches, and provides host and domain helpers |
| `jsonstore.py` | Crash-safe JSON and binary saving (write to a temp file, then replace) |
| `workers.py` | Background downloads shared by the tracker-list and threat-list updaters |
