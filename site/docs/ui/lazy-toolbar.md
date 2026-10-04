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
<!-- if >= 2.0.1 -->

## Addresses, files and searches

`looks_like_url()` and `to_url()` in [core/urls.py](source:jbrowser/core/urls.py) decide whether input is an address.
[[new 2.0.1]] `local_path()` recognises file and folder locations before anything else, spaces included:
`C:\…` and `C:/…`, network paths (`\\server\share`, but not `\\?\` or `\\.\` device paths), `%VARIABLE%\…` (expanded)
and paths in quotes, as Explorer's *Copy as path* writes them. They become `QUrl.fromLocalFile()` addresses, and the
top result reads *Open C:\…* with *File on this PC* or *Folder on this PC* (decided from the text alone: a network
path can take seconds to answer). `file:` input with backslashes or unencoded spaces is cleaned up the same way.
A single-label host with a four- or five-digit port (`nas:5000`), or any port followed by a path (`pi:80/admin`),
opens over `http://`; `psalm:23` stays a search. Input that counts as an address is never sent for suggestions.

Command-line arguments (file associations, *Open with*) go through the same `resolve_input()`; `app.py` makes
relative paths absolute first, because a running copy that receives them has a different working folder.
<!-- endif -->

## Performance

The list is a `QListView` over a `ResultModel` with a custom delegate, so hundreds of rows cost nothing. Each keystroke
rebuilds the sections synchronously (the sources are in memory or SQLite); suggestions arrive asynchronously, are
debounced, and a newer request cancels an older one.
