---
title: Releasing
description: Versions, release notes, and publishing a GitHub release that every installed copy picks up.
---

A release is a **GitHub release tagged `vX.Y.Z`** with these files attached:

- `JBrowser-Setup-X.Y.Z.exe` and `JBrowser-Setup-X.Y.Z.exe.sha256`: the installer and its checksum. Installed copies
  look for exactly these ([automatic updates](auto-update.md)).
<!-- if >= 1.4.1 -->
- `JBrowser-X.Y.Z-<yyyy-MM-dd>.zip` and its `.sha256`: the installer, checksum, LICENSE and INSTALL.txt in one
  download, used by the one-command install ([install.ps1](source:install.ps1)).
<!-- endif -->

Publishing the release is all it takes to update everyone.

## One-time setup

```powershell
winget install GitHub.cli
winget install JRSoftware.InnoSetup
gh auth login                      # GitHub.com → HTTPS → sign in with a browser
```

`git` can come from Git for Windows or from GitHub Desktop, which bundles it; the scripts find either. They push with
the GitHub CLI's sign-in, so git needs no credentials of its own.

## The version

[`jbrowser/__init__.py`](source:jbrowser/__init__.py) holds `__version__`, the single source of truth. The build,
the installer, the exe's version resource and the updater all read it.

```powershell
.\.venv\Scripts\python.exe tools\version.py              # print it
.\.venv\Scripts\python.exe tools\version.py --set 1.5.1  # set it (also rewrites tools\version_info.txt)
```

Versions are `major.minor.patch`: a patch for fixes only, a minor for new features, a major for big or breaking
changes.

## Every release

1. **Write the release notes.** In [CHANGELOG.md](source:CHANGELOG.md), rename `## [Unreleased]` to
   `## [X.Y.Z] - YYYY-MM-DD`, or add that section. Its text becomes the GitHub release notes, the text of the in-app
   *Update* dialog and the [changelog page](../../../changelog/index.html) of this website. Write it for users.
<!-- if >= 1.4.1 -->
2. **Update the README.** Put a short summary at the top of *Release notes* and move the previous version into the
   *Earlier versions* table.
3. **Run the master script:**
   ```powershell
   .\master.ps1 -Version X.Y.Z -Publish      # add -Draft to review the release on github.com first
   ```
   It sets the version, updates every package, builds the app and the installer, packages the zip, commits and
   pushes any changes, tags `vX.Y.Z`, and publishes the release with the notes and all four files. It takes about
   10 minutes, most of it PyInstaller and Inno Setup.
4. **Check it.** Open the release page, and in an installed JBrowser use *Settings → About → Check now*.

`.\master.ps1 -Publish` without `-Version` rebuilds the current version and replaces its release files.
`tools\release.ps1` is the publishing step on its own.
<!-- else -->
2. **Set the version and commit:**
   ```powershell
   .\.venv\Scripts\python.exe tools\version.py --set X.Y.Z
   git commit -am "JBrowser X.Y.Z"
   git push
   ```
3. **Release:**
   ```powershell
   .\tools\release.ps1            # add -Draft to review it on github.com first
   ```
   The script checks the GitHub sign-in and that the working tree is clean, builds the installer, tags `vX.Y.Z`,
   pushes the tag and creates the release with the notes and both files.
4. **Check it.** Open the release page, and in an installed JBrowser use *Settings → About → Check now*.
<!-- endif -->

## If something goes wrong

| Problem | Fix |
|---|---|
| "GitHub CLI is not signed in" | `gh auth login` |
| "CHANGELOG.md has no '## [X.Y.Z]' section" | add it (step 1) |
| "There are uncommitted changes" (`release.ps1` alone) | commit or discard them<!-- if >= 1.4.1 -->, or use `master.ps1 -Publish`, which commits them<!-- endif --> |
| "Release vX.Y.Z already exists" | set a new version<!-- if >= 1.4.1 -->, or use `master.ps1 -Publish` to refresh its files<!-- endif --> |
| The build fails because JBrowser runs from the build folder | close that copy and run again |
| It stopped half-way | fix the cause and run the same command again: a tag already on this commit is reused |
| A bad release is out | delete it on GitHub, or mark it *pre-release* so the updater ignores it, then ship a patch |

!!! tip "Windows PowerShell and native tools"
    Run the scripts directly. Redirecting all their output (`*>&1`) in Windows PowerShell 5.1 turns a native tool's
    progress messages on stderr (PyInstaller's, for example) into errors, and the scripts stop at the first one.

A **draft** or **pre-release** is invisible to the updater<!-- if >= 1.4.1 --> and to `install.ps1`<!-- endif -->, because
GitHub's `releases/latest` API only returns full releases. Use a pre-release to share a test build without updating
everyone.
<!-- if main -->

## The website

The Pages workflow rebuilds this website when a release is published, so the download buttons and the changelog
follow automatically ([the website](website.md)).
<!-- endif -->
