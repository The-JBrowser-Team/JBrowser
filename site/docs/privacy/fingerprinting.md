---
title: Fingerprinting and bot checks
nav_title: Fingerprinting and bot checks
description: What JBrowser changes to resist fingerprinting, and what it deliberately leaves alone so sites don't mistake it for a bot.
---

Two goals pull in opposite directions. **Fingerprinting protection** wants the browser to look different on every
site, so sites can't recognise the user. **Bot checks** (Google's "unusual traffic" page, Cloudflare's "Checking your
browser", reCAPTCHA, hCaptcha) look precisely for browsers that don't look like ordinary Chrome, because automation
tools are the ones that change things.

<!-- if >= 1.5.0 -->
[[changed 1.5.0]] JBrowser resolves this by changing **one** thing that matters most for tracking, doing it
invisibly, and being indistinguishable from Chrome in everything else.

## What JBrowser changes

**Canvas read-backs get per-site noise** (`privacy.fingerprint_protection`, on by default). Drawing text or shapes
on a `<canvas>` and reading the pixels back is the strongest fingerprint a script can take, because it reveals the
exact GPU, driver and font rendering. `privacy_js` ([engine/js.py](source:jbrowser/engine/js.py)) wraps
`getImageData()`, `toDataURL()` and `toBlob()` so the returned pixels have a few bits flipped:

- the noise is derived from a **per-session seed** (a new random number each time JBrowser starts) and the **host**,
  so one site sees stable values during a session (its own features keep working) while two sites see different
  values and can't correlate them;
- about 2 % of pixels change by one bit in one colour channel, invisible to people;
- `toDataURL()` and `toBlob()` work on a noisy copy, so the page's own canvas is never modified;
- very large canvases (over 16 million pixels) are passed through untouched.

**`navigator.globalPrivacyControl`** and **`navigator.doNotTrack`** report the user's choice, matching the `Sec-GPC`
and `DNT` headers the [request pipeline](request-pipeline.md) sends.

## Doing it invisibly

A script that replaces built-in functions is easy to spot: `getImageData.toString()` would show JavaScript source
instead of `[native code]`, the replacement would have a `prototype` or the wrong `length`. `privacy_js` masks all of
that ([page scripts](../engine/page-scripts.md#keeping-the-main-world-script-invisible)). It is the only JBrowser
script in the page's own world; everything else runs in the isolated world, where pages can't see it.

## What JBrowser deliberately leaves alone

| Not changed | Why |
|---|---|
| CPU cores (`hardwareConcurrency`), memory (`deviceMemory`) | Workers report the real values and can't be patched; a mismatch between the page and a worker is a classic bot signal. |
| The WebGL vendor and renderer | A generic "ANGLE (Generic Renderer)" contradicts every other GPU detail and is itself unusual. |
| The user agent | Qt's `QtWebEngine/x.y` token is removed, so the user agent is exactly Chrome's<!-- if >= 1.5.1 --> (except on [Google's sign-in server](#google-sign-in))<!-- endif -->. |
| `Accept-Language` | Built from the Windows display languages like Chrome's (`en-AU,en;q=0.9`). Qt sends none by default, which no real browser does. |

## Sites that get no changes at all

`CHALLENGE_SITES` in [services/privacy.py](source:jbrowser/services/privacy.py) lists the CAPTCHA and bot-check
providers and the big sign-in pages: Google (and every `google.*` domain), gstatic, reCAPTCHA, YouTube, hCaptcha,
Cloudflare, Arkose Labs / FunCaptcha, Microsoft sign-in (`microsoftonline.com`, `live.com`, `microsoft.com`), Apple
and iCloud, PayPal. On those sites `privacy_js` returns immediately, and CAPTCHA providers may keep their third-party
cookies ([cookies](request-pipeline.md#cookies)). Sites on the user's allowed list are treated the same way.
<!-- if >= 1.5.1 -->

## Google sign-in

[[new 1.5.1]] Google refuses to sign in browsers it takes for a web view embedded in another app, with *"Couldn't
sign you in. This browser or app may not be secure."* A Chromium-based Qt WebEngine browser looks like one to its
checks. JBrowser does what other Qt WebEngine browsers do (qutebrowser calls it the `ua-google` quirk):
requests **to `accounts.google.com`** carry a current **Firefox** user agent, which Google's sign-in accepts.

- `ProfileInterceptor` ([request pipeline](request-pipeline.md)) sets the `User-Agent` header when the request's host
  is in `SIGNIN_UA_HOSTS`, in every space, incognito included. Every other site, Google's other services and
  JavaScript's `navigator.userAgent` still see Chrome.
- `firefox_user_agent()` works out the Firefox version from the date (Firefox 140 came out on 24 June 2025, and a new
  version follows every four weeks), so the user agent never looks years old. It counts 30 days per version, so it
  never names a version that doesn't exist yet.
- Once signed in, the Google account works everywhere, because the sign-in cookies belong to the space, not the user
  agent.

If Google changes its checks and sign-in breaks again, test a newer Firefox user agent, or a user agent from another
browser, against a Google account in a throw-away space before changing `SIGNIN_UA_HOSTS` or the helper.
<!-- endif -->

## If a site still shows a challenge

1. Check the site isn't blocked by a filter it depends on: switch protection off for it from the shield menu and
   reload. If that fixes it, the site belongs on the allowed list, or a filter exception is missing upstream.
2. Check the network: a VPN, a shared IP or a proxy makes challenges far more likely, in any browser.
3. For a CAPTCHA or sign-in provider missing from `CHALLENGE_SITES`, add its registrable domain there.
<!-- else -->
## What this version changes

`fingerprint_js()` ([engine/js.py](source:jbrowser/engine/js.py)), installed as `jb:fingerprint` in the page's main
world when `privacy.fingerprint_protection` is on:

- per-site, per-session **noise in canvas read-backs** (`getImageData`, `toDataURL`, `toBlob`);
- a generic **WebGL** vendor and renderer ("Google Inc.", "ANGLE (Generic Renderer)");
- **4 CPU cores** (`navigator.hardwareConcurrency`) and **8 GB of memory** (`navigator.deviceMemory`).

`GPC_JS` and `DNT_JS` set `navigator.globalPrivacyControl` and `navigator.doNotTrack`. Sites on the allowed list are
skipped.

!!! warning "Known issue"
    Bot checks detect these main-world changes: the patched functions don't report `[native code]`, and workers see
    the real CPU and memory values while the page sees the fake ones. Google and Cloudflare then show CAPTCHAs far
    more often. 1.5.0 keeps only the (masked) canvas noise, adds a Chrome-like `Accept-Language` header and exempts
    sign-in and bot-check sites.
<!-- endif -->
