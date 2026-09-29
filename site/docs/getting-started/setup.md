---
title: Setting up a development environment
nav_title: Setting up
description: Install the tools, create the virtual environment and run JBrowser from source.
---

JBrowser runs straight from its source code: there is no compile step. Setting up takes three commands and a few
minutes, most of it downloading Qt WebEngine (about 400 MB).

## Requirements

| What | Why | Get it |
|---|---|---|
| Windows 10 or 11, 64-bit | JBrowser uses Windows APIs directly (DWM backdrops, DPAPI, the window frame) | |
| Python 3.14 or newer, 64-bit, with the `py` launcher | The code uses Python 3.14 | [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.14` |
| Git | To clone the repository | [Git for Windows](https://git-scm.com/download/win), or GitHub Desktop, which bundles it |
| Inno Setup 6 *(optional)* | Only to build the installer | `winget install JRSoftware.InnoSetup` |
| GitHub CLI *(optional)* | Only to publish releases | `winget install GitHub.cli`, then `gh auth login` |

Other operating systems are not supported: `jbrowser/platform/win.py` calls the Win32 API through `ctypes`, and the
window relies on Windows 11 system backdrops.

## Get the code and the packages

```powershell
git clone https://github.com/The-JBrowser-Team/JBrowser.git
cd JBrowser
py -3.14 tools\update_deps.py
```

[`tools/update_deps.py`](source:tools/update_deps.py) does everything else:

1. creates `.venv` with the Python that runs it, if it doesn't exist yet;
2. upgrades pip and installs [`requirements-build.txt`](source:requirements-build.txt): the app's packages from
   [`requirements.txt`](source:requirements.txt) plus PyInstaller and pyflakes;
3. imports every module of the `jbrowser` package and every Qt module the app uses, so a broken package shows up now
   rather than when someone opens a dialog;
4. runs pyflakes over `jbrowser`, `tools` and `main.py`.

Run it again at any time to update every package to its newest version. It prints the installed versions at the end.

## Run JBrowser

```powershell
.\.venv\Scripts\python.exe main.py                                  # your normal profile
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-dev"  # a throw-away profile
```

`python -m jbrowser` works too. Use a throw-away `--profile-dir` while developing: everything JBrowser stores then
goes into that folder, it can run next to your everyday JBrowser, and deleting the folder resets it. See
[the command line](../reference/command-line.md) for every option.

On a new profile the first-run welcome appears. Set `JBROWSER_SKIP_WELCOME=1` to skip it, and
`JBROWSER_SKIP_UPDATES=1` so a development copy never asks GitHub for updates:

```powershell
$env:JBROWSER_SKIP_WELCOME = "1"; $env:JBROWSER_SKIP_UPDATES = "1"
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-dev" --debug
```

`--debug` also prints the log to the console.

## Editor

Any editor works. Point it at the interpreter in `.venv\Scripts\python.exe` so imports resolve. The repository's
[`.editorconfig`](source:.editorconfig) sets UTF-8, LF line endings (CRLF for `.ps1` and `.iss` files), four-space
indentation and a final newline; most editors read it automatically. Lines are kept under about 120 characters.

In VS Code, the Python extension picks up `.venv` by itself. A launch configuration that runs `main.py` with
`--profile-dir` gives you breakpoints in the UI code.

## Next steps

- Keep the [contributor quick reference](quick-reference.md) open while you work.
- Read the [architecture overview](../architecture/overview.md) before a larger change.
- [How to contribute code](contributing.md) explains branches, checks and pull requests.
