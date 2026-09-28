<p align="center">
  <img src="assets/jbrowser.png" width="96" alt="JBrowser logo">
</p>

<h1 align="center">JBrowser</h1>

<p align="center">
  <em>Welcome to the internet - again.</em><br>
  A spatial, privacy-focused web browser for Windows 11.
</p>

<p align="center">
  <a href="https://github.com/The-JBrowser-Team/JBrowser/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/The-JBrowser-Team/JBrowser?label=download"></a>
  <a href="LICENSE"><img alt="Licence: GPL v3" src="https://img.shields.io/badge/licence-GPL%20v3-blue"></a>
  <img alt="Windows 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB">
</p>

JBrowser replaces the tab strip with an **infinite horizontal canvas of web cards** and organises them into
**isolated Spaces**, driven from a vertical sidebar and a keyboard-first **Lazy Toolbar**. It runs in a
native-feeling Windows 11 window with an Acrylic or Mica backdrop, and it is built with Python and
PyQt6 / Qt WebEngine (Chromium).

Made with ❤️ by the JBrowser Company. © 2026 The JBrowser Company.

## Highlights

- **Spatial canvas.** Cards sit side by side and can be resized, split and reordered. Keep scrolling past either end
  to pull in a new card.
- **Spaces.** *Home*, *Work*, *Other*, or your own spaces. Each has its own cookies and storage, and you can open
  incognito spaces too. Favourites and pinned cards sit above them.
- **Lazy Toolbar** (Ctrl+T / Ctrl+K). One box for addresses, searches, open cards, bookmarks, history, passwords and
  100+ commands.
- **Private by default.** Tracker blocking, phishing and malware protection, fingerprinting protection, secure DNS
  (Quad9), HTTPS-first and link cleaning.
- **Built in.** An encrypted password manager, downloads, history, the Archive of recently closed cards, DevTools,
  user scripts and per-space proxies.
- **Light on memory.** Out-of-sight cards stop rendering, and idle cards hibernate.
- **Updates itself.** New versions arrive from GitHub Releases and are verified before they install.

See **[docs/FEATURES.md](docs/FEATURES.md)** for the full list and the keyboard shortcuts, and
**[CHANGELOG.md](CHANGELOG.md)** for what changed in each version.

## Install

1. Download **`JBrowser-Setup-<version>.exe`** from the
   [latest release](https://github.com/The-JBrowser-Team/JBrowser/releases/latest).
2. Run it. It installs for your Windows account without asking for administrator rights, adds a Start menu entry,
   and can register JBrowser as a web browser so you can make it your default in Windows Settings.
3. To uninstall, use *Settings → Apps → Installed apps → JBrowser*. Your data is kept unless you choose to delete it.

Windows SmartScreen may warn about an unrecognised app, because the installer is not code-signed. Choose
*More info → Run anyway*. You can check the download against the `.sha256` file published beside it.

### Updates

An installed JBrowser checks GitHub once a day. When a new version is out, an **Update** button appears on the ribbon.
Click it to read what's new, then choose *Install and restart*. You can also use *Settings → About → Check now*, or
turn automatic checks off there. [docs/AUTO_UPDATE.md](docs/AUTO_UPDATE.md) explains how updating works.

## Run from source

You need Windows 10 or 11 and [Python 3.14+](https://www.python.org/downloads/) (64-bit).

```powershell
git clone https://github.com/The-JBrowser-Team/JBrowser.git
cd JBrowser
py -3.14 tools\update_deps.py        # creates .venv, installs everything and checks every import
.\.venv\Scripts\python.exe main.py
```

Run `tools\update_deps.py` again at any time to update all packages. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
covers the command-line options, test profiles, debugging and code conventions.

## Build and release

| Goal | Command | Output |
|---|---|---|
| Build the app | `.\tools\build_app.ps1` | `dist\JBrowser\JBrowser.exe` |
| Build the installer | `.\tools\build_installer.ps1` | `dist\installer\JBrowser-Setup-<version>.exe` + `.sha256` |
| Publish a release | `.\tools\release.ps1` | a GitHub release, which installed copies update to |

Guides: [docs/BUILDING.md](docs/BUILDING.md) and [docs/RELEASING.md](docs/RELEASING.md).

## Repository layout

| Path | What's inside |
|---|---|
| [`jbrowser/`](jbrowser/README.md) | The application package: start-up, dependency wiring and file locations |
| [`jbrowser/core/`](jbrowser/core/README.md) | Building blocks with no UI: settings, commands, motion, fuzzy search, URL handling |
| [`jbrowser/models/`](jbrowser/models/README.md) | The browser state: spaces, cards and the per-frame update pipeline |
| [`jbrowser/services/`](jbrowser/services/README.md) | Features without widgets: history, passwords, privacy, network, updates and more |
| [`jbrowser/engine/`](jbrowser/engine/README.md) | Qt WebEngine integration: per-space profiles, pages, lifecycle, injected scripts |
| [`jbrowser/platform/`](jbrowser/platform/README.md) | Windows-specific code: backdrops, window frame, DPAPI |
| [`jbrowser/ui/`](jbrowser/ui/README.md) | Every widget: window, canvas, cards, sidebar, Lazy Toolbar, welcome |
| [`jbrowser/ui/dialogs/`](jbrowser/ui/dialogs/README.md) | Settings and the tool windows (history, passwords, downloads, and more) |
| [`assets/`](assets/README.md) | Icon, logo and sound effects bundled with the app |
| [`installer/`](installer/README.md) | The Inno Setup script for `JBrowser-Setup.exe` |
| [`tools/`](tools/README.md) | Scripts for dependencies, versions, icons, builds and releases |
| [`docs/`](docs/README.md) | Features, architecture, development, building, releasing and updates |
| [`.github/`](.github/README.md) | Continuous integration, issue and pull-request templates |
| `main.py`, `JBrowser.spec` | Entry point and the PyInstaller recipe |
| `requirements*.txt` | Runtime and build dependencies |

## Contributing and security

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Please report vulnerabilities privately, as
described in [SECURITY.md](SECURITY.md).

## Licence

JBrowser is free software under the **[GNU General Public License v3.0](LICENSE)**. You may use, study, share and
modify it, and anything you distribute that is based on it must stay under the same licence.

It builds on these projects, each under its own licence:
- [PyQt6 and PyQt6-WebEngine](https://www.riverbankcomputing.com/software/pyqt/) (GPL v3)
- [Qt 6 and Qt WebEngine](https://www.qt.io/), which includes [Chromium](https://www.chromium.org/) (LGPL v3 and
  Chromium's BSD-style licences)
- [cryptography](https://cryptography.io/) (Apache 2.0 or BSD)
- [requests](https://requests.readthedocs.io/) (Apache 2.0)
- [pywinstyles](https://github.com/Akascape/py-window-styles) (CC0)

The sound effects are credited in [assets/sounds/CREDITS.txt](assets/sounds/CREDITS.txt).
