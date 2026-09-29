---
title: JBrowser Source Docs
nav_title: Overview
description: Developer documentation for JBrowser, the spatial, privacy-focused web browser for Windows 11.
---

This is the documentation for people who work on JBrowser's code: how it is put together, why it works the way it
does, and how to build, test and release it. It covers **JBrowser {{version}}**. Use the version button at the top to
read the documentation of another release.

JBrowser is a desktop web browser written in **Python 3.14** on **PyQt6** and **Qt WebEngine**, which embeds
Chromium. Everything you see is a Qt widget painted by JBrowser; every web page is a Chromium page that JBrowser
drives through Qt's API. There is no C++ in the repository.

!!! tip "New here?"
    Start with [Setting up](getting-started/setup.md), then read the [architecture overview](architecture/overview.md).
    The [contributor quick reference](getting-started/quick-reference.md) is the page to keep open while you work.

## Find your way

<div class="card-grid">
<a href="getting-started/setup.html"><strong>Getting started</strong><span>Set up a development environment, run JBrowser from source and make your first change.</span></a>
<a href="architecture/overview.html"><strong>Architecture</strong><span>Layers, the dependency container, the state store, settings and commands.</span></a>
<a href="engine/profiles.html"><strong>Web engine</strong><span>Per-space Chromium profiles, tab controllers, page scripts and the memory saver.</span></a>
<a href="privacy/request-pipeline.html"><strong>Privacy and security</strong><span>Request interception, the ad-filter engine, fingerprinting, threats and the password vault.</span></a>
<a href="ui/overview.html"><strong>User interface</strong><span>The window, theming, the canvas, the sidebar, the Lazy Toolbar and more.</span></a>
<a href="build/building.html"><strong>Build and release</strong><span>PyInstaller, the Inno Setup installer, releases and automatic updates.</span></a>
<a href="testing/testing-changes.html"><strong>Testing and quality</strong><span>Linting, CI, test profiles and debugging.</span></a>
<a href="reference/settings.html"><strong>Reference</strong><span>Every setting, command, shortcut and module, generated from this version's code.</span></a>
</div>

## JBrowser in one minute

- **Cards on a canvas.** A card is one web page. Cards sit left to right on a horizontally scrolling canvas instead
  of in a tab strip. See [the canvas and cards](ui/canvas-and-cards.md).
- **Spaces.** Every space has its own Chromium profile, so cookies and storage never cross between spaces.
  Incognito spaces keep everything in memory. See [profiles and spaces](engine/profiles.md).
- **One state store.** `BrowserState` holds all spaces and cards. The web engine and every widget observe it through
  Qt signals and never talk to each other directly. See [browser state](architecture/state.md).
- **Commands.** Every action is a command with an ID, a title and optional shortcuts, so a click, a key press and the
  Lazy Toolbar all run the same code. See [commands](architecture/commands.md).
- **Privacy in the request path.** Two Qt request interceptors decide, for every request, whether to block, redirect
  or add headers. See [the request pipeline](privacy/request-pipeline.md).

<!-- if >= 1.5.0 -->
## What's new for developers in {{version}}

- `jbrowser/services/adfilter.py`: a token-indexed Adblock Plus filter engine for EasyList and EasyPrivacy, with
  element hiding. See [content blocking](privacy/content-blocking.md).
- One masked main-world privacy script replaces the separate GPC, DNT and fingerprinting scripts; hardware values
  are no longer spoofed, and bot-check sites are exempt. See [fingerprinting and bot checks](privacy/fingerprinting.md).
- `jbrowser/ui/gallery.py`: the Gallery overlay. See [the Gallery](ui/gallery.md).
- Colour tints in `ui/theme.py`, card dragging in `ui/canvas.py`, `ui/sidebar.py` and `ui/window.py`.
<!-- elif == 1.4.1 -->
## What's new for developers in 1.4.1

- `master.ps1` runs the whole build and release, and `install.ps1` is the one-command installer.
- The installer closes a running JBrowser through the Windows Restart Manager instead of refusing to continue.
- `core/jsonstore.py` retries a save when an antivirus scan briefly holds the file.
- The PyInstaller spec leaves out unused Qt modules (a 30 MB smaller download).
<!-- endif -->

## Other documentation

- The [changelog](../../changelog/index.html) lists every user-visible change.
- Each folder of the repository has a `README.md` describing its files; they are the quickest way around the code.
- User-facing features are listed in [docs/FEATURES.md](source:docs/FEATURES.md).
