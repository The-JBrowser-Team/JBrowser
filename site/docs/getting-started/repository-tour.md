---
title: Repository tour
description: What lives where in the JBrowser repository.
---

Every folder has a `README.md` listing its files; this page is the map above them.

## Top level

| Path | What's inside |
|---|---|
| [`jbrowser/`](source:jbrowser/) | The application package (below) |
| [`main.py`](source:main.py) | Entry point for `python main.py` and the PyInstaller build |
| [`assets/`](source:assets/) | The icon, the logo and the welcome-screen sounds bundled with the app |
| [`installer/`](source:installer/) | `JBrowser.iss`, the Inno Setup script for `JBrowser-Setup-<version>.exe` |
| [`tools/`](source:tools/) | Scripts for dependencies, versions, icons, builds and releases |
| [`docs/`](source:docs/) | Guides in Markdown: features, architecture, building, releasing, updates |
<!-- if >= 1.4.1 -->
| [`master.ps1`](source:master.ps1) | Builds, packages and publishes everything in one command |
| [`install.ps1`](source:install.ps1) | The one-command installer users run with `irm … \| iex` |
<!-- endif -->
<!-- if main -->
| [`site/`](source:site/) | This website: templates, styles, scripts and the documentation pages |
<!-- endif -->
| [`JBrowser.spec`](source:JBrowser.spec) | The PyInstaller recipe |
| `requirements*.txt` | Runtime packages, build tools<!-- if >= 1.5.0 -->, exact pinned versions (`requirements.lock.txt`)<!-- endif --> |
| [`.github/`](source:.github/) | CI, issue templates and the pull-request template |

## The `jbrowser` package

The package is split into layers; each only imports the layers below it
([architecture overview](../architecture/overview.md)).

| Folder | Layer | What's inside |
|---|---|---|
| `jbrowser/*.py` | Application | `app.py` (start-up and shutdown), `context.py` (the `AppContext` container), `paths.py` (file locations), `single_instance.py` |
| [`core/`](source:jbrowser/core/) | Core | No UI and no web engine: settings, the command registry, motion, fuzzy matching, URL helpers, atomic JSON files, background downloads |
| [`models/`](source:jbrowser/models/) | Models | `BrowserState`, `Space`, `Tab` and the per-frame update pipeline |
| [`services/`](source:jbrowser/services/) | Services | Features without widgets: history, bookmarks, the password vault, privacy<!-- if >= 1.5.0 --> and the filter engine<!-- endif -->, threats, network, downloads, session, updates and more |
| [`engine/`](source:jbrowser/engine/) | Web engine | Qt WebEngine: per-space profiles, tab controllers, pages, the lifecycle manager and injected JavaScript |
| [`platform/`](source:jbrowser/platform/) | Platform | `win.py`: DWM backdrops, the custom window frame, DPAPI, accent colour |
| [`ui/`](source:jbrowser/ui/) | User interface | Every widget: the window, title bar, sidebar, canvas, cards, Lazy Toolbar<!-- if >= 1.5.0 -->, Gallery<!-- endif --> and welcome |
| [`ui/dialogs/`](source:jbrowser/ui/dialogs/) | User interface | Settings and the tool windows: history, bookmarks, passwords, downloads, cookies and more |

## Finding code for something you can see

- **A button or menu item:** search [`ui/actions.py`](source:jbrowser/ui/actions.py) for its text. The command's
  handler usually calls a method on `BrowserController` in [`ui/controller.py`](source:jbrowser/ui/controller.py).
- **A setting:** search for its key (for example `"privacy.gpc"`); the [settings reference](../reference/settings.md)
  lists where each key is read.
- **Something a web page does differently:** start at [`engine/tab_controller.py`](source:jbrowser/engine/tab_controller.py)
  or [`services/privacy.py`](source:jbrowser/services/privacy.py).
- **A class or function:** use the search box at the top, which also searches the [Python API](../api/index.md).
