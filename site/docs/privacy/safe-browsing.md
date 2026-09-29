---
title: "Safe browsing: threats, HTTPS-first and downloads"
nav_title: Safe browsing
description: Phishing and malware protection, HTTPS-first, link cleaning, look-alike addresses and download protection.
---

## Phishing and malware protection

[`ThreatService`](api:jbrowser.services.threats.ThreatService) ([services/threats.py](source:jbrowser/services/threats.py))
keeps a local set of known dangerous hosts, built from two public feeds (`THREAT_SOURCES`):

- **URLhaus** malware hosts (abuse.ch);
- **Phishing Army**.

The set lives in `threats.txt`, refreshes weekly in the background 8 seconds after start-up, and is checked
**locally**: the addresses a user visits are never sent anywhere. `match(host)` checks the host and each of its
parent domains. `_NEVER_BLOCK` lists huge shared hosts (Google, GitHub, Microsoft, Dropbox, Discord, Wikipedia, cloud
storage) that must never be blocked wholesale even if a feed lists them by mistake.

Where it applies:

1. **Top-level navigations**: `BrowserPage.acceptNavigationRequest()` refuses them and, one event-loop turn later,
   `TabController.show_threat()` shows a warning page (`INTERSTITIAL_HTML`) with an info bar:
   *Go back to safety* or *Continue anyway (unsafe)*. Continuing allows the host until JBrowser restarts
   (`allow_for_session`).
2. **Sub-resources and frames**: `should_block()` blocks them, even with tracker blocking switched off.

Setting: `privacy.threat_protection` (on by default).

## HTTPS-first

With `privacy.https_upgrade` on, `PrivacyService.rewrite()` redirects main-frame `http://` navigations to `https://`
(public hosts only). `TabController` handles the ways that can fail:

| What happens | Result |
|---|---|
| the https page loads | done: the user is on the encrypted version |
| the site redirects back to http within 4 s | the host is remembered as http-only for the session |
| the https version fails to load | the http page opens, with a "not encrypted" info bar |
| the https version has a certificate error | JBrowser, not the site, chose https, so the error is rejected quietly and the http page opens |

## Link cleaning

`strip_tracking()` removes tracking parameters from top-level and frame navigations before they are sent
([request pipeline](request-pipeline.md#rewrite-redirects)). *Copy link without trackers* in the card menu uses the
same function.

## Look-alike addresses

The address pill warns about internationalised host names that mix Latin letters with look-alike characters from
other scripts (`suspicious_idn()` in [ui/titlebar.py](source:jbrowser/ui/titlebar.py)), and the site information
panel shows the connection's security (`security_state()`).

## Passwords on insecure pages

When a password is submitted on an `http://` page (not localhost), an info bar warns that it was sent unencrypted
(`passwords.warn_insecure`).

## Download protection

[services/downloads.py](source:jbrowser/services/downloads.py):

- **Dangerous file types** (`DANGEROUS_EXTENSIONS`: `.exe`, `.msi`, `.ps1`, `.bat`, `.js`, `.lnk`, `.iso` and about
  40 more) ask before they are kept, with a stronger warning when the download came over plain http
  (`downloads.protect`).
- **Mark-of-the-Web.** Every completed download gets a `Zone.Identifier` alternate data stream with `ZoneId=3`
  (internet), so Windows SmartScreen and Office Protected View check it. For normal spaces it also records
  `HostUrl` and `ReferrerUrl`; for incognito spaces only the zone.

## Certificate errors

A site with an invalid certificate shows an info bar: *Back to safety* (the default, also when dismissed) or
*Proceed anyway (unsafe)*. Errors Chromium marks as not overridable are rejected without asking.
