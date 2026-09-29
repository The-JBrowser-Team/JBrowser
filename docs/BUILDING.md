# Building

**The short version:** run `.\master.ps1` from the repository root. It updates the packages, builds the app and the
installer, and packages `distribution\JBrowser-<version>-<date>.zip`. See [RELEASING.md](RELEASING.md) for `-Publish`.

Each step also has its own script:

| Output | Script | Result |
|---|---|---|
| The app (PyInstaller, one folder) | `.\tools\build_app.ps1` | `dist\JBrowser\JBrowser.exe` and its `_internal\` folder |
| The installer (Inno Setup) | `.\tools\build_installer.ps1` | `dist\installer\JBrowser-Setup-<version>.exe` and `.exe.sha256` |
| The zip | `.\master.ps1` | `distribution\JBrowser-<version>-<yyyy-MM-dd>.zip` and `.zip.sha256` |

`build_installer.ps1` runs `build_app.ps1` first.

### Where the output goes

`dist\` in this guide means the output folder, which the scripts print as they run:

- normally `dist\` (and `build\` for temporary files) inside the repository, ignored by git;
- **`%LOCALAPPDATA%\JBrowser-build\dist`** when the repository is inside **OneDrive**. Otherwise OneDrive would
  upload about 450 MB per build, and it locks files while PyInstaller is still writing them, which breaks the build;
- any folder you like: set `JBROWSER_BUILD_DIR` before running the scripts.

The rule lives in [tools/common.ps1](../tools/common.ps1), which all the build scripts share.

## Prerequisites

- Python 3.14+ (`tools\update_deps.py` builds `.venv`, and the build scripts call it automatically)
- Inno Setup 6, for the installer only: `winget install JRSoftware.InnoSetup`

## The app: `tools\build_app.ps1`

```powershell
.\tools\build_app.ps1              # one-folder build (recommended: starts fast)
.\tools\build_app.ps1 -SkipDeps    # don't update packages first
.\tools\build_app.ps1 -OneFile     # a single JBrowser.exe (slower to start; not used by the installer)
```

Steps:
1. `tools\update_deps.py`: update the packages and verify imports and lint (skip with `-SkipDeps`).
2. Refuse to continue if JBrowser is running from `dist\`, because the open files would break the build half-way.
3. `tools\make_icon.py` renders the icon, and `tools\version.py --sync` writes the exe's version resource.
4. PyInstaller builds with [JBrowser.spec](../JBrowser.spec).

The spec's choices, and the equivalent command-line flags:

| Setting | Why |
|---|---|
| one-folder (`COLLECT`) | Starts much faster than `--onefile`, because Qt WebEngine is about 500 MB unpacked |
| `console=False` (`--windowed`) | GUI app, no console window |
| `icon`, `version` | Explorer and taskbar icon, plus the details in the file's Properties |
| `collect_submodules("jbrowser")` | Dialogs are imported lazily, so PyInstaller must be told to include them |
| `PyQt6.QtWebChannel` | Provides `qwebchannel.js` for the isolated password-autofill bridge |
| `PyQt6.QtPrintSupport` | Printing |
| `PyQt6.QtMultimedia` + `assets\sounds` | Welcome-screen sounds. The FFmpeg media plugin is filtered out because sounds use the native Windows backend. |
| `upx=False` (`--noupx`) | UPX corrupts Qt WebEngine binaries (`QtWebEngineProcess.exe`, `Qt6WebEngineCore.dll`) |
| `_needed()` filter (spec only) | Leaves out what a widgets app never loads: Qt Quick 3D / Controls / PDF and similar modules, the QML folder, non-English translations and the debug copy of the DevTools resources. That takes the app from 523 MB to 344 MB and the installer from 138 MB to 108 MB. Qt6Quick, Qt6Qml and Qt6QuickWidgets stay, because Qt6WebEngineCore links against them. |

After changing the filter, check that nothing needed went missing: every DLL's imports must resolve inside the build,
a page must load, and F12 must open DevTools. `-OneFile` builds don't use the filter.

PyInstaller's PyQt6 hooks bundle `QtWebEngineProcess.exe`, the Chromium `.pak` resources, locales and ICU data.
Keep the whole `dist\JBrowser` folder together.

## The installer: `tools\build_installer.ps1`

```powershell
.\tools\build_installer.ps1                 # build the app, then the installer
.\tools\build_installer.ps1 -SkipAppBuild   # reuse the existing dist\JBrowser
```

It compiles [installer/JBrowser.iss](../installer/JBrowser.iss) with the version from `jbrowser/__init__.py`,
then writes `JBrowser-Setup-<version>.exe.sha256` in `sha256sum` format (`<hash>  <file name>`). The auto-updater
refuses any download that doesn't match that file.

What the installer does is described in [installer/README.md](../installer/README.md).

### Test an installer without touching your real installation

```powershell
$dir = "$env:TEMP\jb-install-test"
.\dist\installer\JBrowser-Setup-1.4.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="$dir" /TASKS=""
# ... try "$dir\JBrowser.exe" --profile-dir "$env:TEMP\jb-profile" ...
& "$dir\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES
```

`/TASKS=""` skips the desktop icon and the browser registration. Note that the installer's AppId is shared with any
real installation: a test install replaces the recorded location of an existing one, so reinstall afterwards if you
use JBrowser day to day.

## Code signing (optional)

Unsigned installers trigger SmartScreen's "Windows protected your PC" warning when they are downloaded with a
browser. Once a code-signing certificate is configured (environment variables, see [SIGNING.md](SIGNING.md)), the
build signs `JBrowser.exe`, the installer and its uninstaller through `tools\sign.ps1`, and writes the `.sha256` after
signing. Without one, builds are unsigned.
