---
title: Persistence and data files
nav_title: Persistence
description: How JBrowser stores its data without ever leaving a half-written file.
---

JBrowser keeps everything it knows in a handful of files in the data folder (`%APPDATA%\JBrowser`, or the
`--profile-dir` folder), plus a cache folder that never roams. [`AppPaths`](api:jbrowser.paths.AppPaths) in
[paths.py](source:jbrowser/paths.py) is the only place that knows the locations; the
[data files reference](../reference/data-files.md) lists them all.

## Crash-safe writes

Every JSON and binary file is written through [core/jsonstore.py](source:jbrowser/core/jsonstore.py):

```python
from jbrowser.core.jsonstore import atomic_write_json, atomic_write_bytes, read_json

atomic_write_json(path, data)          # indent=2, UTF-8, ensure_ascii=False
data = read_json(path, default={})
```

`atomic_write_bytes()` writes to a temporary file in the same folder, flushes and `fsync`s it, then swaps it into
place with `os.replace()`. A crash or power cut leaves either the old file or the new one, never half of each.

<!-- if >= 1.4.1 -->
Antivirus scanners and the Windows search indexer briefly open files that were just written, and Windows refuses to
replace a file another program has open ("Access is denied"). `_replace()` therefore retries up to 20 times with a
growing delay (about 2.5 seconds in total) before giving up, and logs how many retries it needed.
<!-- else -->
!!! warning "Known issue in this version"
    If an antivirus scan holds a file at the moment it is replaced, the save fails with "Access is denied" and that
    change is lost. 1.4.1 retries the replacement for about 2.5 seconds.
<!-- endif -->

`read_json()` returns the default for a missing file. A file that can't be parsed is renamed to `*.corrupt` (kept
for diagnosis) and the default is used, so a damaged file never stops JBrowser from starting.

## Who writes what

| File | Owner | When it is written |
|---|---|---|
| `settings.json` | `Settings` | 0.4 s after the last change |
| `session.json` | `SessionManager` | 2.5 s after a change, every 15 s while something changed, and on exit; skipped when the content hash is unchanged |
| `history.sqlite3` | `HistoryService` | on every visit (SQLite in WAL mode, `synchronous=NORMAL`) |
| `vault.bin` | `PasswordVault` | on every change, encrypted ([password vault](../privacy/password-vault.md)) |
| `bookmarks.json`, `favourites.json`, `archive.json`, `downloads.json`, `userscripts.json` | their services | on change, and on exit |
| `blocklist.txt`<!-- if >= 1.5.0 -->, `filters.txt`<!-- endif -->, `threats.txt` | privacy and threat updaters | after a list download (weekly) |
| `Profiles\<space-id>\` | Chromium | continuously (cookies, storage, permissions) |

`ctx.save_all()` asks every service to save immediately; the main window calls it when closing.

## The session

`session.json` holds the spaces (name, icon, colour, proxy, active card, scroll position) and their cards (address,
title, width, zoom, mute, pin, favourite link) with each card's **back/forward history**, serialised by Qt
(`QWebEngineHistory`) and stored as base64. Incognito spaces are never written.

On start-up `SessionManager.restore()` rebuilds the state. Cards are restored **asleep**: only the cards the user can
see are loaded, the others load when they come into view (see [the lifecycle](../engine/lifecycle.md)).

## Deleting data

- **A space.** Chromium keeps a profile's files open until the profile is destroyed, so deleting a space records its
  ID in `profiles.pending_wipe`; its folders are removed at the next start, before any profile opens.
- **Clear on exit.** `privacy.clear_on_exit` can list `history`, `cookies`, `cache` and `downloads`. Cookie and cache
  deletions issued during shutdown are asynchronous, so they are repeated on disk at the next start
  (`ProfileManager._clear_on_start`).
- **Factory reset.** Writes `.factory-reset`; the next start deletes the data and cache folders, or, in portable
  mode, only the names in `AppPaths.OWNED`.

## Adding a new file

1. Add a path to `AppPaths.__init__` (and its name to `OWNED` so a portable factory reset removes it).
2. Read it with `read_json(path, default)` and write it with `atomic_write_json()`.
3. Debounce writes with a single-shot `QTimer` if the data changes often, and add the service's `save_now` to
   `AppContext.save_all()`.
4. Never write personal data for incognito spaces.
