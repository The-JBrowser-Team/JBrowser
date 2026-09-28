# Releasing a new version

A release is a GitHub release tagged `vX.Y.Z` with two files attached:

- `JBrowser-Setup-X.Y.Z.exe`, the installer
- `JBrowser-Setup-X.Y.Z.exe.sha256`, its checksum

Installed copies of JBrowser look for exactly this (see [AUTO_UPDATE.md](AUTO_UPDATE.md)), so publishing it is all it
takes to update everyone.

## One-time setup

```powershell
winget install GitHub.cli          # gh
winget install JRSoftware.InnoSetup
gh auth login                      # choose GitHub.com → HTTPS → sign in with a browser
```

`git` comes from Git for Windows, or from GitHub Desktop, which bundles it (the scripts find either).

## Every release

1. **Pick the version.** Use `major.minor.patch`: a patch for fixes only, a minor for new features, a major for big
   or breaking changes.
   ```powershell
   .\.venv\Scripts\python.exe tools\version.py --set 1.4.1
   ```
   This updates `jbrowser/__init__.py` (the single source of the version) and `tools/version_info.txt`.
2. **Write the release notes.** In [CHANGELOG.md](../CHANGELOG.md), rename `## [Unreleased]` to
   `## [1.4.1] - YYYY-MM-DD`, or add that section. Its text becomes the GitHub release notes and is what users see
   in the *Update* dialog.
3. **Commit and push** (GitHub Desktop, or `git commit -am "JBrowser 1.4.1"` then `git push`).
4. **Release:**
   ```powershell
   .\tools\release.ps1            # or add -Draft to review it on github.com before publishing
   ```
   The script checks you are signed in and have no uncommitted changes, builds the installer, tags `v1.4.1`, pushes
   the tag, and creates the release with the notes and both files.
5. **Check it.** Open the release page, and in an installed JBrowser use *Settings → About → Check now*.

## If something goes wrong

| Problem | Fix |
|---|---|
| "GitHub CLI is not signed in" | `gh auth login` |
| "There are uncommitted changes" | commit or discard them, then run the script again |
| "Release vX.Y.Z already exists" | releases are never overwritten: set a new version with `tools\version.py --set` |
| "CHANGELOG.md has no '## [X.Y.Z]' section" | add the section (step 2) |
| Build failed because JBrowser is running from `dist\` | close that copy, then run again |
| Published a bad release | delete it on GitHub, or mark it *pre-release* so the updater ignores it, then ship a new patch version |

A **draft** or **pre-release** is invisible to the updater: the `releases/latest` API only returns full releases.
Use a pre-release to share a test build without updating everyone.
