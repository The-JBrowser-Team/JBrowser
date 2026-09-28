# `jbrowser/`: the application package

`python main.py` (or `python -m jbrowser`) calls `jbrowser.app.run()`. The big picture is in
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

| File | Purpose |
|---|---|
| `__init__.py` | App identity: **`__version__` (the one place the version is set)**, name, company, GitHub repository, mutex name |
| `__main__.py` | Lets `python -m jbrowser` start the app |
| `app.py` | Start-up and shut-down: command line, Chromium flags, single instance, services, window, welcome, update check |
| `context.py` | `AppContext`: creates every service in dependency order and hands them to the UI (no globals) |
| `paths.py` | Every file and folder JBrowser uses (`%APPDATA%\JBrowser`, caches, portable mode, factory reset) |
| `single_instance.py` | A second launch forwards its URLs to the running window over a local socket |

| Sub-package | Purpose |
|---|---|
| [`core/`](core/README.md) | Building blocks with no UI |
| [`models/`](models/README.md) | The browser state |
| [`services/`](services/README.md) | Features without widgets |
| [`engine/`](engine/README.md) | Qt WebEngine (Chromium) integration |
| [`platform/`](platform/README.md) | Windows-specific code |
| [`ui/`](ui/README.md) | Widgets and windows |

Imports flow downwards: `ui` → `engine` / `services` / `models` → `core` / `platform`.
