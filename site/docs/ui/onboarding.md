---
title: Welcome and guided tour
nav_title: Welcome and tour
description: The first-run experience in ui/onboarding.py, when it appears, and how to change it.
---

[`Onboarding`](api:jbrowser.ui.onboarding.Onboarding) ([ui/onboarding.py](source:jbrowser/ui/onboarding.py)) is the
full-window welcome: an animated intro, story slides, setup pages that apply their choices live, and a guided tour of
the real interface.

## When it appears

`app.py` starts it when `onboarding.version` in the settings is lower than `ONBOARDING_VERSION`, JBrowser wasn't
started with URLs or `--incognito`, and `JBROWSER_SKIP_WELCOME` isn't set. Finishing or skipping stores the current
version.

<!-- if >= 1.5.0 -->
`ONBOARDING_VERSION` is **2**: raising it from 1 showed the welcome once more after the update to 1.5.0, to introduce
colour tints and the Gallery.
<!-- else -->
`ONBOARDING_VERSION` is 1 in this version.
<!-- endif -->

It can be replayed at any time with *Replay welcome* in *Settings → About JBrowser*, or the *Replay the welcome
tour* command.

**Raise `ONBOARDING_VERSION`** when a release adds something the welcome introduces, and only then: every existing
user sees the whole welcome again.

## One layer, one clock

Everything is painted on one widget that covers the window (the browser UI is hidden until the tour), and a single
animation clock (`now()`) drives every effect. Each element computes its state from the time since its step began,
using the easing helpers at the top of the file (`out_cubic`, `out_back`, `seg`, `lerp`…). That keeps dozens of
effects in sync and makes *Fluid animations* off trivial: time jumps to the end.

## The steps

```text
intro → story0 … story<!-- if >= 1.5.0 -->3<!-- else -->2<!-- endif --> → look → search → shield → spaces → touches → ready → (tour)
```

| Step | Content |
|---|---|
| intro | three brand-coloured orbs swirl in on comet trails, pulse on the sound's first hit and merge into the logo; the wordmark letters hop in (timed to `intro.wav`: `T_FORM`, `T_LOGO`, `T_WORD`, `T_END`) |
| story0–<!-- if >= 1.5.0 -->3<!-- else -->2<!-- endif --> | headlines (`STORY`) rise word by word under a shimmering brand gradient<!-- if >= 1.5.0 -->; story3 introduces the Gallery with a painted mini gallery<!-- endif --> |
| look | theme and material as painted previews<!-- if >= 1.5.0 -->, and a colour-tint picker<!-- endif --> |
| search | the default search engine |
| shield | the protection level |
| spaces | name the starting spaces and pick their icons |
| touches | small preferences (sounds, animations, the bookmarks bar…) |
| ready | take the tour, or start browsing |

Setup pages are `SetupPage` widgets inside a frosted panel (`paint_glass`); `ChoiceTile` is the selectable card with
a painted preview. Every choice writes to the settings immediately, so the window behind changes as you choose.

## The tour

`begin_assemble()` fades the real browser in; `start_tour()` then moves a spotlight between parts of the interface
(`TOUR`), with a `TourBubble` explaining each one:
<!-- if >= 1.5.0 -->
spaces, favourites, the address pill (Lazy Toolbar), the canvas, the Gallery button, the card list, the Archive, the
shield and the logo (Settings).
<!-- else -->
spaces, favourites, the address pill (Lazy Toolbar), the canvas, the card list, the Archive, the shield and the logo
(Settings).
<!-- endif -->

`_target_rect()` finds each widget's rectangle, so the tour follows the real layout at any window size. While the
welcome runs, `ctx.commands.set_shortcuts_enabled(False)` keeps browser shortcuts from firing.

## Sound

`Sounds` ([ui/sounds.py](source:jbrowser/ui/sounds.py)) plays `intro.wav` and a soft `click.wav` on each step forward
through `QSoundEffect`, with the native Windows audio backend. `appearance.sounds` mutes it; if Qt Multimedia or an
audio device is missing, playback silently does nothing.
