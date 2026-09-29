---
title: Tab controllers and pages
nav_title: Tab controllers
description: TabController owns one card's QWebEnginePage and turns engine events into state, info bars and actions.
---

Every card has exactly one [`TabController`](api:jbrowser.engine.tab_controller.TabController)
([engine/tab_controller.py](source:jbrowser/engine/tab_controller.py)). `EngineRegistry` creates it when a `Tab`
is added to `BrowserState` and disposes it when the tab is removed. The controller owns:

- a [`BrowserPage`](api:jbrowser.engine.page.BrowserPage), the `QWebEnginePage` subclass, in the space's profile;
- a per-page `PageInterceptor` that blocks requests and counts them for this card;
- a `QWebChannel` with a [`PageBridge`](api:jbrowser.engine.page.PageBridge) object, registered in JBrowser's
  isolated script world, for password capture and autofill.

The widget that shows the page (`WebCard` with its `QWebEngineView`) belongs to the UI and only attaches to
`controller.page`. The controller never touches widgets; it writes to its `Tab` and emits signals.

## From engine events to state

`_connect()` wires the page's signals:

| Page signal | Result |
|---|---|
| `urlChanged` | `tab.url`, `secure`, back/forward state; per-site zoom; saved-login count; history (after 0.9 s for single-page apps) |
| `titleChanged`, `iconChanged` | `tab.title` (also in history), `tab.icon` (and the favicon cache, not for incognito) |
| `loadStarted`, `loadProgress`, `loadFinished` | `loading`, `progress`; a visit in history; the HTTPS-first fallback on failure |
| `recentlyAudibleChanged`, `audioMutedChanged` | `audible`, `muted` |
| `lifecycleStateChanged` | `sleeping` (discarded) and `throttled` (frozen) |
| `renderProcessTerminated` | `crashed`, and a *Reload* info bar |
| `permissionRequested` | an *Allow / Block* info bar |
| `certificateError` | a *Back to safety / Proceed anyway* info bar (or a silent fallback to http, when JBrowser chose https) |
| `authenticationRequired`, `proxyAuthenticationRequired` | a sign-in dialog through `ctx.hooks` |
| `fullScreenRequested`, `desktopMediaRequested`, `printRequested`, `windowCloseRequested`, `findTextFinished`, `linkHovered` | re-emitted for the UI |

All writes go through `tab.update(...)`, so they are coalesced once per frame
([the update pipeline](../architecture/state.md#the-coalescing-update-pipeline)).

## Info bars

Anything that needs the user's answer inside a card is an **info bar**: the controller emits
`infobar(InfoBarSpec)` and later `infobarClosed(key)`; the card shows it as an `InfoBarWidget`.
[`InfoBarSpec`](api:jbrowser.models.infobar.InfoBarSpec) ([models/infobar.py](source:jbrowser/models/infobar.py))
carries a key (one bar per key), the text, an icon, a kind (`info`, `warning`, `danger`), `InfoAction` buttons, an
optional timeout, what dismissing means (`on_dismiss`) and whether it survives navigation. Permission prompts,
certificate errors, *Save password?*, crashes, dangerous sites and external-protocol links all use it.

Engine requests that are answered later (a permission, a deferred certificate error) are copied and kept in
`_pending`, because the signal's argument is a temporary. `dispose()` denies whatever is still pending.

## Navigation rules in `BrowserPage`

`acceptNavigationRequest()` runs before every navigation:

1. **External protocols** (`mailto:`, `tel:`, `zoommtg:`, … or any unknown scheme in the main frame) are not
   loaded; an info bar offers to open them with the registered Windows app.
2. **Known phishing and malware hosts** are refused. For a main-frame navigation the dangerous-site page is shown
   one event-loop turn later, because starting a navigation from inside this callback aborts Chromium
   ([safe browsing](../privacy/safe-browsing.md)).
3. Everything else is left to Chromium.

`createWindow()` is forwarded to `TabController.create_window()` ([popups](profiles.md#popups)).

## Loading lazily

A restored card has a URL and a saved history but no page load. `ensure_loaded()` restores the history with
`QDataStream` (which also navigates) or loads the URL, the first time the card is shown or woken. `history_bytes()`
does the reverse for the session and the Archive.

## Lifecycle operations

The [lifecycle manager](lifecycle.md) decides; the controller executes:

| Method | Does |
|---|---|
| `probe(callback)` | asks the page (<!-- if >= 1.5.0 -->isolated world<!-- else -->main world<!-- endif -->) whether it plays media, has unsaved input<!-- if < 1.5.0 -->, open WebSockets or WebRTC calls<!-- endif --> or is in full screen<!-- if >= 1.5.0 -->, and adds what the controller knows itself: an open WebSocket, a granted camera/microphone/screen<!-- endif -->; `None` after 2 s |
| `throttle(freeze)` | `page.setVisible(False)` and, when Chromium agrees, `LifecycleState.Frozen` |
| `unthrottle(render_visible)` | back to `Active` and visible |
| `discard()` | `LifecycleState.Discarded`, only when `recommendedState()` allows it |
| `wake()` | back to `Active`, loading the page if it never loaded |

## Other responsibilities

Zoom (steps from 25 % to 500 %, remembered per host in `zoom.sites`, never for incognito), find in page, mute,
saved-login lookup and autofill ([password vault](../privacy/password-vault.md)), *Clear site data* and recording
visits in history (never for incognito spaces).
