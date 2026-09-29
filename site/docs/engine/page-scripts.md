---
title: Page scripts and script worlds
nav_title: Page scripts
description: The JavaScript JBrowser injects into pages, which world each script runs in, and why.
---

JBrowser adds a few scripts to every page. They are Python strings in [engine/js.py](source:jbrowser/engine/js.py)
(so the frozen build needs no data files) and are installed on each profile by
`ProfileManager._install_base_scripts()` as `QWebEngineScript`s named `jb:*`.

## Script worlds

Chromium runs scripts in **worlds**. All worlds share the page's DOM, but each has its own JavaScript globals, so a
script in one world cannot see variables, functions or patched prototypes of another.

| World | ID | Who runs there |
|---|---|---|
| Main world | `0` (`ScriptWorldId.MainWorld`) | the page's own scripts |
| JBrowser's isolated world | `1` (`BRIDGE_WORLD` in `engine/js.py`) | JBrowser's helpers, the `QWebChannel` bridge |
| User scripts | set per script | the user's own scripts and styles ([services/userscripts.py](source:jbrowser/services/userscripts.py)) |

**Rule:** anything that reads from the page, holds secrets or talks to Python runs in the isolated world. Only code
that must change what the *page's* JavaScript sees (a `navigator` property, a canvas method) runs in the main world,
and it is kept as small as possible.

## The scripts

<!-- if >= 1.5.0 -->
| Name | World | When | Does |
|---|---|---|---|
| `jb:privacy` | main | document creation, all frames | `privacy_js()`: `navigator.globalPrivacyControl`, `navigator.doNotTrack`, canvas read-back noise. The only main-world script. Skipped on exempt sites. |
| `jb:guard` | isolated | document creation | `GUARD_JS`: remembers edited form fields; `window.__jbGuardProbe()` reports media playing, unsaved input and full screen to the [lifecycle manager](lifecycle.md) |
| `jb:cosmetic` | isolated | document creation | `cosmetic_js()`: element hiding for the page's site ([content blocking](../privacy/content-blocking.md)) |
| `jb:qwebchannel` | isolated | document creation | Qt's `qwebchannel.js`, read from the QtWebChannel module's resources |
| `jb:autofill` | isolated | document ready | `AUTOFILL_JS`: finds login forms, reports submitted credentials, fills saved ones |

### Keeping the main-world script invisible

Bot checks (Google's "unusual traffic", Cloudflare's "Checking your browser") look for pages whose built-in functions
were replaced, because automation tools do exactly that. `privacy_js` therefore:

- builds replacements with method shorthand, so they have no `prototype`, like native functions;
- copies the original's `length`;
- installs a `Function.prototype.toString` that reports `function getImageData() { [native code] }` for its
  replacements (through a `WeakMap`) and behaves normally for everything else, including itself;
- changes **no hardware values** (CPU cores, memory, WebGL renderer): faking them in the page but not in workers,
  where they can't be faked, is itself a strong bot signal;
- does nothing at all on exempt hosts: `CHALLENGE_SITES` in [services/privacy.py](source:jbrowser/services/privacy.py),
  any `google.*` domain, and sites on the user's allowed list.

See [fingerprinting and bot checks](../privacy/fingerprinting.md) for the reasoning.

### What the guard no longer does in the page

Earlier versions wrapped `window.WebSocket` and `RTCPeerConnection` in the main world to learn whether a page had a
live connection. That was detectable, so since 1.5.0 the controller learns it outside the page: the
`PageInterceptor` sees WebSocket requests, and the permission handler sees a granted camera, microphone or screen.
<!-- else -->
| Name | World | When | Does |
|---|---|---|---|
| `jb:guard` | main | document creation | `GUARD_JS`: wraps `WebSocket` and `RTCPeerConnection` to count live connections, tracks edited fields; `window.__jbGuardProbe()` reports them to the [lifecycle manager](lifecycle.md) |
| `jb:gpc` | main | document creation, all frames | `GPC_JS`: `navigator.globalPrivacyControl = true` (when enabled) |
| `jb:dnt` | main | document creation, all frames | `DNT_JS`: `navigator.doNotTrack = "1"` (when enabled) |
| `jb:fingerprint` | main | document creation, all frames | `fingerprint_js()`: canvas noise, a generic WebGL vendor and renderer, 4 CPU cores and 8 GB of memory (when enabled; skipped on allowed sites) |
| `jb:qwebchannel` | isolated | document creation | Qt's `qwebchannel.js` |
| `jb:autofill` | isolated | document ready | `AUTOFILL_JS`: finds login forms, reports submitted credentials, fills saved ones |

!!! note "Changed in 1.5.0"
    Sites that check for bots detected these main-world changes and answered with CAPTCHAs. 1.5.0 merged GPC, DNT
    and canvas noise into one masked script, stopped changing hardware values, moved the guard to the isolated
    world and exempted sign-in and security-check sites.
<!-- endif -->

## Talking to Python: `QWebChannel`

Each `TabController` registers a [`PageBridge`](api:jbrowser.engine.page.PageBridge) object as `jbBridge` on a
`QWebChannel` bound to `BRIDGE_WORLD`. Scripts in that world reach it through `qt.webChannelTransport`; the page's
own scripts cannot, because the transport object lives in the isolated world. The bridge has two slots:

- `loginFormDetected(count)`: a visible password field appeared;
- `credentialsSubmitted(username, password)`: a login form was submitted.

Python talks to the page with `page.runJavaScript(code, BRIDGE_WORLD, callback)`, for example
`window.__jbFill(user, pass)` to autofill, or `window.__jbGuardProbe()` for the lifecycle probe.

## Adding a script

1. Write it as a raw string in `engine/js.py`, wrapped in an IIFE with `'use strict'` and a guard against running
   twice (`if (window.__jbSomething) return;`).
2. Prefer the isolated world. If it has to run in the main world, mask every replaced function as `privacy_js` does,
   and exempt `CHALLENGE_SITES`.
3. Add it in `_install_base_scripts()` with a `jb:` name, an injection point (`DocumentCreation`, `DocumentReady` or
   `Deferred`) and whether it runs in sub-frames.
4. If a setting controls it, reinstall scripts when that setting changes (`ProfileManager._on_setting`). New scripts
   reach open pages on their next navigation.
