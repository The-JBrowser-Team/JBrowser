---
title: The Lazy Toolbar
description: The command overlay that replaces the new-tab page and the address bar, and how it finds and ranks results.
---

The [`LazyToolbar`](api:jbrowser.ui.lazy_toolbar.LazyToolbar) ([ui/lazy_toolbar.py](source:jbrowser/ui/lazy_toolbar.py))
is a centred `Overlay` with one text box and a result list. It replaces both the new-tab page and the omnibox.

## Modes

`BrowserController.open_lazy_toolbar(mode, text, insert_at)` opens it in one of three modes:

| Mode | Opened by | Enter does | Shift+Enter does |
|---|---|---|---|
| `new` | Ctrl+T, *New card*, pull-to-add | opens a new card (at `insert_at` when pulled from an end) | opens in the current card |
| `current` | Ctrl+K on a card | opens in the current card | opens a new card |
| `edit` | Ctrl+L, F6, Alt+D, clicking the address pill | edits the current address, pre-filled and selected | opens a new card |

Tab completes the selected result into the box. Escape or a click outside closes it.

## Sources and sections

Nothing is shown until the user types. Then `refresh()` builds the list from sections, in this order:

| Section | Source | Limit (normal / with prefix) |
|---|---|---|
| Top result | `resolve_input()`: a URL, a keyword search (`yt lofi`), a developer host, or a web search | |
| Open cards | every card in every space, `best_match()` on title and URL, +5 for the current space | 4 / 12 |
| Bookmarks | `BookmarkService`, matched on title, URL and folder | 3 / 20 |
| History | `HistoryService.pages_matching()`, fuzzy score + frecency | 5 / 25 |
| Suggestions | Google Suggest (`SuggestionClient`), never from incognito spaces, off with `search.suggestions` | 5 |
| Commands | the [command registry](../architecture/commands.md), matched on title, keywords and category, with live state ("On", "Active") and the shortcut | 4 / 40 |
| Passwords | the vault, matched on host and username (only with 3+ characters or `$`) | 3 / 12 |

A **prefix** narrows the search to one section: `>` commands, `@` cards, `*` bookmarks, `#` history, `$` passwords.

## Matching and ranking

[core/fuzzy.py](source:jbrowser/core/fuzzy.py) is a small fzf-style matcher: the query's characters must appear in
order; consecutive characters, word-boundary hits and prefix matches score higher. `best_match()` tries several fields
and slightly prefers the first (the title). Matched character positions are returned, and the delegate highlights
them.

History results add **frecency** (`PageStat.frecency()` in [services/history.py](source:jbrowser/services/history.py)):
visits weighted by how recent they are, so the pages you actually use rise to the top.

## Keyword searches

`search.keywords` holds shortcuts such as `g`, `ddg`, `yt`, `w`, `gh`, `maps`, `mdn`, `py`, `so`, `pypi`, `npm`
and `r` (see `DEFAULT_SEARCH_KEYWORDS` in [core/settings.py](source:jbrowser/core/settings.py)). Typing
`yt lofi beats` searches YouTube directly. The default engine (`search.engine`) handles everything else.

## Performance

The list is a `QListView` over a `ResultModel` with a custom delegate, so hundreds of rows cost nothing. Each keystroke
rebuilds the sections synchronously (the sources are in memory or SQLite); suggestions arrive asynchronously, are
debounced, and a newer request cancels an older one.
