---
title: Glossary
description: The words used in JBrowser's code and documentation.
---

AppContext
:   The dependency container that creates and holds every service ([architecture](../architecture/overview.md#the-dependency-container-appcontext)).

Archive
:   Cards closed in the last 48 hours, with their back/forward history; never for incognito spaces.

BrowserController
:   `ui/controller.py`: what every user intent does. Widgets and commands call it.

BrowserState
:   The single store of spaces, cards, focus and selection ([browser state](../architecture/state.md)).

BRIDGE_WORLD
:   JBrowser's isolated script world (ID 1); pages can't see scripts or objects in it.

Canvas
:   The horizontally scrolling surface of one space, holding its cards.

Card
:   One web page on the canvas. The UI object is `WebCard`, the state is `Tab`, the engine side is `TabController`.
    "Tab" survives in code names for historical reasons.

CHALLENGE_SITES
:   Sites that run bot checks or sign-ins; JBrowser changes nothing in their pages ([fingerprinting](../privacy/fingerprinting.md)).

Command
:   A named action with an ID, a title and optional shortcuts ([commands](../architecture/commands.md)).

Discard
:   Chromium's `Discarded` lifecycle state: the renderer is freed. JBrowser calls it *sleeping*.

Element hiding
:   `##` filter rules that hide page elements, such as empty ad frames ([content blocking](../privacy/content-blocking.md)).

Favourite
:   A site pinned above the spaces in the sidebar; it works in every space.

First party
:   The site of the page itself (`info.firstPartyUrl()`); a request to another registrable domain is third-party.

Freeze
:   Chromium's `Frozen` lifecycle state: JavaScript timers and tasks pause.
<!-- if >= 1.5.0 -->

Gallery
:   The overlay grid of every card, in one space or all of them ([the Gallery](../ui/gallery.md)).
<!-- endif -->

Incognito space
:   A space with an off-the-record profile: nothing is written to disk.

Info bar
:   A bar inside a card that asks or tells the user something (permissions, *Save password?*, crashes).

Lazy Toolbar
:   The command overlay that replaces the new-tab page and the address bar ([Lazy Toolbar](../ui/lazy-toolbar.md)).

Material
:   The window backdrop: Acrylic, Mica, Mica Alt or Solid.

Memory saver
:   Putting idle cards to sleep after a chosen time ([lifecycle](../engine/lifecycle.md)).

Pipeline
:   `TabUpdatePipeline`: coalesces `Tab` changes and delivers them once per frame.

Profile
:   A `QWebEngineProfile`: cookies, storage, cache and permissions. One per space.

Registrable domain
:   The part of a host name a person can register (`example.co.uk` for `a.b.example.co.uk`), approximated by
    `registrable_domain()`.

Ribbon
:   The title bar: navigation, the address pill, tools and window buttons. Also the header of a card.

Snapshot
:   A picture of a card taken while it still renders, shown while it sleeps<!-- if >= 1.5.0 --> and used by the Gallery<!-- endif -->.

Space
:   An isolated workspace with its own profile, cards, name, icon and colour.

Throttle
:   Hiding an out-of-sight page so it stops drawing, and freezing it when safe.
<!-- if >= 1.5.0 -->

Tint
:   A colour wash over the window (`appearance.tint`) ([theming](../ui/theming.md#colour-tints)).
<!-- endif -->

Token (filter engine)
:   A word a URL must contain for a filter to be checked at all.

Token (theme)
:   A named colour in the palette, such as `text2` or `card_solid`.
