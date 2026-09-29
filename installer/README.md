# `installer/`: the Windows installer

[`JBrowser.iss`](JBrowser.iss) is an [Inno Setup 6](https://jrsoftware.org/isinfo.php) script. Build it with
`tools\build_installer.ps1`, which passes the version and folders in, rather than opening it in the Inno Setup IDE.
See [docs/BUILDING.md](../docs/BUILDING.md).

## What the installer does

| | |
|---|---|
| **Installs to** | `%LOCALAPPDATA%\Programs\JBrowser` for the current user, with no administrator prompt and no install-mode question. An administrator can install for all users (Program Files) from the command line: `JBrowser-Setup-<version>.exe /ALLUSERS`. |
| **Shortcuts** | Start menu, plus an optional desktop icon (the *desktopicon* task) |
| **Browser registration** | The *browser* task (on by default) registers JBrowser under `StartMenuInternet` / `RegisteredApplications` with `http`, `https`, `.htm` and `.html` handlers, so it appears in *Settings → Apps → Default apps*. Windows never lets an installer make itself the default without asking. |
| **Upgrades** | Installs over the previous version (same `AppId`), after removing the old `_internal` folder so no stale Qt files remain |
| **Running copy** | Found by the Windows Restart Manager (`CloseApplications=force`). The *Preparing to Install* page offers to close it; JBrowser then saves its session and exits normally, and leftover web-engine helper processes are ended. The last page offers to start JBrowser again. Silent installs close it automatically. |
| **Uninstall while running** | Asks you to close JBrowser first (it checks the `JBrowser.AppMutex` mutex the app holds), so no files are left behind |
| **Silent mode** | `/SILENT` or `/VERYSILENT` installs without questions. The auto-updater also passes JBrowser's own `/RELAUNCH` switch, which starts the new version at the end. |
| **Uninstall** | *Apps & features*. It asks whether to delete your JBrowser data too (default: keep it). A silent uninstall always keeps the data. |
| **Licence page** | Shows [LICENSE](../LICENSE) (GNU GPL v3) |
| **Code signing** | With a code-signing certificate configured, the build passes `/DSignSetup` and a `jbsign` sign tool, and Inno Setup signs Setup and the uninstaller with `tools\sign.ps1` ([docs/SIGNING.md](../docs/SIGNING.md)). Otherwise both are unsigned. |

## Editing tips

- **Never change `AppId`.** Windows uses it to recognise JBrowser. A new value would install a second copy beside
  the old one instead of upgrading it.
- `AppVersion`, `SourceDir` and `OutputDir` come from the build script (`/D…`). The `#ifndef` defaults only
  matter when you compile by hand.
- The output name `JBrowser-Setup-<version>.exe` must stay in that form, because the updater looks for it
  (`INSTALLER_RE` in `jbrowser/services/updater.py`).
- Don't bring back `AppMutex=` in `[Setup]`: it stops Setup with "JBrowser is currently running" and no way to
  continue, which is what 1.4.0 did. The Restart Manager closes JBrowser for the user instead.
- To test changes without touching a real installation, compile a copy with a different `AppId` and `AppName`.
  Otherwise a test install replaces the real one's uninstall entry and Start menu shortcut.
- Command-line switches: see the [Inno Setup documentation](https://jrsoftware.org/ishelp/index.php?topic=setupcmdline).
