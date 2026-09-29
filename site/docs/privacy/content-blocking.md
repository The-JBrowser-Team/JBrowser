---
title: Content blocking and the filter engine
nav_title: Content blocking
description: The lists JBrowser downloads, how they are split, and how the Adblock Plus engine matches requests and hides ad boxes.
---

<!-- if >= 1.5.0 -->
[[new 1.5.0]] JBrowser blocks ads and trackers with the same lists the big blockers use, read by its own Adblock
Plus engine, [services/adfilter.py](source:jbrowser/services/adfilter.py). There are three stages: download and split
the lists, match every request, and hide the empty boxes that blocked ads leave behind.
<!-- else -->
In this version JBrowser blocks trackers and ads **by domain**: the built-in list plus the whole-domain rules it
extracts from downloaded lists. Element hiding and full Adblock Plus rules arrived in 1.5.0.
<!-- endif -->

## The lists

`BLOCKLIST_SOURCES` in [services/privacy.py](source:jbrowser/services/privacy.py):

| List | Kind |
|---|---|
| EasyPrivacy | trackers and telemetry (Adblock Plus syntax) |
| EasyList | ads (Adblock Plus syntax) |
| Peter Lowe's ad and tracking servers | hosts file |
| NoCoin | cryptominers (hosts file) |

On top of them, [services/blocklist_data.py](source:jbrowser/services/blocklist_data.py) ships a built-in list of
ad, tracker, miner and telemetry domains, so blocking works before anything is downloaded.

The lists refresh in the background once a week (`privacy.blocklist_auto`, `privacy.blocklist_updated`), 12 seconds
after start-up, through the global proxy if one is set. *Update lists now* in *Settings → Privacy and security*
(or the *Update tracker blocklists* command) refreshes them at once; *Use built-in list only* deletes the downloaded
ones and stops the weekly refresh.

<!-- if >= 1.5.0 -->
## Splitting a list

`BlocklistUpdater` (a `QThread`) downloads every list with `fetch_text()` (streamed, cancellable, at most 64 MB) and
passes it through `split_list()`:

- `||domain^` rules with no options (or only `$third-party`), hosts-file lines and bare domains go to
  **`blocklist.txt`**: a set of domains, looked up by `Blocklist.match()` in constant time;
- everything else goes to **`filters.txt`**: URL patterns, exceptions, options and element-hiding rules for the
  `FilterEngine`.

Both files are written atomically, then `PrivacyService` reloads them and emits `blocklistUpdated`, which makes
`ProfileManager` reinstall the element-hiding script.

## Network filters

`FilterEngine.from_text()` parses `filters.txt` into `NetworkFilter` objects:

| Syntax | Meaning |
|---|---|
| `||example.com^` | the domain and its sub-domains, any scheme |
| `|https://` / `…|` | anchored at the start / end of the URL |
| `*` | any characters |
| `^` | a separator: anything but a letter, digit, `_ - . %`, or the end |
| `@@…` | an exception |
| `$script,image,…`, `$~image` | only / never these request types (`css`, `xhr`, `frame`, `beacon` are aliases) |
| `$third-party`, `$~third-party`, `$1p`, `$3p` | only third-party / only first-party requests |
| `$domain=a.com|~b.a.com` | only on these first-party sites / never on these |
| `$important` | cannot be overridden by an exception |
| `@@||site^$document` | no blocking at all on `site` |
| `@@||site^$elemhide`, `$generichide` | no element hiding / no generic element hiding on `site` |

Filters with options JBrowser can't honour (`$popup`, `$csp`, `$removeparam`, `$redirect`-only behaviour and others
in `_UNSUPPORTED`) are skipped rather than approximated, as are regular-expression filters.

### Fast matching: tokens

Checking ~13,000 filters for every request would be far too slow. Like Adblock Plus, the engine files every filter
under **one token**: the longest run of `[a-z0-9%]` (three or more characters) that the URL must contain as a whole
word (`_best_token()`). A token next to a `*` is not used, because the wildcard could extend it.

For a request, `_candidates()` splits the URL into its tokens and only tests the filters filed under those tokens,
plus the few filters that have no usable token. A typical request checks a handful of filters: matching costs about
10 to 40 microseconds. Each filter's regular expression is compiled on first use (`_to_regex()`), so start-up only
parses text.

### Safety valves

The lists come from the internet, so nothing in them may make JBrowser slow or crash it:

- patterns with more than `MAX_WILDCARDS` (4) `*`, or longer than 512 characters, are skipped: they could
  backtrack badly;
- URLs are cut to `MAX_URL` (2,048) characters before matching;
- a line that fails to parse is skipped without affecting the rest.

## Element hiding

Blocking an ad request leaves an empty frame, often labelled "Advertisement". `##` rules hide those elements:

| Syntax | Meaning |
|---|---|
| `##.ad-slot` | hide on every site (generic) |
| `example.com,news.org##.promo` | hide on these sites (specific) |
| `~example.com##.ad` | a generic rule except on these sites |
| `example.com#@#.ad` | don't hide `.ad` on this site |

Procedural and extended syntax (`:has-text()`, `:-abp-…`, `#?#`, `#$#`, scriptlets `+js()`) and selectors containing
braces are skipped.

### Why a profile script, not a style sheet per page

A style sheet has to be in place **before the page first paints**, or the ads flash up and vanish. Qt only applies a
script added to a page from the *next* navigation on, so JBrowser can't insert per-site CSS when a navigation starts.
Instead, `cosmetic_data()` compacts all the rules into one JSON payload (`g` generic, `s` specific, `u` exceptions,
`k` generic-rule exclusions, `nc`/`ng` sites without cosmetic/generic hiding), and `cosmetic_js()` wraps it into a
single **profile script** (`jb:cosmetic`, isolated world, document creation). In every page it:

1. builds the host chain (`a.b.example.com`, `b.example.com`, `example.com`);
2. stops on sites where hiding is off, or that the user allowed;
3. collects the generic selectors (minus exceptions and exclusions) and the site's specific ones;
4. adds one `<style>` with one `display:none!important` rule per selector, so a selector Chromium doesn't understand
   only drops its own rule; if `<html>` doesn't exist yet, a `MutationObserver` adds it the moment it does.

The payload is built once per list version and cached in `PrivacyService` (keyed by the engine and the allowed list).

## Checking what gets blocked

- The shield in the address pill shows how many requests were blocked on the current page (`tab.blocked`).
- `FilterEngine.css_for(host)` returns the exact style sheet a site gets, for tests and diagnostics.
- The log reports the list sizes when they load:
  `Filter engine: 13013 network filters, 23956 element-hiding rules`.
<!-- else -->
## How blocking works in this version

`BlocklistUpdater` downloads every list and `parse_filter_list()` keeps only whole-domain rules: `||domain^` without
`$domain=` or first-party options, hosts-file lines and bare domains. They are written to `blocklist.txt` and merged
with the built-in list. `PrivacyService.should_block()` then blocks third-party requests to any of those domains or
their sub-domains ([the request pipeline](request-pipeline.md)).

Everything else in EasyList and EasyPrivacy (URL patterns, exceptions, element hiding) is ignored, which is why ads
served from a site's own domain, and the empty boxes of blocked ads, still show.
<!-- endif -->
