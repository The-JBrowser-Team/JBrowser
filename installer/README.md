# `installer/`: the Windows installer

[`JBrowser.iss`](JBrowser.iss) is an [Inno Setup 6](https://jrsoftware.org/isinfo.php) script. Build it with
`tools\build_installer.ps1`, which passes the version and folders in, rather than opening it in the Inno Setup IDE.
See [docs/BUILDING.md](../docs/BUILDING.md).

## What the installer does

| | |
|---|---|
| **Installs to** | `%LOCALAPPDATA%\Programs\JBrowser` for the current user, with no administrator prompt. *Install for all users* on the first page is still offered and uses Program Files. |
| **Shortcuts** | Start menu, plus an optional desktop icon (the *desktopicon* task) |
| **Browser registration** | The *browser* task (on by default) registers JBrowser under `StartMenuInternet` / `RegisteredApplications` with `http`, `https`, `.htm` and `.html` handlers, so it appears in *Settings → Apps → Default apps*. Windows never lets an installer make itself the default without asking. |
| **Upgrades** | Installs over the previous version (same `AppId`), after removing the old `_internal` folder so no stale Qt files remain |
| **Running copy** | Detected through the `JBrowser.AppMutex` mutex, and closed before files are replaced |
| **Silent mode** | `/SILENT` or `/VERYSILENT` installs without questions. The auto-updater also passes JBrowser's own `/RELAUNCH` switch, which starts the new version at the end. |
| **Uninstall** | *Apps & features*. It asks whether to delete your JBrowser data too (default: keep it). A silent uninstall always keeps the data. |
| **Licence page** | Shows [LICENSE](../LICENSE) (GNU GPL v3) |

## Editing tips

- **Never change `AppId`.** Windows uses it to recognise JBrowser. A new value would install a second copy beside
  the old one instead of upgrading it.
- `AppVersion`, `SourceDir` and `OutputDir` come from the build script (`/D…`). The `#ifndef` defaults only
  matter when you compile by hand.
- The output name `JBrowser-Setup-<version>.exe` must stay in that form, because the updater looks for it
  (`INSTALLER_RE` in `jbrowser/services/updater.py`).
- Command-line switches: see the [Inno Setup documentation](https://jrsoftware.org/ishelp/index.php?topic=setupcmdline).
