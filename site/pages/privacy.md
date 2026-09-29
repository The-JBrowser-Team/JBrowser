---
title: Privacy policy
kicker: Project
lead: JBrowser collects nothing about you. Here is every connection it makes by itself, and how to turn each off.
description: What JBrowser sends over the network by itself, to whom, and how to switch it off.
---

JBrowser has no accounts, no analytics and no telemetry. The JBrowser team receives nothing about you or what you do
in JBrowser. Your history, bookmarks, passwords, cookies and settings stay on your computer, in your Windows user
folder; passwords are encrypted.

The websites you visit see what any browser shows them. Beyond that, JBrowser connects to these services by itself:

| What | Service | When | What it receives | Turn it off |
|---|---|---|---|---|
| Update check | GitHub (`api.github.com`, `github.com`) | Once a day, and when you click *Check now* | A request for the newest release, with JBrowser's version in the user agent | Settings → About JBrowser → *Check for updates automatically* |
| Ad and tracker lists | EasyList and EasyPrivacy (`easylist.to`), Peter Lowe's list (`pgl.yoyo.org`), NoCoin (`raw.githubusercontent.com`) | Once a week | A download request | Settings → Privacy and security → *Block trackers, ads, cryptominers and telemetry* |
| Phishing and malware lists | URLhaus (`urlhaus.abuse.ch`), Phishing Army (`phishing.army`) | Once a week | A download request. The addresses you visit are checked on your computer and never sent. | Settings → Privacy and security → *Phishing and malware protection* |
| Secure DNS | Quad9 (`dns.quad9.net`), or Cloudflare if you choose it | For every website you open | The names of the sites you visit (encrypted, instead of going to your internet provider) | Settings → Network and DNS → *DNS provider* → *Windows default* |
| Search suggestions | Google (`suggestqueries.google.com`) | While you type in the Lazy Toolbar | What you type. Never from incognito spaces. | Settings → Search → *Show search suggestions while I type* |
| Searches | The search engine you choose (Google by default) | When you search | Your search | Settings → Search |

By default JBrowser also asks websites not to track you (*Global Privacy Control* and *Do Not Track*), blocks
third-party cookies, and removes known tracking codes from links.

## Your data

Everything JBrowser stores is in `%APPDATA%\JBrowser` (and `%LOCALAPPDATA%\JBrowser\Cache` for caches).
*Settings → Clear browsing data* deletes it selectively, and *Settings → Reset* deletes all of it. Uninstalling asks
whether to delete it too.

## Changes

This policy changes only with JBrowser itself; each change is listed in the
[changelog](../changelog/index.html). Questions: [open an issue](https://github.com/The-JBrowser-Team/JBrowser/issues).
