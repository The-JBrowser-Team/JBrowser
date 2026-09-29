---
title: "Lifecycle: throttling and the memory saver"
nav_title: Lifecycle and memory saver
description: How cards out of sight stop drawing, how idle cards go to sleep, and what protects a card from both.
---

A canvas can hold dozens of live pages. [`LifecycleManager`](api:jbrowser.engine.lifecycle.LifecycleManager)
([engine/lifecycle.py](source:jbrowser/engine/lifecycle.py)) keeps that cheap with two mechanisms built on Chromium's
page lifecycle states (`Active`, `Frozen`, `Discarded`).

## Throttling: out of sight

Canvases report visibility with `set_in_view(tab_id, visible, render_visible)` whenever a card enters or leaves the
viewport, or its space is shown or hidden.

1. When a card leaves view, a single-shot timer starts: `THROTTLE_DELAY_MS` = **5 seconds**.
2. When it fires, the manager emits `aboutToThrottle(tab_id)`: the card takes a snapshot while it can still render
   (for the sleep preview<!-- if >= 1.5.0 --> and the Gallery<!-- endif -->). Then it **probes** the page.
3. `TabController.throttle(freeze)` hides the page (`page.setVisible(False)`: no frames, `requestAnimationFrame`
   stops, timers slow down) and, if the probe found nothing that needs to keep running, **freezes** it
   (`LifecycleState.Frozen`: JavaScript tasks and timers pause). Chromium must also recommend a non-active state.
4. The moment the card is visible again, `unthrottle()` restores `Active` and visibility.

Setting: `performance.throttle` (on by default). Switching it off unthrottles every card immediately.

## Sleeping: the memory saver

Every `SCAN_INTERVAL_MS` (20 s), `scan()` looks for cards that have been inactive longer than the preset in
`performance.sleep_preset`:

| Preset | Sleeps after |
|---|---|
| `off` | never |
| `minimal` | 30 minutes |
| `moderate` (default) | 20 minutes |
| `maximum` | 10 minutes |

Inactivity is measured from `tab.last_active`, which is updated when a card is focused or leaves the view. A
candidate is put to sleep with `try_sleep()`: probe, then `aboutToSleep` (the card swaps its live view for the
snapshot), then `TabController.discard()` sets `LifecycleState.Discarded`, which frees the renderer. If Chromium
refuses (`recommendedState()` says the page is still needed), the card wakes again and nothing is lost.

A sleeping card shows its last snapshot, faded, with a moon badge. Clicking it, focusing it or scrolling it into
view calls `wake()`, which reloads the page from its preserved history.

## What protects a card

Two layers of checks, and a card is left alone if **any** of them says so.

**Synchronous checks** (`_is_protected_sync`): it is playing audio; it has a download in progress; DevTools are
open; it is the focused card of the active space; it is visible; its site is on the `performance.never_sleep` list.

**The page probe** (`TabController.probe`), answered by the guard script and the controller:

| Probe field | Source | Protects because |
|---|---|---|
| `media` | a `<video>`/`<audio>` element is playing | music, video |
| `dirty` | a form field was edited and not submitted | unsaved text |
| `fullscreen` | `document.fullscreenElement` | a presentation or a game |
<!-- if >= 1.5.0 -->
| `ws` | the card's `PageInterceptor` saw a WebSocket request since the last navigation | chat, live dashboards |
| `rtc` | the card was granted the camera, microphone or screen | a call or a screen share |
<!-- else -->
| `ws` | the guard's `WebSocket` wrapper counted an open connection | chat, live dashboards |
| `rtc` | the guard's `RTCPeerConnection` wrapper counted a live call | a call |
<!-- endif -->

A page that doesn't answer within 2 seconds counts as protected. When the user asks a card to sleep
(*Put card to sleep*), the reason it can't is shown as a toast (`sleepBlocked`).

## Restored sessions

Cards restored at start-up are created with `sleeping=True` and not loaded. Only the cards the canvas actually shows
call `ensure_loaded()`; the rest load when they come into view. A 30-card session therefore starts as fast as a
3-card one.

## Signals for the UI

| Signal | The UI does |
|---|---|
| `aboutToThrottle(tab_id)` | take a snapshot while the page still renders |
| `aboutToSleep(tab_id)` | show the snapshot instead of the live view |
| `woke(tab_id)` | show the live view again |
| `sleepBlocked(tab_id, reason)` | tell the user why a card can't sleep |
