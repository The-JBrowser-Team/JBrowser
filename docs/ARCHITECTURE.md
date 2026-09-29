# Architecture

JBrowser is a Python application on **PyQt6 / Qt 6 WebEngine**, where Qt WebEngine embeds Chromium. Everything runs in
one Qt process, plus the Chromium renderer processes (`QtWebEngineProcess.exe`) that Qt starts for web pages.

## Layers

```
            ┌──────────────────────── jbrowser/ui ────────────────────────┐
 user ────► │ MainWindow · TitleBar · Sidebar · Canvas/WebCard · LazyToolbar │
            │ Gallery · dialogs/ · Onboarding · BrowserController · actions  │
            └───────────────┬───────────────────────────────▲──────────────┘
                 intents    │                               │ Qt signals
            ┌───────────────▼───────────────┐   ┌───────────┴──────────────┐
            │ jbrowser/models  BrowserState │──►│ jbrowser/engine          │
            │ Space · Tab · update pipeline │   │ profiles · TabController │
            └───────────────┬───────────────┘   │ lifecycle · injected JS  │
                            │                   └───────────┬──────────────┘
            ┌───────────────▼───────────────────────────────▼──────────────┐
            │ jbrowser/services  history · vault · privacy · threats ·      │
            │ network · downloads · session · archive · updater · …         │
            ├──────────────────────────────────────────────────────────────┤
            │ jbrowser/core  settings · commands · motion · fuzzy · urls    │
            │ jbrowser/platform  Windows DWM, frame, DPAPI                  │
            └──────────────────────────────────────────────────────────────┘
```

**Dependencies point downwards.** `core` and `platform` import nothing else from JBrowser. `models` and `services`
never import `ui`. The UI observes lower layers through Qt signals.

## Start-up (`jbrowser/app.py`)

1. Parse the command line, then set the Chromium flags and Qt environment (D3D11 widgets, the native Windows audio
   backend).
2. Enforce a single instance (`single_instance.py`): a second launch forwards its URLs to the running window and
   exits. Hold the named mutex `JBrowser.AppMutex`, which the uninstaller uses to see that JBrowser is running.
3. Build the `AppContext` (`context.py`), a dependency container that creates every service in order and holds
   no globals.
4. Restore the session, create the `MainWindow`, and show the first-run welcome if it has not been seen.
5. Start background jobs: tracker and threat list refreshes, and the update check (after 15 s).
6. On exit, tear down in reverse order: save the session, stop pages, then close profiles before the application
   object goes away. The order matters for Qt WebEngine. The same path runs when Windows asks JBrowser to close
   (signing out, or an installer's Restart Manager): `aboutToQuit` closes the main window, whose `closeEvent` does
   the saving and teardown.

## Data flow

- **`BrowserState`** (`models/state.py`) is the single source of truth for spaces, cards, focus and selection.
- The **engine** (`EngineRegistry` → one `TabController` per card) listens to the state and owns the Chromium pages.
  Engine events (title, favicon, progress, audio and so on) are written to `Tab` models, and the
  **`TabUpdatePipeline`** flushes them to the UI once per frame. Off-screen cards only mark themselves stale.
- **UI surfaces** (canvas, sidebar, title bar, Lazy Toolbar) observe the same state and never talk to each other.
- **User intents** go through `BrowserController` (`ui/controller.py`) or the `CommandRegistry` (`core/commands.py`,
  filled by `ui/actions.py`), so a click, a shortcut and a Lazy Toolbar command all do the same thing.
- **Settings** (`core/settings.py`) are one observable JSON-backed store. Widgets subscribe to the keys they care
  about, so changes apply immediately.

## Spaces and isolation

`engine/profiles.py` creates one `QWebEngineProfile` per space, each with its own storage folder. Cookies, storage,
cache and permissions therefore never cross spaces. Incognito spaces use off-the-record profiles that never write to
disk. Deleting a space schedules its folder for removal at the next start, because Chromium keeps the files open.

## Performance

- `engine/lifecycle.py` stops frame production 5 s after a card leaves view, and freezes the page when that is safe.
- After the chosen idle time, the memory saver hibernates background cards (the renderer is discarded and a faded
  snapshot is kept). Cards that are playing media, have unsaved input, use WebRTC or WebSockets, or have DevTools open
  are protected.
- A restored session only loads the cards that are visible.

## Updates and installation

`services/updater.py` asks the GitHub Releases API for the latest release, downloads the installer and checks its
SHA-256. It then starts a hidden helper that waits for JBrowser to close and runs the Inno Setup installer silently.
See [AUTO_UPDATE.md](AUTO_UPDATE.md) and [BUILDING.md](BUILDING.md).

## Data locations

| What | Where |
|---|---|
| Settings, session, history, bookmarks, vault, downloads list, user scripts, archive, favourites | `%APPDATA%\JBrowser\` |
| Per-space browser profiles (cookies, storage, permissions) | `%APPDATA%\JBrowser\Profiles\<space-id>\` |
| HTTP caches and favicons | `%LOCALAPPDATA%\JBrowser\Cache\` |
| Logs | `%APPDATA%\JBrowser\Logs\jbrowser.log` |
| Tracker, ad-filter and dangerous-site lists | `%APPDATA%\JBrowser\blocklist.txt`, `filters.txt`, `threats.txt` |
| Program files (installed) | `%LOCALAPPDATA%\Programs\JBrowser\` |
| Downloaded updates (temporary) | `%TEMP%\JBrowser-Update\` |

`--profile-dir PATH` (portable mode) keeps all user data in `PATH` instead. The locations are defined in
`jbrowser/paths.py`.

## Implementation notes and limitations

- **Mica with Qt WebEngine.** Widget windows are composited through Direct3D 11 from the start
  (`QT_WIDGETS_RHI=1`), and the whole window is client area (a custom `WM_NCCALCSIZE`). That lets the DWM backdrop
  show through translucent pixels while Chromium renders through D3D11.
- **DNS-over-HTTPS.** PyQt6 exposes `QWebEngineGlobalSettings.DnsMode` but not `setDnsMode()`, so JBrowser calls the
  exported Qt function through `ctypes`. If a future Qt build changes that export, the DNS selector reports that it
  is unavailable.
- **Per-space proxies.** Chromium has one network stack per process, so a space's proxy applies to all traffic while
  that space is in front, and it is re-applied on every space switch. HTTPS (TLS-to-proxy) proxies are passed at
  start-up and need a restart.
- **Tracker and ad blocking** (`services/privacy.py`, `services/adfilter.py`). `BlocklistUpdater` splits each
  downloaded list: pure domain rules go to `blocklist.txt` (a set, checked for third-party requests), and every other
  Adblock Plus rule goes to `filters.txt`. `FilterEngine` indexes network filters by their rarest token, so a request
  is only matched against a handful of candidates (tens of microseconds). `PageInterceptor` asks
  `PrivacyService.should_block()` for every request: threats first, then the per-site allowlist and `$document`
  exceptions, domain rules, network filters, and `@@` exceptions last (unless the filter is `$important`).
  Cosmetic (`##`) rules become one profile-level script in the isolated world that picks the rules for the page's
  host and adds a `<style>` before the first paint. Procedural filters (`:has-text()`, `+js()` and similar) are
  skipped. Rules with more than 4 wildcards or longer than 512 characters are skipped, and URLs are cut at 2,048
  characters, so no filter can make matching slow.
- **Looking like Chrome.** The only script in the page's main world is `privacy_js` (canvas noise and the GPC/DNT
  signals), and every function it patches reports itself as native code. Hardware values are not changed, the
  `Accept-Language` header follows the Windows display languages, and sites that run bot checks
  (`CHALLENGE_SITES` in `services/privacy.py`) get no page scripts at all. Memory-saver probes run in the isolated
  world, and WebSocket and capture detection happens in the request interceptor and permission handler, not in the
  page.
- **Gallery** (`ui/gallery.py`) is an overlay child of `SpaceStack`. While it is open, the canvases are hidden, so
  the translucent window never blends live web views into it and hidden pages stop drawing frames. Thumbnails come
  from a fresh grab of the visible cards and from the snapshots cards take when they leave view or a space is left.
  Blank grabs (a page that hasn't painted) are discarded.
- **Colour tints** (`ui/theme.py`). With a translucent material, the tint is a wash (`window_tint`, 15 % dark or
  10 % light) painted over the backdrop by `RootWidget`. With *Solid*, the tint is mixed into each `*_solid` token.
  An active incognito space overrides both with black.
- **Sound effects** use Qt Multimedia with the native Windows backend, so the build leaves out the FFmpeg plugin.
  Web video uses Chromium's own codecs.
