---
title: Debugging
description: Logs, DevTools, Qt and Chromium diagnostics, and common problems.
---

## The log

`Logs\jbrowser.log` in the data folder (`%APPDATA%\JBrowser\Logs`, or `<profile-dir>\Logs`), rotated at 2 MB with
three old copies. Every module logs through `logging.getLogger(__name__)`.

- `--debug` sets the level to DEBUG and also prints to the console.
- `JBROWSER_CONSOLE_LOG=1` prints to the console without the extra detail.
- Unhandled exceptions are logged with their traceback by the exception hook in `app.py`, and the user sees a short
  "Something went wrong" toast instead of a crash.
- With `--debug`, pages' console messages are logged too (`BrowserPage.javaScriptConsoleMessage`).

## Web pages

Press **F12** (or Ctrl+Shift+I) on a card for Chromium's DevTools, docked inside the card. The console shows the
page's main world; pick JBrowser's isolated world from the console's context menu to inspect its helpers.

`QTWEBENGINE_REMOTE_DEBUGGING=<port>` opens the DevTools protocol, so Chrome's `chrome://inspect` or a script can
attach from outside.

## Qt and Chromium

| Variable | Use |
|---|---|
| `QT_LOGGING_RULES="qt.webenginecontext.debug=true"` | prints Qt WebEngine's configuration (GPU, sandbox, flags) at start-up |
| `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"` | rules the GPU out when pages are blank or flicker |
| `QTWEBENGINE_CHROMIUM_FLAGS="--enable-logging --v=1"` | Chromium's own logging to stderr (very verbose) |

JBrowser appends its own flags to `QTWEBENGINE_CHROMIUM_FLAGS`, so yours are kept.

## Debugging Python

Run `main.py` under a debugger (VS Code, PyCharm) with a test `--profile-dir`. Breakpoints work everywhere on the UI
thread. Two things to know:

- Qt calls Python back from C++; an exception in a slot is logged by the exception hook and does not stop the app.
  Search the log for `Unhandled exception`.
- Pausing at a breakpoint freezes the whole UI, and Chromium may consider the page unresponsive; that is expected.

## Common problems

| Symptom | Likely cause |
|---|---|
| "JBrowser is already running" / nothing happens on start | another JBrowser uses the same data folder; use a different `--profile-dir` |
| Blank or flickering pages | the GPU driver: try `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` |
| `RuntimeError: wrapped C/C++ object … has been deleted` | a Python reference outlived its Qt object, often a finished animation ([motion](../ui/motion.md#stopping-an-animation-safely)) or a widget deleted with `deleteLater()` |
| A crash on exit | teardown order: views before pages before profiles ([shutdown](../architecture/startup-shutdown.md#shutdown)) |
| A setting "doesn't apply" | the component reads it once; subscribe to `settings.changed` ([settings](../architecture/settings.md#changes-apply-immediately)) |
| A page script doesn't run on the first load | it was added to a page during a navigation; install it on the profile ([page scripts](../engine/page-scripts.md#adding-a-script)) |
| A build fails half-way with locked files | the repository is in OneDrive, or JBrowser is running from the build folder ([building](../build/building.md#where-the-output-goes)) |
