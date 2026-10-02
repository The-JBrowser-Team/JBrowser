<p align="center">
  <img src="assets/jbrowser.png" width="96" alt="JBrowser logo">
</p>

<h1 align="center">JBrowser</h1>

<p align="center">
  <em>Welcome to the internet - again.</em><br>
  A spatial, privacy-focused web browser for Windows 11.
</p>

<p align="center">
  <a href="https://jbrowser.app/"><b>Website</b></a> ·
  <a href="https://jbrowser.app/download/"><b>Download</b></a> ·
  <a href="https://jbrowser.app/changelog/"><b>Changelog</b></a> ·
  <a href="https://jbrowser.app/docs/"><b>Developer docs</b></a>
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

<p align="center">
  <img src="site/static/img/shots/hero-dark-1920.webp" width="900" alt="JBrowser on Windows 11: the sidebar with favourites and spaces, and two pages side by side on the canvas">
</p>

Made with ❤️ by the JBrowser Team. © 2026 The JBrowser Team.

## Download

JBrowser is free for **Windows 10 and 11**. The easiest way to install it takes about a minute:

1. **Open PowerShell**: press the **Windows** key, type `PowerShell`, and press **Enter**.
2. **Copy this line, paste it into the PowerShell window** (right-click, or <kbd>Ctrl</kbd>+<kbd>V</kbd>) **and press
   Enter**:

   ```powershell
   irm https://raw.githubusercontent.com/The-JBrowser-Team/JBrowser/main/install.ps1 | iex
   ```

3. The JBrowser installer opens. Click through it like any other app.

The command downloads the newest JBrowser from this repository's
[releases](https://github.com/The-JBrowser-Team/JBrowser/releases/latest), checks that the file is exactly the one
published (its SHA-256 fingerprint), and opens the installer. It needs no administrator rights and changes nothing else.
[install.ps1](install.ps1) is short, so you can read it first. Run the same line again at any time to update.

Prefer a normal download? Get **`JBrowser-Setup-<version>.exe`** from the
[latest release](https://github.com/The-JBrowser-Team/JBrowser/releases/latest) and open it. Because JBrowser is new and
not code-signed yet, Windows may say "Windows protected your PC": click *More info*, then *Run anyway*
([why](docs/SIGNING.md)).

## Highlights

- **Spatial canvas.** Cards sit side by side and can be resized, split, reordered and **stacked in columns** of up to
  three. Keep scrolling past either end to pull in a new card.
- **Reading mode** (F9). Articles without the clutter, in serif or sans-serif, in four colour themes.
- **Spaces.** *Home*, *Work*, *Other*, or your own spaces. Each has its own cookies and storage, and you can open
  incognito spaces too. Favourites and pinned cards sit above them.
- **Gallery.** See every card of a space, or of all spaces, at a glance; filter, open, close and move them.
- **Lazy Toolbar** (Ctrl+T / Ctrl+K). One box for addresses, searches, open cards, bookmarks, history, passwords and
  100+ commands.
- **Private by default.** Ad and tracker blocking (EasyList and EasyPrivacy), phishing and malware protection,
  fingerprinting protection, secure DNS (Quad9), HTTPS-first and link cleaning.
- **Built in.** An encrypted password manager, protected downloads (keep-or-delete warnings, or a strict mode that
  blocks risky files), history, the Archive of recently closed cards, DevTools, user scripts and per-space proxies.
- **Light on memory.** Out-of-sight cards stop rendering, and idle cards hibernate.
- **Updates itself.** New versions arrive from GitHub Releases and are verified before they install.

See **[docs/FEATURES.md](docs/FEATURES.md)** for the full list and the keyboard shortcuts.

## Release notes

### 2.0.0 (latest) · 2 October 2026 · [download](https://github.com/The-JBrowser-Team/JBrowser/releases/tag/v2.0.0)

**JBrowser 2.0 is here**, the biggest update yet.

- **Stack cards in columns**: up to three cards on top of each other. Drag a card onto another, or press the new stack
  button on the ribbon (Alt+Shift+S) to choose a new page, an open card, a favourite or a bookmark. Cards in a column
  share one width.
- **Reading mode** (F9): articles without ads or clutter, with your choice of font, colours and text size. JBrowser
  suggests it once when you're reading an article, and never again if you say so.
- **Download protection levels**: *Standard* warns about risky files and lets you keep or delete them; *Strict* blocks
  them. Covers programs, dangerous sites and sites without HTTPS.
- **A cleaner ribbon**: the shield now sits in the address bar, the Downloads button appears only when you download
  something and shows the percentage, and a whole download row opens its file.
- **Google sign-in fixes itself**: *Fix and sign in again*, and JBrowser switches back by itself once you're in.
- **No colour warp** when minimising or maximising, favourites that reopen at the width you left them, and plainer
  language everywhere.

**1.6.2** (2 October 2026): windows that keep their colours, Google sign-in through the whole hand-off, frosted
menus, an update window that keeps its size.

**1.6.1** (1 October 2026): scrolling up and down no longer slides to the next card.

**1.6.0** (1 October 2026):

- **Dark mode stays dark on Acrylic**, even when Windows itself uses light mode (and the other way round).
- **Google sign-in, for good**: while you sign in, JBrowser presents itself as Firefox in every way Google checks.
- **Fewer "I'm not a robot" checks** when you're not signed in to Google.
- **Smoother horizontal scrolling**, especially on slower PCs and large screens.
- **Settings → Advanced**: a graphics mode for cards that glitch, how JBrowser introduces itself, and the (now
  optional) note about videos it can't play.
- A translucent Archive, a cleaner right-click menu, and a livelier website.

### Earlier versions

| Version | Highlights |
|---|---|
| 1.5.4 | Encrypted password export (CSV in an AES-256 ZIP), a calmer Archive, Python 3.14.7 |
| 1.5.3 | The one-line PowerShell install works again, simpler download window, an open-source section on the website, which moved to jbrowser.app |
| 1.5.2 | Sites see the current Chrome (155), Google sign-in pages exempt from blocking, card outline in your tint, saved pages can't read your files, ready for SignPath code signing |
| 1.5.1 | Google sign-in fix (Firefox user agent for Google's sign-in server), code signing built into the release scripts, a website with real screenshots and versioned developer docs |
| 1.5.0 | The Gallery, colour tints, drag cards anywhere, real ad blocking with EasyList and EasyPrivacy, fewer CAPTCHAs |
| 1.4.1 | Setup closes a running JBrowser for you, a 30 MB smaller download, nothing lost when Windows closes JBrowser |
| 1.4.0 | Automatic updates from GitHub, a proper Windows installer, a livelier welcome animation, open source under the GNU GPL v3 |
| 1.2.0 | First-run welcome and guided tour, pull to add a card, favourites and pinned cards, the Archive (closed cards from the last 48 hours), an optional Home button |
| 1.1.0 | Rebuilt Settings, phishing and malware protection, fingerprinting protection, HTTPS-first, download protection, *Clear browsing data* and *Reset* |
| 1.0.0 | First release: the spatial card canvas, isolated Spaces, the Lazy Toolbar, memory saver, secure DNS, tracker blocking and the password manager |

Every change is listed in **[CHANGELOG.md](CHANGELOG.md)**, and each release's notes are on the
[Releases page](https://github.com/The-JBrowser-Team/JBrowser/releases).

## More ways to install

The [one-line install](#download) above is the easiest. It downloads the release zip, checks its SHA-256
fingerprint, and starts the installer, without Windows SmartScreen's "Windows protected your PC" warning.

### Download the zip yourself

1. Open the **[latest release](https://github.com/The-JBrowser-Team/JBrowser/releases/latest)** and download
   **`JBrowser-<version>-<date>.zip`**, for example `JBrowser-1.4.0-2026-09-28.zip`.
2. Extract it, then run **`JBrowser-Setup-<version>.exe`**. `INSTALL.txt` in the zip explains each step.
3. The installer works for your Windows account without administrator rights. It adds a Start menu entry, and it can
   register JBrowser as a web browser so you can make it your default in Windows Settings.

The release page also has the installer on its own (`JBrowser-Setup-<version>.exe`). When a downloaded installer isn't
code-signed, Windows SmartScreen says "Windows protected your PC"; choose *More info → Run anyway*
([why](docs/SIGNING.md)). To uninstall, use *Settings → Apps → Installed apps → JBrowser*. Your data is kept unless you
choose to delete it.

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
covers the command-line options, test profiles, debugging and code conventions, and the
**[developer documentation](https://jbrowser.app/docs/)** explains the architecture, the web
engine, privacy, the UI and the release process for every version, with a generated Python API reference.

## Build and release

You need Python 3.14+, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`)
and, to publish, [GitHub CLI](https://cli.github.com/) signed in with `gh auth login`.
**[master.ps1](master.ps1)** does everything else, from the repository folder:

| Goal | Command |
|---|---|
| Build and package the current version | `.\master.ps1` |
| Release a new version (update) | `.\master.ps1 -Version 1.4.1 -Publish` |
| Rebuild the current version and refresh its release files | `.\master.ps1 -Publish` |

It updates every package and checks every import, builds the app and the installer, and packages them as
**`distribution\JBrowser-<version>-<date>.zip`**. With `-Publish`, it also commits and pushes your changes and publishes
the GitHub release. Installed copies then update themselves, and the one-command install above picks it up. Before
releasing a new version, describe it in [CHANGELOG.md](CHANGELOG.md) and under *Release notes* above.

The steps can also be run on their own (`tools\build_app.ps1`, `tools\build_installer.ps1`, `tools\release.ps1`).
When the repository is inside OneDrive, the build folder is `%LOCALAPPDATA%\JBrowser-build` so OneDrive doesn't sync
it. Guides: [docs/BUILDING.md](docs/BUILDING.md) and [docs/RELEASING.md](docs/RELEASING.md).

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
| [`site/`](site/README.md) | The website: home page, download page, changelog and the versioned developer docs |
| [`.github/`](.github/GITHUB_CONFIG.md) | Continuous integration, the website and signed-release workflows, issue and pull-request templates |
| `.signpath/` | SignPath artifact configurations for code signing ([docs/SIGNING.md](docs/SIGNING.md)) |
| `master.ps1` | Builds, packages and publishes everything in one command |
| `install.ps1` | Installs or updates JBrowser from the latest release zip (the one-command install) |
| `distribution/` | Zips made by `master.ps1` (local only, not in git) |
| `main.py`, `JBrowser.spec` | Entry point and the PyInstaller recipe |
| `requirements*.txt` | Runtime and build dependencies |

## Contributing and security

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md). Please report vulnerabilities privately, as
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
- [Mozilla Readability](https://github.com/mozilla/readability) for reading mode (Apache 2.0, included unmodified in
  [jbrowser/engine/vendor/readability](jbrowser/engine/vendor/readability))

The sound effects are credited in [assets/sounds/CREDITS.txt](assets/sounds/CREDITS.txt).
