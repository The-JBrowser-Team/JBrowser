---
title: Dependencies
description: The packages JBrowser needs, how tools/update_deps.py manages them, and how to add one.
---

## Runtime packages

[`requirements.txt`](source:requirements.txt):

| Package | Used for |
|---|---|
| **PyQt6** | Qt 6 widgets, networking, multimedia, printing |
| **PyQt6-WebEngine** | Qt WebEngine (Chromium) and `QWebEngineView` |
<!-- if < 2.0.3 -->
| **pywinstyles** | small Windows styling helpers |
<!-- endif -->
| **requests** | background downloads of the filter and threat lists |
| **cryptography** | AES-GCM and Scrypt for the password vault |

The Qt and Chromium binaries come with `PyQt6-Qt6` and `PyQt6-WebEngine-Qt6`, which pip installs as dependencies.
Chromium security fixes therefore reach JBrowser through new PyQt6-WebEngine releases.

## Build and developer tools

[`requirements-build.txt`](source:requirements-build.txt) adds **PyInstaller** (the build) and **pyflakes** (the lint
check) to the runtime packages.
<!-- if main -->
[`requirements-site.txt`](source:requirements-site.txt) holds **Markdown** and **Pygments** for this website; they
are not needed to run or build JBrowser.
<!-- endif -->

## `tools/update_deps.py`

[`tools/update_deps.py`](source:tools/update_deps.py) is the one tool for the environment:

| Command | Does |
|---|---|
| `py -3.14 tools\update_deps.py` | creates `.venv` if needed, upgrades pip and **every** package in `requirements-build.txt` to its newest version (`--upgrade-strategy eager`), then verifies |
| `… --check` | verifies only: imports every module, runs pyflakes; installs nothing (this is what CI runs) |
| `… --runtime-only` | installs `requirements.txt` only, without PyInstaller and pyflakes |
| `… --lock` | also writes `requirements.lock.txt` with the exact installed versions |

"Verify" means: import every Qt module JBrowser uses and **every module of the `jbrowser` package** in a subprocess
(with `QT_QPA_PLATFORM=offscreen`), then run pyflakes over `jbrowser`, `tools` and `main.py`. A missing or broken
package fails here, not when a user opens a rarely used dialog. The versions of the main packages are printed at the
end.

<!-- if >= 1.5.0 -->
## The lock file

`requirements.lock.txt` pins the exact versions of the last `--lock` run. Releases are built from freshly updated
packages; the lock file records what a release was built with, and `pip install -r requirements.lock.txt` recreates
that environment exactly when a build needs to be reproduced.
<!-- endif -->

## Adding a package

1. Prefer the standard library and Qt. Every package ends up in the installer and in the licence notices.
2. Add it to `requirements.txt` (runtime) or `requirements-build.txt` (tools only) with a minimum version, and add its
   top-level module to `REQUIRED_IMPORTS` in `tools/update_deps.py` if the app imports it.
3. Check the licence is compatible with the GPL v3 and list it in the README's licence section.
4. Run `tools\update_deps.py`, then build the app and check the package is bundled (PyInstaller hooks usually
   handle it; otherwise add it to `hiddenimports` in `JBrowser.spec`).

## Security updates

Run `tools\update_deps.py` before every release (`master.ps1` does it automatically), and watch
[PyQt6-WebEngine releases](https://pypi.org/project/PyQt6-WebEngine/) for Chromium security fixes; a new
PyQt6-WebEngine is a reason for a patch release on its own.
