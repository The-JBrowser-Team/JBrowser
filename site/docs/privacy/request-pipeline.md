---
title: The request pipeline
nav_title: Request pipeline
description: Every request a page makes passes two interceptors. What each one decides, and in which order.
---

Qt WebEngine lets an application inspect every network request before Chromium sends it. JBrowser uses two
`QWebEngineUrlRequestInterceptor`s, both in [services/privacy.py](source:jbrowser/services/privacy.py), and both
delegate their decisions to [`PrivacyService`](api:jbrowser.services.privacy.PrivacyService):

```text
page request
   │
   ▼
ProfileInterceptor (one per space)      rewrite():   developer host → redirect
   │                                                  tracking parameters → redirect to the clean URL
   │                                                  http → https (HTTPS-first) → redirect
   │                                    otherwise:   add DNT: 1 and Sec-GPC: 1 headers
<!-- if >= 1.5.1 -->
   │                                                 Firefox User-Agent for accounts.google.com
<!-- endif -->
   ▼
PageInterceptor (one per card)          should_block(): block, and count it on the card
   │                                    (a WebSocket request is noted for the memory saver)
   ▼
Chromium's network service
```

Qt calls the profile interceptor first, then the page's own. Both run on the UI thread for every request, so they
must be fast and must never raise: each wraps its work in `try/except` and logs failures.

## `rewrite()`: redirects

In order, the first rule that applies wins:

1. **Developer hosts.** A request to a mapped name (`app.test`) is redirected to its local target
   (`http://127.0.0.1:3000`), keeping the path and query. See [networking](../engine/networking.md#localhost-developer-hosts).
2. **Link cleaning** (`privacy.strip_tracking`, on by default). For top-level and frame `GET` navigations,
   `strip_tracking()` removes known tracking parameters: `utm_*`, `fbclid`, `gclid`, `msclkid`, `mc_eid` and about
   40 more, plus site-specific ones such as YouTube's `si` or Amazon's `ref_`. Allowed sites are skipped.
3. **HTTPS-first** (`privacy.https_upgrade`, off by default). A main-frame `http://` navigation to a public host is
   redirected to `https://`. If the site bounces back to http within 4 seconds, or the https version fails to load or
   has a certificate error, JBrowser opens the original http page instead, shows a "not encrypted" warning, and
   doesn't try that host again this session.

If nothing redirects, the interceptor adds `DNT: 1` (`privacy.dnt`) and `Sec-GPC: 1` (`privacy.gpc`).
<!-- if >= 1.5.1 -->

[[new 1.5.1]] Requests to Google's sign-in server (`SIGNIN_UA_HOSTS`, `accounts.google.com`) also get a Firefox
`User-Agent` header, so Google lets the user sign in. [Fingerprinting and bot checks](fingerprinting.md#google-sign-in)
explains why.
<!-- endif -->
<!-- if >= 1.6.0 -->
[[new 1.6.0]] While a page is on that server, its whole space presents Firefox, not just these requests
([engine/signin.py](source:jbrowser/engine/signin.py)).
<!-- endif -->
<!-- if >= 1.5.2 -->

[[new 1.5.2]] **Local files.** Before anything else, a request from a local page (`file://`) for another local file
is blocked when it could read the file's contents (fetch/XHR, frames, objects, workers: `_FILE_READ_TYPES`). Qt lets
local pages read any local file, unlike Chrome, so a downloaded HTML file opened in JBrowser could otherwise read the
user's documents. Images, style sheets, scripts, fonts and media still load, so saved web pages look right.
<!-- endif -->

## `should_block()`: blocking

<!-- if >= 1.5.0 -->
In order:

1. **Main-frame navigations are never blocked here**: a page you asked for always loads (dangerous sites are stopped
   earlier, in `BrowserPage.acceptNavigationRequest`).
2. **Local hosts** (localhost, private addresses) are never blocked.
3. **Threats**: a sub-resource or frame from a known phishing or malware host is always blocked, even with tracker
   blocking off.
4. With `privacy.block_trackers` off, stop here.
5. **The allowed list**: when the page's own site (the first party) is on `privacy.allowlist`<!-- if >= 1.5.2 -->, or is a sign-in page (`SIGNIN_PAGE_HOSTS`, [why](fingerprinting.md#google-sign-in))<!-- endif -->, nothing is blocked.
<!-- if >= 1.6.0 -->
   [[new 1.6.0]] **Google talking to Google** isn't filtered either: a request from a Google page (any `google.*`,
   `gstatic.com` or `googleapis.com` host, `_GOOGLE_HOST`) to another of those hosts. Blocking Google's own pings and
   logs on its own pages made Google Search answer with "unusual traffic" pages and CAPTCHAs. Ad and tracker hosts
   such as `doubleclick.net` are other domains and stay blocked.
<!-- endif -->
6. **List exemptions**: `@@||site^$document` rules in the filter lists exempt a site completely.
7. **Domain rules** (`Blocklist`: the built-in list plus the downloaded domain lists) block **third-party** requests
   to tracker and ad domains.
8. **Network filters** (`FilterEngine.blocking_filter`) match the full URL, the request type and the first party
   against the Adblock Plus rules.
9. **Exceptions**: if something matched, `@@` rules can still allow the request, unless the matching filter was
   `$important`.

The request type comes from Qt's resource type (`_RTYPE` maps script, image, stylesheet, font, sub-document, XHR,
media, ping, object, WebSocket and "other"). Third-party means the request's registrable domain differs from the
first party's (`registrable_domain()` in [core/urls.py](source:jbrowser/core/urls.py)).

The [content blocking](content-blocking.md) page explains the lists and the filter engine.
<!-- else -->
1. Main-frame navigations and local hosts are never blocked here.
2. **Threats**: sub-resources and frames from known phishing or malware hosts are always blocked.
3. With `privacy.block_trackers` off, stop here.
4. When the first party is on `privacy.allowlist`, nothing is blocked.
5. **Third-party** requests to a domain on the blocklist (the built-in list plus the whole-domain rules extracted
   from the downloaded lists) are blocked, as are a few built-in path rules.

This version blocks by domain only. URL-pattern rules, exceptions and element hiding came with the filter engine in
1.5.0.
<!-- endif -->

A blocked request increments `tab.blocked`, which the shield button in the address pill shows.

## Cookies

Each profile's cookie store has a filter, `PrivacyService.allow_cookie()`. With
`privacy.block_third_party_cookies` on (the default), third-party cookies are refused, except:

<!-- if >= 1.5.0 -->
- cookies set by CAPTCHA providers (`CAPTCHA_COOKIE_SITES`: reCAPTCHA, hCaptcha, Cloudflare challenges, Arkose
  Labs), which keep their "this person already passed" state in their own cookies; without them every site shows a
  harder challenge;
<!-- endif -->
<!-- if >= 1.6.0 -->
- [[new 1.6.0]] Google's reCAPTCHA (`www.google.com/recaptcha/…`, `recaptcha.google.com`) and "Sign in with Google"
  (`accounts.google.com`) inside other sites (`CAPTCHA_COOKIE_PATHS`, matched on the host and the path of the address
  using the cookie). Without them reCAPTCHA met every visitor who isn't signed in to Google as a stranger and asked
  "I'm not a robot" far more often. Google's other third-party cookies stay blocked;
<!-- endif -->
- on sites where protection is switched off (the allowed list).

## Adding a rule

- Something that changes the URL: add it to `rewrite()`, keep it cheap, and return `None` quickly for the common case.
- Something that blocks: put it in `should_block()` at the right place in the order above, and make sure it can't
  block main-frame navigations.
- Always test with a page that makes many requests (a news site) and watch the log for exceptions.
