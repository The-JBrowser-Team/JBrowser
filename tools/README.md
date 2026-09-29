# `tools/`: maintenance scripts

Most of the time you only need **`..\master.ps1`** in the repository root, which runs these in order (dependencies,
build, installer, zip in `distribution\`, and publishing with `-Publish`). The tools below are its individual steps.

Run them from the repository root. The Python tools use `.venv\Scripts\python.exe`, except `update_deps.py`,
which can create `.venv` from any Python 3.14+.

| Tool | What it does | Typical use |
|---|---|---|
| `update_deps.py` | Creates or updates `.venv`, upgrades **all** packages, imports every module and runs pyflakes | `py -3.14 tools\update_deps.py` · `--check` · `--lock` · `--runtime-only` |
| `version.py` | Prints, sets or syncs the version. `jbrowser/__init__.py` is the single source, and `version_info.txt` is generated from it. | `python tools\version.py --set 1.4.1` |
| `build_app.ps1` | Builds `dist\JBrowser\JBrowser.exe` with PyInstaller | `.\tools\build_app.ps1` · `-SkipDeps` · `-OneFile` |
| `build_installer.ps1` | Builds the app, then `dist\installer\JBrowser-Setup-<v>.exe` and its `.sha256` | `.\tools\build_installer.ps1` · `-SkipAppBuild` |
| `release.ps1` | Tags, pushes and publishes the GitHub release that installed copies update to | `.\tools\release.ps1` · `-Draft` · `-SkipBuild` |
| `common.ps1` | Shared by the three `.ps1` scripts: paths, and where build output goes (outside OneDrive, see below) | dot-sourced, not run directly |
| `make_icon.py` | Renders the vector logo into `assets\jbrowser.ico` and `jbrowser.png` | runs during every build |
| `convert_sounds.py` | Converts an MP3 into the WAV format used for UI sounds, and prints its loudness envelope | `python tools\convert_sounds.py in.mp3 assets\sounds\x.wav` |
| `site_screenshots.py` | Photographs the real app in front of a gradient (the canvas, Gallery, Lazy Toolbar, privacy panel, every colour tint, light mode, incognito, the welcome) and converts the pictures for the website. About two and a half minutes; hands off the mouse meanwhile. | `.\.venv\Scripts\python.exe tools\site_screenshots.py` |
| `build_site.py` | Builds the website (home page, download page, changelog and the versioned developer docs) from `site/`, `CHANGELOG.md` and every release tag. Needs `requirements-site.txt`. | `python tools\build_site.py --serve` · `--offline` · `--out DIR` |
| `version_info.txt` | The exe's version resource (generated: don't edit by hand) | written by `version.py --sync` |

`dist\` above is the build output folder. When the repository is inside OneDrive it is
`%LOCALAPPDATA%\JBrowser-build\dist` instead, so OneDrive doesn't sync (and lock) the build. Set `JBROWSER_BUILD_DIR` to
override it.

Guides: [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md), [docs/BUILDING.md](../docs/BUILDING.md) and
[docs/RELEASING.md](../docs/RELEASING.md).

If PowerShell refuses to run the `.ps1` scripts, allow local scripts for your account once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or run a script with
`powershell -ExecutionPolicy Bypass -File tools\build_app.ps1`.
