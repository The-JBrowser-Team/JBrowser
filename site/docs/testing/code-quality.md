---
title: Code quality and CI
nav_title: Code quality and CI
description: The checks every change must pass, locally and on GitHub.
---

## The check

```powershell
.\.venv\Scripts\python.exe tools\update_deps.py --check
```

It must end with *Everything is up to date and importable*. It does two things:

1. **Imports every module** of the `jbrowser` package, and every Qt and third-party module the app uses, in a fresh
   subprocess with `QT_QPA_PLATFORM=offscreen`. A syntax error, a missing import or a module-level mistake in a rarely
   used dialog fails here, not in a user's hands.
2. **Runs pyflakes** over `jbrowser`, `tools` and `main.py`: unused imports and variables, undefined names, shadowed
   names, f-strings without placeholders. The code base is kept at zero warnings.

## Continuous integration

[.github/workflows/ci.yml](source:.github/workflows/ci.yml) runs on every push to `main`, every pull request, and by
hand. On `windows-latest` with Python 3.14 (pip cache keyed on the requirements files) it runs
`python tools/update_deps.py`: a fresh environment with the newest packages, then the same import and pyflakes check.
A pull request is only merged with a green check.
<!-- if main -->

A second workflow, [.github/workflows/pages.yml](source:.github/workflows/pages.yml), builds and deploys this website
([the website](../build/website.md)).
<!-- endif -->

## Conventions the check doesn't enforce

- `from __future__ import annotations` and type hints everywhere; a module docstring in every file.
- Qt signals between layers; no widget imports in `core`, `models` or `services`.
- No blocking work on the UI thread; atomic writes for every file.
- Plain, friendly British English in anything users read.
- Lines under about 120 characters, four-space indentation, LF line endings (CRLF for `.ps1` and `.iss`), as in
  `.editorconfig`.

## Reviewing a change

A reviewer checks that the change:

- keeps the layering ([architecture](../architecture/overview.md)) and goes through `BrowserController` or a command;
- works with *Fluid animations* off, in both themes, and in an incognito space if it touches browsing data;
- never writes personal data for incognito spaces;
- adds a changelog line under `## [Unreleased]` written for users;
- keeps docstrings accurate: the [Python API reference](../api/index.md) is generated from them.
