# Releasing a new version

A release is a GitHub release tagged `vX.Y.Z` with these files attached:

- `JBrowser-Setup-X.Y.Z.exe` and `JBrowser-Setup-X.Y.Z.exe.sha256`: the installer and its checksum. Installed copies
  of JBrowser look for exactly these (see [AUTO_UPDATE.md](AUTO_UPDATE.md)).
- `JBrowser-X.Y.Z-<yyyy-MM-dd>.zip` and its `.sha256`: the installer, checksum, LICENSE and INSTALL.txt in one
  download. The README's one-command install ([install.ps1](../install.ps1)) uses it.

Publishing a release is all it takes to update everyone.

## One-time setup

```powershell
winget install GitHub.cli          # gh
winget install JRSoftware.InnoSetup
gh auth login                      # choose GitHub.com → HTTPS → sign in with a browser
```

`git` comes from Git for Windows, or from GitHub Desktop, which bundles it (the scripts find either). The scripts push
with the GitHub CLI sign-in, so git needs no separate credentials.

## Every release

1. **Pick the version.** Use `major.minor.patch`: a patch for fixes only, a minor for new features, a major for big
   or breaking changes.
2. **Write the release notes.** In [CHANGELOG.md](../CHANGELOG.md), rename `## [Unreleased]` to
   `## [1.4.1] - YYYY-MM-DD`, or add that section. Its text becomes the GitHub release notes and is what users see
   in the *Update* dialog. Then update **Release notes** in [README.md](../README.md): put a short summary of the
   new version at the top, and move the previous one into the *Earlier versions* table.
3. **Run the master script:**
   ```powershell
   .\master.ps1 -Version 1.4.1 -Publish      # add -Draft to review the release on github.com first
   ```
   It sets the version, updates the packages, builds the app and the installer, and packages
   `distribution\JBrowser-1.4.1-<date>.zip`. It then commits and pushes your changes, tags `v1.4.1`, and publishes the
   release with the notes and all four files. It takes about 5–8 minutes.
4. **Check it.** Open the release page, and in an installed JBrowser use *Settings → About → Check now*.

`.\master.ps1 -Publish` without `-Version` rebuilds the current version and replaces its release files.
`tools\release.ps1` is the publishing step on its own; master.ps1 calls it.

## If something goes wrong

| Problem | Fix |
|---|---|
| "GitHub CLI is not signed in" | `gh auth login` |
| "CHANGELOG.md has no '## [X.Y.Z]' section" | add the section (step 2) |
| "There are uncommitted changes" (`release.ps1` on its own) | commit or discard them, or use `master.ps1 -Publish`, which commits them |
| "Release vX.Y.Z already exists" (`release.ps1` on its own) | set a new version, or use `master.ps1 -Publish` to refresh its files |
| Build failed because JBrowser is running from the build folder | close that copy, then run again |
| Stopped half-way | fix the cause and run the same command again: an existing tag on the same commit is reused |
| Published a bad release | delete it on GitHub, or mark it *pre-release* so the updater ignores it, then ship a new patch version |

A **draft** or **pre-release** is invisible to the updater and to `install.ps1`, because the `releases/latest` API only
returns full releases. Use a pre-release to share a test build without updating everyone.
