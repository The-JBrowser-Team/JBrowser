# Contributing to JBrowser

Thank you for helping. This page explains how to set up, where things go and what a good change looks like.

## Set up

```powershell
git clone https://github.com/The-JBrowser-Team/JBrowser.git
cd JBrowser
py -3.14 tools\update_deps.py          # .venv + all packages + import and lint checks
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-dev"
```

Use `--profile-dir` with a throw-away folder so testing never touches your real browsing data.
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) has the details.

## Find your way around

- The [developer documentation](https://jbrowser.app/docs/) covers the architecture, the
  web engine, privacy, the UI, building and releasing, with a Python API reference generated from the code.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains the layers and how data flows between them.
- Every folder has a `README.md` listing its files and what each is for.
- Most user-facing behaviour starts in `jbrowser/ui/controller.py` (`BrowserController`) or a command in
  `jbrowser/ui/actions.py`. Search for the command's title to find it.

## Make a change

1. Branch from `main`: `git switch -c short-description`.
2. Keep the layering. `core` and `models` never import `ui`. Services talk to the UI through Qt signals. UI widgets
   do not reach into each other; they go through `BrowserController` or the command registry.
3. Match the surrounding code: type hints, `from __future__ import annotations`, short docstrings, Qt signals over
   callbacks, and plain-language text for anything users read.
4. New setting? Add its default to `DEFAULTS` in `jbrowser/core/settings.py`, and a control with an explanation in
   `jbrowser/ui/dialogs/settings.py`.
5. New shortcut or palette action? Register it in `jbrowser/ui/actions.py`. It then appears in the Lazy Toolbar and
   the shortcut sheet automatically.
6. Before committing:
   ```powershell
   .\.venv\Scripts\python.exe tools\update_deps.py --check   # every module imports, pyflakes is clean
   ```
   Then start the app and try what you changed, including in an incognito space if it touches browsing data.
7. Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), creating that heading at the top if it is
   missing.
8. Open a pull request. The template asks for a summary and how you tested it, and CI runs the same checks.

## Report a bug or ask for a feature

Use the issue templates on GitHub. For bugs, include the JBrowser version (Settings → About), the Windows version,
steps to reproduce and, if possible, the end of `%APPDATA%\JBrowser\Logs\jbrowser.log`.

Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Licence

By contributing you agree that your contribution is licensed under the [GNU GPL v3](LICENSE), like the rest of
JBrowser.
