---
title: "Networking: DNS, proxies and developer hosts"
nav_title: Networking
description: Secure DNS through a ctypes call into Qt, live proxy switching per space, and localhost developer mapping.
---

Everything network-related that isn't blocking lives in [services/network.py](source:jbrowser/services/network.py).

## Secure DNS

[`DnsManager`](api:jbrowser.services.network.DnsManager) switches Chromium's resolver between the Windows resolver and
DNS-over-HTTPS, at runtime and for the whole process:

| `network.dns_mode` | Resolver |
|---|---|
| `system` | whatever Windows uses |
| `quad9` (default) | `https://dns.quad9.net/dns-query`, which also refuses known malicious domains |
| `cloudflare` | `https://cloudflare-dns.com/dns-query` |

With `network.dns_fallback` on, a failing DoH server falls back to the system resolver (`SecureWithFallback`);
otherwise DNS-over-HTTPS is strict (`SecureOnly`).

!!! note "Why ctypes"
    PyQt6 exposes `QWebEngineGlobalSettings.DnsMode` but not the static `setDnsMode()`. `DnsManager` loads
    `Qt6WebEngineCore.dll` and calls the exported C++ function by its mangled name. `DnsMode` is passed by value, which
    on MSVC x64 means a pointer to a temporary the callee destroys, so the `QStringList` inside is reference-counted up
    once beforehand to balance that destructor. If a future Qt build changes the export, `available` is `False` and
    the DNS setting reports that it can't be applied instead of crashing.

The mode is applied at start-up before the first profile touches the network, and again whenever the setting changes.

## Proxies

[`ProxyManager`](api:jbrowser.services.network.ProxyManager) handles a global proxy (`network.proxy`) and optional
per-space overrides (`Space.proxy`, edited with *Proxy for current space…*).

| Type | How it is applied |
|---|---|
| HTTP (CONNECT), SOCKS5 | `QNetworkProxy.setApplicationProxy()`, live |
| System proxy | `QNetworkProxyFactory.setUseSystemConfiguration(True)`, live |
| HTTPS (TLS to the proxy) | Chromium's `--proxy-server` flag, at start-up only (a restart is needed) |

Chromium has one network stack per process, so a per-space proxy is really "the proxy of the space in front":
`AppContext` calls `proxy.apply(space.proxy)` on every space switch. To make Chromium re-read the configuration
immediately, `_kick()` loads a dummy address (`http://proxy-refresh.jbrowser.invalid/`) in a hidden page for each
profile; the request fails harmlessly but resets the network context.

Credentials are stored in `settings.json` protected with **DPAPI** (`protect_secret()` / `reveal_secret()`), which
ties them to the Windows user account. `requests_proxies()` gives JBrowser's own downloads (filter lists, threat
lists) the same route as the pages. Proxy authentication prompts are answered from the stored credentials first.

## Localhost developer hosts

`network.dev_hosts` maps friendly names to local servers, for example `app.test → 127.0.0.1:3000`.
`PrivacyService.rewrite()` redirects matching requests to the target (see [the request pipeline](../privacy/request-pipeline.md)),
`looks_like_url()` treats those names as addresses in the Lazy Toolbar, and the dev-host dialog manages the list.

`DEV_PORTS` lists common development ports (3000 React/Next.js, 5173 Vite, 8000 Django/FastAPI, 8080, 4200 Angular,
5000 Flask, 8888 Jupyter). Each has a Lazy Toolbar command that opens `localhost:<port>`, and
[`PortProbe`](api:jbrowser.services.network.PortProbe) checks asynchronously, with a `QTcpSocket` and a 600 ms
timeout, whether something is listening, so the UI can show which servers are running.
