---
title: Testing your changes
nav_title: Testing changes
description: How to try a change safely and what to check before opening a pull request.
---

JBrowser is a desktop GUI around Chromium, so most of its behaviour is tested by running it. These habits make that
quick, repeatable and safe for your own data.

## Use a throw-away profile

```powershell
$env:JBROWSER_SKIP_WELCOME = "1"; $env:JBROWSER_SKIP_UPDATES = "1"
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-test" --debug
```

- `--profile-dir` keeps every file in that folder: nothing touches your everyday JBrowser, and both can run at
  the same time (one instance per data folder).
- Deleting the folder resets everything. Delete it between runs to test first-run behaviour.
- Remove `JBROWSER_SKIP_WELCOME` to test the welcome; remove `JBROWSER_SKIP_UPDATES` to test update checks.

## A checklist

Go through what applies to your change:

- **Both themes** and <!-- if >= 2.0.3 -->**both materials** (Frosted, Solid)<!-- else -->**all materials** (Acrylic, Mica, Mica Alt, Solid)<!-- endif --><!-- if >= 1.5.0 -->, with and without a colour tint<!-- endif -->.
- ***Fluid animations* off**: everything must still work, instantly.
- **An incognito space**: no history, favicons, archive, session or passwords may be written.
- **Several spaces**: the change behaves correctly in the space you are not looking at, and after switching.
- **Restart**: the state survives *Restart JBrowser* (the session, settings).
- **The keyboard**: the feature works without a mouse, and Ctrl+/ lists any new shortcut.
- **A small window** (the minimum is 760 × 480) and a maximised one; a high-DPI display if you have one.
- **The log**: no new warnings or tracebacks in `<profile-dir>\Logs\jbrowser.log`.
- **The build**, for changes to packaging, imports or assets: build the app and run the exe ([building](../build/building.md#checking-a-build)).

## Testing specific areas

| Area | How |
|---|---|
| Tracker and ad blocking | open a news site and watch the shield count; switch protection off for the site and compare<!-- if >= 1.5.0 -->; `FilterEngine.css_for(host)` shows the element-hiding CSS for a site<!-- endif --> |
| Threat protection | add a test host with `ctx.threats.add_hosts({...})` from a debug session and navigate to it |
| HTTPS-first | turn it on and open `http://` addresses of sites with and without https |
| The memory saver | choose *After 10 minutes*, or run *Sleep all inactive cards now* from the Lazy Toolbar |
| Updates | run from source with `__version__` set lower and use *Settings → About → Check now* ([automatic updates](../build/auto-update.md#testing)) |
| The installer | build a copy with a different `AppId` ([the installer](../build/installer.md#testing-without-touching-a-real-installation)) |
| Page scripts | F12 on the card: the page's console shows main-world errors; isolated-world scripts log with `--debug` |

## Scripted checks

Qt applications can be driven from Python: start `jbrowser.app` in-process with a test profile, then schedule steps
with `QTimer.singleShot` that call `BrowserController` methods, read `BrowserState`, and grab widgets with
`widget.grab()` for screenshots. `QTWEBENGINE_REMOTE_DEBUGGING=9333` opens Chromium's DevTools protocol on a port, so
a script can read page titles and URLs (`http://127.0.0.1:9333/json`). This is how larger changes, such as a new
overlay or a change to the request pipeline, are exercised end to end before a release.

When you close JBrowser from a script, close the process you started (by its PID), never other windows.
