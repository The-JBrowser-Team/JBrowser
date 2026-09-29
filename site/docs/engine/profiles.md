---
title: Profiles and space isolation
nav_title: Profiles and spaces
description: One Chromium profile per space, incognito profiles, and what each profile is configured with.
---

Isolation between spaces is not something JBrowser implements itself: it is Chromium's profile mechanism.
[`ProfileManager`](api:jbrowser.engine.profiles.ProfileManager) ([engine/profiles.py](source:jbrowser/engine/profiles.py))
gives **every space its own `QWebEngineProfile`**, created the first time a card in that space needs one.

## Persistent and incognito profiles

| | Persistent space | Incognito space |
|---|---|---|
| Profile | `QWebEngineProfile("space-<id>")` | `QWebEngineProfile()` (off-the-record) |
| Cookies, localStorage, IndexedDB, service workers | `<data>\Profiles\<space-id>\` | memory only |
| HTTP cache | `<cache>\Profiles\<space-id>\` (up to 512 MB) | memory only |
| Permissions | stored on disk | kept in memory |
| History, favicons, archive, session | recorded | never recorded |

Two cards in different spaces can be signed in to the same site as different people, and a tracker cookie set in
*Home* is invisible in *Work*. Closing an incognito space destroys its profile and everything in it.

Qt creates a named profile's default folders before the paths can be redirected; `ProfileManager` removes those
empty stray folders again, so nothing is left in `QtWebEngine\` under the user's AppData.

## What every profile gets

`_create()` configures each profile the same way:

- **User agent:** <!-- if >= 1.5.2 -->`identity.apply()` presents the newest stable Chrome version (recorded at every release) in the user agent and the client hints, as a Chromium browser ([details](../privacy/fingerprinting.md#the-browser-jbrowser-presents)).<!-- else -->Qt's default with the `QtWebEngine/x.y` token removed, so sites see a normal Chrome user agent.<!-- endif -->
<!-- if >= 1.5.0 -->
- **`Accept-Language`:** built by `accept_language()` from the Windows display languages, like Chrome does
  (for example `en-AU,en;q=0.9`). Qt sends none by default, and a browser without one looks automated.
<!-- endif -->
- **Two interceptors:** the profile-wide `ProfileInterceptor` (headers, HTTPS upgrades, link cleaning, developer
  hosts) and, per page, the card's `PageInterceptor` (blocking). See [the request pipeline](../privacy/request-pipeline.md).
- **A cookie filter:** `PrivacyService.allow_cookie()` decides about third-party cookies.
- **Downloads** go to the `DownloadManager`, tagged with the space and whether it is incognito.
- **Notifications** go through `AppContext.present_notification()` to the in-app and Windows notification.
- **Page scripts** (`_install_base_scripts`), see [page scripts and script worlds](page-scripts.md), plus the user's own
  scripts and styles for that space.
- **Web settings** (`_apply_settings`): full screen allowed, smooth scrolling following *Fluid animations*, DNS
  prefetch and hyperlink auditing (`<a ping>`) off, pop-ups blocked unless the user allowed them, WebRTC limited to
  public interfaces (no local IP leaks), optional autoplay blocking and forced dark mode, and the back/forward cache on.

Changing a related setting re-applies it to every open profile: privacy switches reinstall the page scripts, other
`privacy.*` keys and `appearance.force_dark_web` re-apply the web settings.

## Lifetime

- **Created** lazily by `profile_for(space)` when `EngineRegistry` creates the first `TabController` of the space.
- **Released** by `release(space)` when the space is deleted. Chromium keeps the files open until the profile object
  is gone, so a persistent space's folders are deleted at the next start (`profiles.pending_wipe`).
- **Disposed** by `dispose_all()` at shutdown, after every page ([start-up and shutdown](../architecture/startup-shutdown.md#shutdown)).

## One network stack

Chromium has a single network service per process, shared by all profiles. Two consequences:

- A space's **proxy** can't apply to that space alone. JBrowser applies the active space's proxy to everything and
  re-applies it on every space switch ([networking](networking.md)).
- **DNS-over-HTTPS** is global.

## Popups

`window.open()` with window features (OAuth sign-ins, payment pages) asks the page for a `WebDialog`.
`TabController.create_window()` then asks the UI (`ctx.hooks.create_popup`) for a small `PopupWindow` that shares the
opener's profile, so the sign-in lands in the right space and `window.opener` keeps working. Other new windows
(links with `target=_blank`, middle-clicks) become new cards next to the opener.
