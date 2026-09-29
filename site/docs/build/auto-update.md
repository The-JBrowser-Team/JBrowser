---
title: Automatic updates
nav_title: Automatic updates
description: How an installed JBrowser finds, verifies and installs a new release.
---

Code: [`services/updater.py`](source:jbrowser/services/updater.py) (the logic),
[`ui/dialogs/update.py`](source:jbrowser/ui/dialogs/update.py) (the dialog) and `UpdateChip` in
[`ui/titlebar.py`](source:jbrowser/ui/titlebar.py) (the ribbon button).

## The flow

1. **Check.** 15 seconds after start-up, and then every hour, [`UpdateService`](api:jbrowser.services.updater.UpdateService)
   checks whether a day has passed since the last check (`updates.last_check`). If so it asks the GitHub API:
   ```text
   GET https://api.github.com/repos/The-JBrowser-Team/JBrowser/releases/latest
   ```
   The repository is `GITHUB_REPO` in `jbrowser/__init__.py`. The request carries no personal data, only a
   `User-Agent` of `JBrowser/<version>`. Anonymous API calls are limited to 60 an hour per IP address, far more than
   a daily check needs.
2. **Compare.** `parse_version()` reads the tag (`v1.5.0` → `(1, 5, 0)`) and `is_newer()` compares it with
   `__version__`. If it is newer, and the user hasn't chosen *Skip this version* for it (`updates.skipped`), the
   ribbon shows an **Update** button and a notice.
3. **Download.** *Install and restart* first fetches `JBrowser-Setup-<version>.exe.sha256`, then streams the
   installer to `%TEMP%\JBrowser-Update\` while hashing it. A file whose SHA-256 doesn't match, or that grows past
   `MAX_INSTALLER_BYTES` (1 GB), is deleted and never run. Downloads come only from the release's own asset URLs,
   and redirects may not downgrade from HTTPS.
4. **Install.** JBrowser starts a hidden PowerShell helper and closes itself. The helper waits for JBrowser and its
   `QtWebEngineProcess.exe` children to exit, then runs the installer with
   `/SILENT /SUPPRESSMSGBOXES /NORESTART /SP- /RELAUNCH`. Inno Setup replaces the program files and `/RELAUNCH` starts
   the new version. User data in `%APPDATA%\JBrowser` is never touched.

All network I/O is asynchronous (`QNetworkAccessManager`); nothing blocks the UI.

## States

```text
idle → checking → uptodate | available | error
                   available → downloading → ready (or error)
```

`UpdateService.stateChanged(state)` announces every change; the chip, the dialog and *Settings → About* follow it.
<!-- if >= 1.4.1 -->
*Check for updates* while a download is running shows its progress instead of starting a second check.
<!-- endif -->

## Which copies update themselves

| Copy | Behaviour |
|---|---|
| installed with `JBrowser-Setup.exe` (`unins000.exe` next to `JBrowser.exe`) | downloads, verifies and installs |
| a plain `dist\JBrowser` build, or running from source | reports new versions and offers *Open the download page* |

## Settings

| Key | Default | Meaning |
|---|---|---|
| `updates.auto_check` | `true` | check automatically once a day (*Settings → About*) |
| `updates.last_check` | `0` | Unix time of the last successful check |
| `updates.skipped` | `""` | a version the user chose to skip (a manual check still shows it) |

## Testing

- **Against the live repository:** run from source with `__version__` set lower, or install an older release, then
  use *Settings → About → Check now*.
- **Without network calls:** set `JBROWSER_SKIP_UPDATES=1`.
- **Unit level:** `parse_version`, `is_newer` and `UpdateService._parse_release(<release JSON>)` are pure functions;
  feed them a saved response from the API.

## Changing the repository

Edit `GITHUB_REPO` in `jbrowser/__init__.py`. Installed copies keep checking the old repository until they update to
a build with the new value, so publish one last release in the old repository that points to the new one.
