---
title: Building the app
nav_title: Building
description: PyInstaller, the build scripts, where the output goes and what the spec leaves out.
---

<!-- if >= 1.4.1 -->
**The short version:** `.\master.ps1` from the repository folder updates the packages, builds the app and the
installer, and packages `distribution\JBrowser-<version>-<date>.zip`. The steps below can also run on their own.
<!-- else -->
**The short version:** `.\tools\build_installer.ps1` builds the app and then the installer.
<!-- endif -->

| Output | Script | Result |
|---|---|---|
| The app (PyInstaller, one folder) | `.\tools\build_app.ps1` | `dist\JBrowser\JBrowser.exe` and its `_internal\` folder |
| The installer (Inno Setup) | `.\tools\build_installer.ps1` | `dist\installer\JBrowser-Setup-<version>.exe` and `.exe.sha256` |
<!-- if >= 1.4.1 -->
| The zip | `.\master.ps1` | `distribution\JBrowser-<version>-<yyyy-MM-dd>.zip` and `.zip.sha256` |
<!-- endif -->

The PowerShell scripts share [tools/common.ps1](source:tools/common.ps1): `$Root`, `$Py` (the `.venv` Python), the
`Step` helper, and where output goes.

## Where the output goes

- normally `dist\` (and `build\` for PyInstaller's temporary files) inside the repository, ignored by git;
- **`%LOCALAPPDATA%\JBrowser-build\`** when the repository is inside **OneDrive**, because OneDrive would upload
  about 450 MB per build and lock files while PyInstaller is still writing them;
- anywhere you like: set `JBROWSER_BUILD_DIR`.

## `tools\build_app.ps1`

```powershell
.\tools\build_app.ps1              # one-folder build (the one the installer uses)
.\tools\build_app.ps1 -SkipDeps    # don't update packages first
.\tools\build_app.ps1 -OneFile     # a single JBrowser.exe (slow to start; not used for releases)
```

1. `tools\update_deps.py` updates and verifies the packages (skipped with `-SkipDeps`).
2. It refuses to continue if JBrowser is running from the build folder, because open files would break the build.
<!-- if >= 1.4.1 -->
3. It clears the previous build, so files from an earlier build can never end up in an installer.
<!-- endif -->
4. `tools\make_icon.py` renders `assets\jbrowser.ico` from the vector logo, and `tools\version.py --sync` writes the
   exe's version resource (`tools\version_info.txt`).
5. PyInstaller builds with [JBrowser.spec](source:JBrowser.spec).
<!-- if >= 1.5.1 -->
6. `tools\sign.ps1` signs `JBrowser.exe` when a code-signing certificate is configured ([code signing](signing.md)).
<!-- endif -->

## The spec

| Choice | Why |
|---|---|
| one folder (`COLLECT`) | starts much faster than one file: Qt WebEngine is about 500 MB unpacked |
| `console=False` | a GUI app: no console window |
| `icon`, `version` | the icon and the details in the file's Properties |
| `collect_submodules("jbrowser")` | dialogs are imported lazily, so PyInstaller must be told about them |
| `PyQt6.QtWebChannel` | provides `qwebchannel.js` for the isolated autofill bridge |
| `PyQt6.QtPrintSupport`, `PyQt6.QtMultimedia` + `assets\sounds` | printing, and the welcome sounds (the FFmpeg plugin is filtered out: sounds use the native backend) |
| `upx=False` | UPX corrupts Qt WebEngine binaries |
<!-- if >= 1.4.1 -->
| the `_needed()` filter | leaves out what a widgets app never loads: Qt Quick 3D/Controls/PDF and similar modules, the QML folder, non-English translations and the debug copy of the DevTools resources. That took the app from 523 MB to 344 MB and the installer from 138 MB to 108 MB. Qt6Quick, Qt6Qml and Qt6QuickWidgets stay: Qt6WebEngineCore links against them.<!-- if >= 2.0.1 --> [[changed 2.0.1]] It also leaves out every debug-build copy of the engine's resources (`*.debug.pak`, `v8_context_snapshot.debug.bin`) and unused plugins (`_UNUSED_PLUGINS`: TIFF, TGA, WBMP and ICNS images, the off-screen and minimal platforms, TUIO touch, NMEA positioning and Qt6SerialPort), another 6 MB on disk.<!-- endif --> |
<!-- endif -->

PyInstaller's PyQt6 hooks bundle `QtWebEngineProcess.exe`, the Chromium `.pak` resources, locales and ICU data. Keep
the whole `dist\JBrowser` folder together.

<!-- if >= 1.4.1 -->
After changing the filter, check nothing needed went missing: every DLL's imports must resolve inside the build, a
page must load, and F12 must open DevTools.
<!-- endif -->

## Checking a build

Run the built `JBrowser.exe` with a throw-away profile and look at: a page loads, DevTools open, a download works,
the welcome sound plays, and it exits cleanly (exit code 0, no `QtWebEngineProcess.exe` left behind). The log is in
`<profile-dir>\Logs\jbrowser.log`.

```powershell
& "$env:LOCALAPPDATA\JBrowser-build\dist\JBrowser\JBrowser.exe" --profile-dir "$env:TEMP\jb-build-test"
```

## Code signing (optional)

<!-- if >= 1.5.1 -->
With a code-signing certificate configured, `build_app.ps1` signs `JBrowser.exe` right after PyInstaller, and the
installer build signs Setup and its uninstaller. See [Code signing and SmartScreen](signing.md).
<!-- else -->
Unsigned installers trigger a SmartScreen warning until they build up a reputation. With a code-signing certificate,
sign `JBrowser.exe` before building the installer, then sign the installer and recompute its `.sha256`:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\JBrowser\JBrowser.exe
```
<!-- endif -->
