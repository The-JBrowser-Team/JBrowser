---
title: Reading mode
nav_title: Reading mode
description: How JBrowser finds articles, pulls them out of the page and shows them without the clutter.
since: 2.0.0
---

[[new 2.0.0]] Reading mode shows an article's text and pictures without the rest of the page. It has three parts.

## Detecting articles

[engine/reader.py](source:jbrowser/engine/reader.py) uses **Mozilla Readability** (0.6.0, the engine behind Firefox
Reader View), vendored unmodified in `jbrowser/engine/vendor/readability/` under the Apache License 2.0 and shipped as
data files by `JBrowser.spec`.

`TabController._check_readable()` runs `Readability-readerable.js` (`readerable_js()`) in JBrowser's isolated world
(`BRIDGE_WORLD`) 0.7 s after a page loads, or 1.5 s after a single-page site changes its address. It shares the page's
DOM but not its JavaScript, so the page can't see or influence it. The result goes into `tab.readable`; a new address
resets it, and leaves reading mode.

## Extracting and showing the article

`TabController.extract_article()` runs `Readability.js` on a clone of the document (`extract_js()`, also in the
isolated world) and returns the title, byline, site name, language, direction, length and cleaned HTML.
`BrowserController.set_reading()` passes it to `WebCard.show_reader()`, which shows a
[`ReaderView`](source:jbrowser/ui/reader_view.py) in the card's stack, in front of the live page:

- The article is rendered by `reader.render()` into a page loaded with `setHtml()` and the article's address as its
  base URL. A Content-Security-Policy meta tag allows no scripts, frames, forms or plugins; Readability has already
  removed scripts. Pages bigger than `setHtml()`'s 2 MB limit drop large inline images first, then shorten the text.
- The page uses `ProfileManager.reader_profile()`: an in-memory profile with no JBrowser page scripts, no cookies and
  the same browser identity as the spaces. The card's own request interceptor is attached, so trackers in the article
  stay blocked.
- The `ReaderBar` sets the font (`reading.font`: serif or sans), the colours (`reading.theme`: auto, light, sepia,
  dark) and the text size (`reading.zoom`, the page's zoom factor). Font and colours switch by changing the classes
  of the article's `<html>` element from the isolated world, so the reading position is kept.
- A link opens in the card and leaves reading mode; Ctrl+click or middle-click opens it as a background card
  (`_LinkCatcher`). Back, forward, reload, sleep and any new address leave reading mode too.

## The suggestion

`ReadingOffer` appears at the bottom of the card when the page is readable, the card is active, the window has focus,
`reading.offer` is on and the page hasn't been offered before in this session (`BrowserController.claim_reading_offer`).
It waits until you scroll well into the article or stay on it for 9 seconds. *Don't show again* turns `reading.offer`
off (Settings → Appearance turns it back on). It is drawn solid: Qt composites a partly transparent widget over a web
page far more see-through than its alpha suggests (`theme.solid()`).

## Buttons and shortcuts

- The ribbon's reading button (`TitleBar.reading_btn`) is a toggle; its glyph turns to the accent colour on articles.
- A card shows its own reading button when its page is readable.
- **F9** and **Alt+Shift+R** (`view.reading`) toggle reading mode for the active card; *Reading mode* is also in the
  card menu and the ··· menu → Page.
