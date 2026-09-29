---
title: Contributor quick reference
nav_title: Quick reference
description: The commands, files and conventions you need most often, on one page.
---

The page to keep open while you work. Every command runs from the repository folder in PowerShell.

## Everyday commands

| To… | Run |
|---|---|
| Create or update the environment | `py -3.14 tools\update_deps.py` |
| Check that everything imports and pyflakes is clean | `.\.venv\Scripts\python.exe tools\update_deps.py --check` |
| Run JBrowser with a test profile | `.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-dev"` |
| Run with console logging | add `--debug` |
| Skip the welcome and the update check | `$env:JBROWSER_SKIP_WELCOME = "1"; $env:JBROWSER_SKIP_UPDATES = "1"` |
| Print the version | `.\.venv\Scripts\python.exe tools\version.py` |
<!-- if >= 1.4.1 -->
| Build and package everything | `.\master.ps1` |
| Release a new version | `.\master.ps1 -Version X.Y.Z -Publish` |
<!-- else -->
| Build the installer | `.\tools\build_installer.ps1` |
| Release a new version | `python tools\version.py --set X.Y.Z`, commit, then `.\tools\release.ps1` |
<!-- endif -->
<!-- if main -->
| Build and preview this website | `.\.venv\Scripts\python.exe tools\build_site.py --serve` |
<!-- endif -->

## Where to make a change

| To… | Edit |
|---|---|
| Add a setting | its default in `DEFAULTS` ([core/settings.py](source:jbrowser/core/settings.py)) and a control in [ui/dialogs/settings.py](source:jbrowser/ui/dialogs/settings.py) |
| Add a command or shortcut | [ui/actions.py](source:jbrowser/ui/actions.py): it appears in the Lazy Toolbar and the shortcut sheet by itself |
| Change what an action does | `BrowserController` in [ui/controller.py](source:jbrowser/ui/controller.py) |
| Change colours, fonts or surfaces | [ui/theme.py](source:jbrowser/ui/theme.py) |
| Change animation timing | [core/motion.py](source:jbrowser/core/motion.py), and `motion().animate_value()` at the call site |
| Inject JavaScript into pages | [engine/js.py](source:jbrowser/engine/js.py), installed by [engine/profiles.py](source:jbrowser/engine/profiles.py) |
| Decide what gets blocked | `PrivacyService.should_block()` in [services/privacy.py](source:jbrowser/services/privacy.py) |
| Store a new file | a path on `AppPaths` in [paths.py](source:jbrowser/paths.py) and `atomic_write_json()` from [core/jsonstore.py](source:jbrowser/core/jsonstore.py) |
| Call a Windows API | [platform/win.py](source:jbrowser/platform/win.py) |
| Show the welcome again to existing users | raise `ONBOARDING_VERSION` in [ui/onboarding.py](source:jbrowser/ui/onboarding.py) |
| Change the version | `python tools\version.py --set X.Y.Z` |

## The rules that keep the code healthy

1. **Dependencies point down.** `core` and `platform` import nothing else from JBrowser; `models` and `services`
   never import `ui`. The UI observes lower layers through Qt signals. See [the architecture](../architecture/overview.md).
2. **Widgets don't talk to each other.** They read `BrowserState` and settings, and send intents to
   `BrowserController` or run a command.
3. **Everything that moves asks `motion()`**, so *Fluid animations* can turn every animation off.
4. **Saves are atomic.** Write through `atomic_write_json()` / `atomic_write_bytes()`, never `open(..., "w")`.
5. **Nothing blocks the UI thread.** Network work runs asynchronously (`QNetworkAccessManager`) or in a `QThread`
   stopped with `stop_worker()` from [core/workers.py](source:jbrowser/core/workers.py).
6. **Plain language for users.** "Clear browsing data", not "Purge storage".
7. **pyflakes stays clean.** CI fails otherwise.

## Useful locations

| What | Where |
|---|---|
| Your data (normal profile) | `%APPDATA%\JBrowser` |
| Caches | `%LOCALAPPDATA%\JBrowser\Cache` |
| The log | `%APPDATA%\JBrowser\Logs\jbrowser.log`, or `<profile-dir>\Logs` |
| Build output, repository outside OneDrive | `dist\` and `build\` |
| Build output, repository inside OneDrive | `%LOCALAPPDATA%\JBrowser-build\` |
| Installed JBrowser | `%LOCALAPPDATA%\Programs\JBrowser\` |

The full list is in [data files](../reference/data-files.md).
