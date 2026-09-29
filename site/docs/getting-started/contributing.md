---
title: How to contribute code
nav_title: Contributing
description: From a branch to a merged pull request.
---

JBrowser is developed on GitHub at [{{repo_url}}]({{repo_url}}). Changes arrive as pull requests against `main`.
The same text in short form lives in [CONTRIBUTING.md](source:CONTRIBUTING.md).

## 1. Pick something

- Look at the [open issues](repo:issues). Bugs have a reproduction and a JBrowser version.
- For anything larger than a fix, open an issue first and describe what you want to change. It saves you from
  building something that doesn't fit.
- Security problems never go in public issues; see [SECURITY.md](source:SECURITY.md).

## 2. Branch

```powershell
git switch main
git pull
git switch -c short-description
```

## 3. Make the change

Match the code around you:

- `from __future__ import annotations` and type hints on every function.
- A module docstring saying what the file is for; one-line docstrings on classes and non-obvious functions.
  These docstrings are what the [Python API reference](../api/index.md) shows.
- Qt signals connect the layers; services never import widgets.
- New dialogs subclass `ChromeWindow` (tool windows) or `JDialog` (small prompts), so they follow the theme.
- Text users read is plain and friendly, in British English ("colour", "favourites").
- Every animation goes through `motion()` ([motion and animation](../ui/motion.md)).

The [quick reference](quick-reference.md#where-to-make-a-change) says which file to edit for common changes.

## 4. Check it

```powershell
.\.venv\Scripts\python.exe tools\update_deps.py --check
```

This imports every module and runs pyflakes, exactly like CI. Then start JBrowser with a test profile and try what
you changed. [Testing your changes](../testing/testing-changes.md) has a checklist, including incognito spaces,
*Fluid animations* off and both themes.

## 5. Describe it

Add a line under `## [Unreleased]` at the top of [CHANGELOG.md](source:CHANGELOG.md) (create the heading if it is
missing). Write it for users: what changed for them, not which function you edited. The changelog becomes the
release notes and the text of the in-app *Update* dialog.

## 6. Open a pull request

Push the branch and open a pull request. The template asks for a summary and how you tested it. CI runs
`tools/update_deps.py` on Windows with Python 3.14 (see [code quality and CI](../testing/code-quality.md)).

Commits read best as one line saying what changed, followed by the reason if it isn't obvious. Keep unrelated
changes in separate pull requests.

## Licence

By contributing you agree that your contribution is licensed under the
[GNU GPL v3](source:LICENSE), like the rest of JBrowser.
