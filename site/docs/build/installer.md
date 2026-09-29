---
title: The installer
description: What JBrowser-Setup.exe does, how it upgrades a running copy, and how to test it safely.
---

The installer is an [Inno Setup 6](https://jrsoftware.org/isinfo.php) script, [installer/JBrowser.iss](source:installer/JBrowser.iss),
compiled by `tools\build_installer.ps1`, which passes in the version and folders (`/D…`) and then writes
`JBrowser-Setup-<version>.exe.sha256` in `sha256sum` format (`<hash>  <file name>`).

## What it does

| | |
|---|---|
| **Installs to** | `%LOCALAPPDATA%\Programs\JBrowser`, for the current user, without an administrator prompt (`PrivilegesRequired=lowest`)<!-- if >= 1.4.1 --> and without asking "for me or for all users"<!-- endif -->. `/ALLUSERS` on the command line installs to Program Files. |
| **Shortcuts** | Start menu, and an optional desktop icon (the `desktopicon` task) |
| **Browser registration** | The `browser` task (on by default) registers JBrowser under `StartMenuInternet` and `RegisteredApplications` with `http`, `https`, `.htm` and `.html` handlers, so it can be chosen in *Settings → Apps → Default apps*. Windows never lets an installer make itself the default. |
| **Upgrades** | Installs over the previous version (same `AppId`), removing the old `_internal` folder first so no stale Qt files remain |
| **Silent mode** | `/SILENT` or `/VERYSILENT`. JBrowser's own `/RELAUNCH` switch starts the new version at the end (the updater uses it) |
| **Uninstall** | From *Apps & features*; asks whether to delete the user's data too (default: keep). A silent uninstall always keeps it. |
| **Requirements** | 64-bit Windows 10 1809 or newer (`MinVersion=10.0.17763`) |

## A running JBrowser

<!-- if >= 1.4.1 -->
Setup uses the **Windows Restart Manager** (`CloseApplications=force`). The *Preparing to Install* page offers to
close JBrowser; Windows then asks it to close, JBrowser saves its session and exits in order
([when Windows closes JBrowser](../architecture/startup-shutdown.md#when-windows-closes-jbrowser)), and any leftover
web-engine processes are ended. The last page offers to start JBrowser again. Silent installs close it automatically.

The uninstaller still refuses to run while JBrowser is open: it checks the `JBrowser.AppMutex` mutex the app holds, so
no files are left behind.

!!! warning "Don't bring back `AppMutex=` in `[Setup]`"
    That is what 1.4.0 did: Setup stopped with "JBrowser is currently running" and no way to continue.
<!-- else -->
`AppMutex=JBrowser.AppMutex` in `[Setup]` makes Setup refuse to continue while JBrowser is running ("JBrowser is
currently running"). The user must close JBrowser and start Setup again.

!!! note "Changed in 1.4.1"
    1.4.1 replaced the mutex check with the Windows Restart Manager, which offers to close JBrowser, and JBrowser
    learned to save everything when Windows asks it to close.
<!-- endif -->

## Editing the script

- **Never change `AppId`.** Windows recognises JBrowser by it; a new value installs a second copy instead of
  upgrading.
- The output name `JBrowser-Setup-<version>.exe` must keep that form: the updater looks for it (`INSTALLER_RE` in
  [services/updater.py](source:jbrowser/services/updater.py)).
- `AppVersion`, `SourceDir` and `OutputDir` come from the build script; the `#ifndef` defaults only matter when
  compiling by hand.
- `.iss` files use CRLF line endings (see `.editorconfig`).

## Testing without touching a real installation

A test install with the real `AppId` replaces the uninstall entry and shortcuts of the JBrowser you use every day.
Compile a copy of the script with a **different `AppId` and `AppName`**, install that into a temporary folder, try it,
and uninstall it:

```powershell
$dir = "$env:TEMP\jb-install-test"
.\JBrowser-Test-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="$dir" /TASKS=""
& "$dir\JBrowser.exe" --profile-dir "$env:TEMP\jb-install-profile"
& "$dir\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES
```

`/TASKS=""` skips the desktop icon and the browser registration.
