---
title: Architecture overview
nav_title: Overview
description: The layers of JBrowser, the dependency container and how an action travels through the code.
---

JBrowser is one Python process running a Qt event loop, plus the Chromium renderer processes
(`QtWebEngineProcess.exe`) that Qt WebEngine starts for web pages. All of JBrowser's own code runs on the Qt main
thread, apart from a few background downloads.

## Layers

```text
            ┌──────────────────────── jbrowser/ui ─────────────────────────┐
 user ────► │ MainWindow · TitleBar · Sidebar · Canvas/WebCard · LazyToolbar │
<!-- if >= 1.5.0 -->
            │ Gallery · dialogs/ · Onboarding · BrowserController · actions  │
<!-- else -->
            │ dialogs/ · Onboarding · BrowserController · actions (commands) │
<!-- endif -->
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
never import `ui`. Upper layers call down directly; lower layers report back up only through **Qt signals** or the
small `UiHooks` interface. This is what lets the engine, the state and the services start before any window exists,
and what keeps widgets from depending on each other.

| Layer | Knows about | Must not import |
|---|---|---|
| `core`, `platform` | Python, Qt | anything else in `jbrowser` |
| `models` | `core` | `services`, `engine`, `ui` |
| `services` | `core`, `models` | `engine`<!-- if >= 1.5.0 -->*<!-- endif -->, `ui` |
| `engine` | `core`, `models`, `services` | `ui` |
| `ui` | everything | |

<!-- if >= 1.5.0 -->
\* `services/privacy.py` imports `engine/js.py` lazily, only to build the element-hiding script, because all
injected JavaScript lives in one place.
<!-- endif -->

## The dependency container: `AppContext`

[`jbrowser/context.py`](source:jbrowser/context.py) creates every non-UI object once, in dependency order, and
holds no globals. Everything else receives the context (usually as `ctx`) and reaches services through it:

```python
ctx.settings      # core.settings.Settings
ctx.state         # models.state.BrowserState
ctx.commands      # core.commands.CommandRegistry
ctx.history, ctx.bookmarks, ctx.vault, ctx.privacy, ctx.threats, ctx.downloads, ...
ctx.profiles      # engine.profiles.ProfileManager
ctx.engine        # engine.registry.EngineRegistry (one TabController per card)
ctx.lifecycle     # engine.lifecycle.LifecycleManager
ctx.session       # services.session.SessionManager
ctx.hooks         # UiHooks: what the engine may ask of the UI
```

The construction order is **state → services → engine → session**, and the constructor also wires services to each
other (for example the Archive follows history deletions). Read the constructor of `AppContext`: it is the table of
contents of the application.

`ctx.hooks` starts as a do-nothing `UiHooks` and is replaced by `WindowHooks` when the main window exists. The engine
uses it for the few things that need a widget: asking for HTTP credentials, unlocking the vault, creating popup
windows, toasts and notifications.

## The UI side

- `MainWindow` ([`ui/window.py`](source:jbrowser/ui/window.py)) builds the sidebar, title bar and `SpaceStack`, and
  creates the `BrowserController`.
- `BrowserController` ([`ui/controller.py`](source:jbrowser/ui/controller.py)) is **what every user intent does**:
  open a URL, close a card, switch space, open a dialog.
- `register_commands()` ([`ui/actions.py`](source:jbrowser/ui/actions.py)) turns those intents into
  [commands](commands.md) with titles, shortcuts and Lazy Toolbar keywords.
- Widgets observe `BrowserState`, `Tab` models and settings, and never call each other.

## Following one action through the code

What happens when you press **Ctrl+W**:

1. The `QShortcut` installed by `CommandRegistry.install_shortcuts()` fires and runs the command `card.close`.
2. Its handler calls `BrowserController.close_selected()`, which calls `close_tab()` for each selected card.
3. `close_tab()` reads the card's back/forward history from its `TabController` and calls
   `BrowserState.remove_tab()`.
4. `BrowserState` removes the `Tab` and emits signals. Each listener does its own part, without knowing about the
   others:
    - `tabArchived` → `ArchiveService.add_closed()` keeps the card for 48 hours (not for incognito spaces);
    - `tabRemoved` → the canvas and the sidebar drop the card's widgets, and `EngineRegistry` disposes the
      `TabController` on the next event-loop turn, after the view is gone;
    - `activeTabChanged` → the title bar shows the newly focused card;
    - `dirty` → `SessionManager` schedules a save 2.5 seconds later.

The same `remove_tab()` runs when a page closes itself, when you middle-click a card, or when you close a card from
the Lazy Toolbar or the Gallery. That is the point of the design: one path for every way in.

## Threads and processes

- **Main thread:** all widgets, all JBrowser logic, all Qt WebEngine calls (Qt requires that).
- **Worker threads:** filter-list and threat-list downloads (`QThread` subclasses using `requests`), stopped safely
  with `stop_worker()` from [`core/workers.py`](source:jbrowser/core/workers.py).
- **Asynchronous network:** update checks, search suggestions and the port probe use Qt's asynchronous APIs, so
  they never block.
- **Chromium processes:** one or more `QtWebEngineProcess.exe` renderers, plus Chromium's GPU and network
  services. JBrowser never talks to them directly, only through Qt's API.

## Read next

- [Start-up and shutdown](startup-shutdown.md): the exact order in `app.py`.
- [Browser state and the update pipeline](state.md): how engine events reach widgets.
- [Profiles and spaces](../engine/profiles.md): how isolation works.
