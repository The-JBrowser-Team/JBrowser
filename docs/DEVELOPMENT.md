# Development

## Set up once

Requirements: Windows 10 or 11, and [Python 3.14+](https://www.python.org/downloads/) (64-bit) with the `py`
launcher.

```powershell
py -3.14 tools\update_deps.py
```

This creates `.venv`, installs [requirements-build.txt](../requirements-build.txt) (the app plus PyInstaller and
pyflakes), imports every module and runs pyflakes. Run it again whenever you want the newest packages. It upgrades
everything, then proves it still works:

| Command | Does |
|---|---|
| `python tools\update_deps.py` | create or update `.venv`, then verify |
| `python tools\update_deps.py --check` | verify only (imports + pyflakes); installs nothing |
| `python tools\update_deps.py --runtime-only` | skip the build tools |
| `python tools\update_deps.py --lock` | also write `requirements.lock.txt` with exact versions |

## Run

```powershell
.\.venv\Scripts\python.exe main.py                              # your normal profile
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb" # a throw-away profile (recommended for testing)
```

| Option | Purpose |
|---|---|
| `URL …` | Open URLs or search terms as new cards (forwarded to the running window if JBrowser is already open) |
| `--incognito` | Start in a new incognito space |
| `--no-restore` | Start without restoring the previous cards |
| `--profile-dir PATH` | Portable mode: keep all data (profiles, settings, vault) in `PATH` |
| `--debug` | Verbose logging to the console |

"Restart" and "Factory reset" relaunch JBrowser with the same options. An internal `--wait-pid` argument makes the
new copy wait until the old one has closed.

Environment variables that help with testing:

| Variable | Effect |
|---|---|
| `JBROWSER_SKIP_WELCOME=1` | Don't show the first-run welcome |
| `JBROWSER_SKIP_UPDATES=1` | Don't check GitHub for updates |
| `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` | Work around blank or flickering pages on unusual GPUs |

Only one JBrowser runs per data folder, so a test run with its own `--profile-dir` can sit beside your everyday
browser.

## Where to change things

| To… | Edit |
|---|---|
| Add a setting | its default in `DEFAULTS` in `jbrowser/core/settings.py`, and its control in `jbrowser/ui/dialogs/settings.py` |
| Add a command or shortcut | `jbrowser/ui/actions.py` (it then appears in the Lazy Toolbar and the shortcut sheet) |
| Change what a click or command does | `jbrowser/ui/controller.py` (`BrowserController`) |
| Change colours, fonts or surfaces | `jbrowser/ui/theme.py` |
| Change animation timing | `jbrowser/core/motion.py` (all animations respect the *Fluid animations* setting) |
| Change the welcome screen | `jbrowser/ui/onboarding.py` (bump `ONBOARDING_VERSION` to show it again to existing users) |
| Add a Windows API call | `jbrowser/platform/win.py` |
| Inject JavaScript into pages | `jbrowser/engine/js.py` |
| Change the version | `python tools\version.py --set X.Y.Z` (see [RELEASING.md](RELEASING.md)) |

## Code conventions

- Python 3.14 with `from __future__ import annotations` and type hints.
- A module docstring says what the file is for. Classes and non-obvious functions get a one-line docstring.
- Qt signals connect the layers. Services never import widgets.
- Text users read is plain and friendly ("Clear browsing data", not "Purge storage").
- New dialogs subclass `ChromeWindow` (tool windows) or `JDialog` (small modal prompts) so they match the theme.
- Keep `pyflakes` clean. CI runs `tools/update_deps.py --check` on every push.

## Debugging

- Logs: `%APPDATA%\JBrowser\Logs\jbrowser.log` (or `<profile-dir>\Logs`). `--debug` also prints them to the console.
- Web pages: press F12 on a card for Chromium DevTools.
- Qt warnings appear in the log. `QT_LOGGING_RULES="qt.webenginecontext.debug=true"` shows the WebEngine
  configuration.

## Sound effects and the icon

- `assets/sounds/*.wav` are made from source MP3s with `tools/convert_sounds.py` (see [assets/README.md](../assets/README.md)).
- `assets/jbrowser.ico` is rendered from the vector logo by `tools/make_icon.py`. The build does this automatically.
