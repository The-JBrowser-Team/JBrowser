# How auto-update works

Code: [`jbrowser/services/updater.py`](../jbrowser/services/updater.py) (the logic),
[`jbrowser/ui/dialogs/update.py`](../jbrowser/ui/dialogs/update.py) (the dialog) and `UpdateChip` in
[`jbrowser/ui/titlebar.py`](../jbrowser/ui/titlebar.py) (the ribbon button).

## The flow

1. **Check.** 15 seconds after start-up, and then every hour, JBrowser checks whether a day has passed since the
   last check. If so it calls the GitHub Releases API:
   ```
   GET https://api.github.com/repos/The-JBrowser-Team/JBrowser/releases/latest
   ```
   The repository is `GITHUB_REPO` in `jbrowser/__init__.py`. The request sends no personal data, only a
   `User-Agent` of `JBrowser/<version>`. Anonymous API calls are limited to 60 an hour per IP address, which a
   once-a-day check stays well within.
2. **Compare.** The release tag (`v1.4.1`) is compared with `__version__`. If it is newer, an **Update** button
   appears on the ribbon and a notice is shown (unless the user chose *Skip this version* for it).
3. **Download.** Clicking *Install and restart* fetches `JBrowser-Setup-<version>.exe.sha256` first, then streams
   the installer to `%TEMP%\JBrowser-Update\` while hashing it. A file whose SHA-256 doesn't match, or that grows past
   1 GB, is deleted and never run. Downloads come only from the release's own asset URLs, and redirects may not
   downgrade from HTTPS.
4. **Install.** JBrowser starts a hidden PowerShell helper and closes itself. The helper waits for the JBrowser
   process and its `QtWebEngineProcess.exe` children to exit, then runs the installer with
   `/SILENT /SUPPRESSMSGBOXES /NORESTART /SP- /RELAUNCH`. Inno Setup replaces the program files, and `/RELAUNCH`
   (JBrowser's own switch, handled in `installer/JBrowser.iss`) starts the new version.
   User data in `%APPDATA%\JBrowser` is never touched.

If JBrowser is still running when the installer starts, the installer sees the `JBrowser.AppMutex` named mutex and
closes it first.

## Which copies update themselves

| Copy | Behaviour |
|---|---|
| Installed with `JBrowser-Setup.exe` (`unins000.exe` beside `JBrowser.exe`) | Downloads, verifies and installs |
| A plain `dist\JBrowser` build, or running from source | Reports new versions and offers *Open the download page* |

## Settings

| Key | Default | Meaning |
|---|---|---|
| `updates.auto_check` | `true` | Check automatically once a day (*Settings → About*) |
| `updates.last_check` | `0` | Unix time of the last successful check |
| `updates.skipped` | `""` | A version the user chose to skip (a manual *Check now* still shows it) |

## States

`idle` → `checking` → `uptodate` | `available` | `error`, and from `available`: `downloading` → `ready` (or `error`).
`UpdateService.stateChanged` announces every change. The chip, the dialog and the About page all follow it.

## Testing

- **Against the live repository:** install a release, set `__version__` lower in a source run, or install an older
  release, then use *Settings → About → Check now*.
- **Without network calls:** set `JBROWSER_SKIP_UPDATES=1`.
- **Unit-level:** `parse_version`, `is_newer` and `UpdateService._parse_release(<release JSON>)` are pure functions.
  Feed them a saved response from the API URL above.

## Changing the repository

Edit `GITHUB_REPO` in `jbrowser/__init__.py`. Copies that are already installed keep checking the old repository
until they update to a build that has the new value. Before moving, publish one last release in the old repository
that points to the new one.
