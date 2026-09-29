---
title: Start-up and shutdown
description: What jbrowser/app.py does, step by step, and why the order matters.
---

Everything starts in `run()` in [`jbrowser/app.py`](source:jbrowser/app.py). `main.py`, `python -m jbrowser` and
the frozen `JBrowser.exe` all call it.

## Start-up, in order

1. **Parse the command line** (`_parse_args`). Unknown options pass through to Qt and Chromium.
2. **Wait for a previous copy** (`--wait-pid`). After *Restart* or *Factory reset*, the new process waits until the
   old one has fully exited, so the two never share a profile folder.
3. **Resolve file locations** with `AppPaths` ([paths.py](source:jbrowser/paths.py)). If the `.factory-reset` marker
   exists, erase everything JBrowser owns now, before anything opens a file.
4. **Logging** to `Logs\jbrowser.log` (2 MB, three rotations), and to the console with `--debug`.
5. **Chromium and Qt environment** (`_chromium_flags`), which must be set before Qt WebEngine loads:
    - `QTWEBENGINE_CHROMIUM_FLAGS` gets `--log-level=3`, plus `--proxy-server` for an HTTPS proxy (the only proxy
      type that needs a start-up flag). Flags JBrowser added in an earlier run are remembered in
      `JBROWSER_ADDED_CHROMIUM_FLAGS` and dropped, so a removed proxy doesn't survive a restart.
    - `QT_WIDGETS_RHI=1` and `QT_WIDGETS_RHI_BACKEND=d3d11`: widget windows composite through Direct3D from the
      start. Otherwise the first web card converts the window, which recreates its handle (a flicker) and drops the
      Mica backdrop.
    - `QT_MEDIA_BACKEND=windows`: sound effects use the native backend, so the build needs no FFmpeg.
6. **Import `QtWebEngineWidgets` before `QApplication` exists** (Qt's rule), set the AppUserModelID so the taskbar
   groups windows correctly, and create the application with the Fusion style.
7. **Single instance** ([single_instance.py](source:jbrowser/single_instance.py)). The instance key includes a hash
   of the data folder, so one JBrowser runs per profile. A second launch sends its URLs to the running window as
   JSON over a local socket and exits with code 0.
8. **Hold the `JBrowser.AppMutex` named mutex** for the life of the process. The installer uses it to see that
   JBrowser is running.
9. **Settings and theme.** On the very first run, *Fluid animations* follows the Windows "Animation effects"
   setting.
10. **`AppContext`** creates every service and the engine ([architecture overview](overview.md#the-dependency-container-appcontext)).
11. **Network before the first page:** apply the DNS mode (DNS-over-HTTPS is set process-wide) and the proxy.
12. **Restore the session** (unless `--no-restore`), and delete the profile folders of default spaces that older
    versions created and that are no longer used.
13. **Create `MainWindow`** and install an exception hook that logs the traceback and shows a short
    "Something went wrong" toast instead of crashing.
<!-- if >= 1.4.1 -->
14. **Connect Windows' shutdown requests:** `commitDataRequest` saves everything, and `aboutToQuit` closes the
    window (see below).
<!-- endif -->
15. **Show the window**, start the session autosave, then one of: the welcome (when `onboarding.version` is older
    than `ONBOARDING_VERSION`), the URLs from the command line, or the Lazy Toolbar when there are no cards.
16. **Background jobs:** the dangerous-site list after 8 s, the update check after 15 s (skipped with
    `JBROWSER_SKIP_UPDATES`), and the filter lists after 12 s. Each refreshes at most weekly, except the update
    check (daily).

## Shutdown

Qt WebEngine is strict about teardown order: **views before pages, pages before profiles, profiles before the
application.** Getting it wrong crashes on exit or leaves Chromium processes behind. The order is enforced in two
places:

1. `MainWindow.closeEvent()` ([ui/window.py](source:jbrowser/ui/window.py)) saves the window geometry, closes
   popups and tool windows, calls `ctx.save_all()` (session, settings, bookmarks, downloads, user scripts, archive,
   favourites), tears down every card's view, then calls `ctx.shutdown()` and quits the event loop.
2. After `app.exec()` returns, `run()` flushes deferred deletions, disposes the profiles, deletes the window and
   runs the garbage collector, flushing deletions between each step.

If *Restart* or *Factory reset* was requested, `run()` finally starts a new copy with the same `--profile-dir` and
`--debug` options plus `--wait-pid`.

<!-- if >= 1.4.1 -->
### When Windows closes JBrowser

When the user signs out, or an installer uses the Windows Restart Manager, Qt quits **without** a close event.
Since 1.4.1, `commitDataRequest` saves everything first and `aboutToQuit` calls `window.close()`, so the same
orderly `closeEvent()` runs. After a normal close the window is already shut down and this does nothing.
<!-- else -->
!!! warning "Known issue in this version"
    When Windows closes JBrowser (signing out, or an installer's Restart Manager), Qt quits without a close event,
    so the latest changes may not be saved. Fixed in 1.4.1.
<!-- endif -->

## Restart and factory reset

Both set `ctx.restart_requested` and close the window normally. A factory reset first writes the `.factory-reset`
marker; the new copy sees it in step 3 and erases the data before anything opens it. In portable mode
(`--profile-dir`) only the files in `AppPaths.OWNED` are removed, because the folder may hold the user's own files.
