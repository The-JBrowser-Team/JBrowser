# JBrowser features

Everything JBrowser can do, grouped by area. New in a release? See [CHANGELOG.md](../CHANGELOG.md).

### Windows 11 look & feel
- **Acrylic** by default, or **Mica, Mica Alt** or **Solid** (Settings → Appearance); dark/light/system theme and the Windows accent colour.
- **Colour tints**: rose, coral, amber, lime, mint, teal, sky, indigo, violet, slate or *No colour* (Settings →
  Appearance, the welcome setup, or "colour" in the Lazy Toolbar). Over Acrylic or Mica it is a light wash; with
  *Solid* the surfaces take on the colour. Incognito spaces are always black.
- Segoe UI throughout, with restrained weights; a 12-hour clock centred in the sidebar header, and the logo doubles
  as the Settings button.
- Custom title bar that keeps native behaviour: drag, double-click maximise, Aero Snap, **Snap Layouts flyout** on the maximise button, rounded corners, shadow, resize edges.
  Buttons are grouped like Chrome: navigation · address pill · tools · window controls.
- Alpha-layered surfaces over the backdrop; natively rounded menus and tooltips; Segoe Fluent Icons throughout.
- **Fluid Animations** (Settings → Appearance, on by default): turn it off and every transition becomes instant.
  On first run it follows the Windows "Animation effects" accessibility setting.

### Spatial canvas
- Cards laid out left→right on a continuous canvas with a live **overview strip** (minimap).
- **Pull to add**: keep scrolling past the first or last card and a "+" grows in the gap; when its ring fills, a new
  card opens at that end. Alt+← on the first card (or Alt+→ on the last) twice does the same from the keyboard.
- Pan with trackpad swipes, horizontal wheel, **Alt + mouse wheel** anywhere, or by dragging the overview strip.
- **Alt + ← / →** steps focus between cards (smoothly scrolled into view); Ctrl+Tab cycles and wraps around.
- **Pinned cards** stay at the start of their space (right-click → Pin card).
- **Alt + 0** = 100 % width, **Alt + 1 … 9** = 10 % … 90 % of the canvas, applied to **all selected cards**.
- Multi-select with **Ctrl + Click / Shift + Click** on card headers (or in the sidebar list), **Ctrl + Shift + A** selects all.
- Split presets: **50 / 50** (Alt+Shift+D), **33 / 33 / 33** (Alt+Shift+T), **25 % × 4** (Alt+Shift+Q), focus 80 %.
- **Drag a card by its ribbon** to reorder it (the card lifts and the others make room), or drop it onto a space in
  the sidebar to move it there. **Alt + drag** anywhere on a card does the same. Double-click a ribbon to toggle full
  width, middle-click to close.
- Cards in the sidebar list can be dragged too: a line shows where the card lands, and dropping it on a space moves it.

### Gallery (Ctrl+Shift+G, or the Gallery button on the ribbon)
- Every card of the space as a grid of live thumbnails that pop in one after another; the current card is marked.
- **This space / All spaces** switch: all spaces at once, grouped under each space's name, icon and colour.
- Type to filter by title or address; arrow keys, Home/End and Enter to open; Delete or × to close a card; Esc to
  go back. Drag tiles to reorder, or into another space's group to move them. *New card* tiles add a card.
- Built for the keyboard and screen readers (every tile has an accessible name and description), and it follows
  *Fluid Animations*.

### Spaces & isolation
- **Home / Work / Other** by default; create, rename, recolour, re-icon, reorder and delete spaces.
- Every space has its **own Qt WebEngine profile**: cookies, localStorage, IndexedDB, service workers, cache and
  permissions are stored in a separate directory, so a login in *Work* never leaks into *Home*.
- **Incognito spaces** (Ctrl+Shift+N) use off-the-record profiles: nothing touches the disk and everything is gone when the space closes.
- Switch spaces from the sidebar (click, or **↑ / ↓** when the space list has focus, Ctrl+Shift+E), with **Alt + ↑ / ↓**
  from anywhere, or from the space chip in the address pill. Spaces slide vertically when switching.
- **Favourites** sit above the spaces as icon tiles and work in every space: clicking one focuses its card in the
  current space or opens it. Add or remove them from the card menu or the Lazy Toolbar.
- The sidebar can be **hidden completely** (Ctrl+B, its hide button, or right-click → Hide sidebar); point at the left
  edge of the window to peek at it.
- The **New card** button sits at the end of the sidebar's card list, even in an empty space (Settings → Appearance →
  *Always show the "New card" button*).

### Performance & tab lifecycle
- **Coalescing update pipeline**: engine events (title, favicon, progress, audio…) are written to state models and
  flushed once per frame; off-screen cards only mark themselves stale and repaint when they become visible.
- **Out-of-sight render throttle** (default on): exactly 5 s after a card leaves the viewport, or its space is hidden,
  its page stops producing frames and, when safe, is frozen (JS timers paused). Full speed returns the moment it re-enters view.
- **Memory saver** (Off / after 30 min / **after 20 min** / after 10 min): inactive background cards are
  hibernated (renderer discarded) and replaced by a faded snapshot with a moon badge on the card and in the sidebar.
- **Smart protection guard**: cards playing audio/video, with unsaved form input, open WebSockets or WebRTC calls,
  `beforeunload` handlers, active downloads or DevTools open are never put to sleep. A per-site never-sleep list is available.
- Restored sessions load lazily: only the cards you can actually see are loaded at start-up.

### The Lazy Toolbar (Ctrl+T / Ctrl+K / Ctrl+L)
- Replaces blank new-tab pages. It opens empty with the cursor ready; results appear as you type a URL, a search or a
  **keyword search** (`yt lofi`, `gh qt`, `w python`, …).
- Live **Google search suggestions** (toggleable; never sent from incognito spaces).
- **Fuzzy search** across open cards in every space, bookmarks, history (frecency-ranked), saved passwords and 100+ commands.
- Scope prefixes: `>` commands · `@` cards · `*` bookmarks · `#` history · `$` passwords.
- Run actions directly: switch DNS resolver, toggle proxy, toggle animations, card-size presets, clear cache,
  open localhost:3000/5173/8000/8080, change theme/material, memory-saver presets, and more.
- Enter opens in the mode's target, **Shift+Enter** in the other one (new card ↔ this card), Tab completes.

### Security, networking & developer tools
- **DNS resolver** with live switching: *OS default*, **Quad9 malware-blocking DoH (recommended, default)**, *Cloudflare 1.1.1.1 DoH*,
  with optional fallback to the system resolver.
- **Proxies**: global or **per-space** HTTP (CONNECT) and SOCKS5 proxies applied instantly; HTTPS (TLS-to-proxy)
  proxies applied at start-up; system proxy; credentials protected with DPAPI; connection test.
- **Localhost developer toolkit**: map hosts such as `app.test → 127.0.0.1:3000` (requests are transparently routed),
  one-click launchers for common dev ports with live "something is listening" indicators.
- **Tracker and ad blocking** with a built-in **Adblock Plus filter engine**: the full EasyList and EasyPrivacy rules
  (address patterns, `@@` exceptions, `$third-party`, `$domain=`, resource types, `$important`) plus the Peter Lowe and
  NoCoin domain lists. **Element hiding** (`##` rules) removes the empty ad boxes left behind, before the page first
  paints. Per-card blocked counter, per-site protection toggle (an allowed site is left completely alone),
  third-party-cookie blocking (CAPTCHA providers excepted), **Global Privacy Control** and **Do Not Track** headers +
  JS signals, pop-up blocking, WebRTC IP-leak protection. The lists refresh weekly in the background.
- **Phishing and malware protection**: pages on the URLhaus and Phishing Army lists are stopped before they load and
  replaced by a warning page ("Go back to safety" / "Continue anyway"). Lists are stored locally and refreshed weekly;
  the addresses you visit are never sent anywhere.
- **Fingerprinting protection**: per-site, per-session noise in canvas read-backs, so sites cannot build a stable
  canvas fingerprint. Everything else reports what Chrome reports: JBrowser sends Chrome's headers (including a real
  `Accept-Language`), changes no hardware values, and leaves sign-in and security-check sites (Google, Cloudflare,
  Microsoft, Apple, PayPal, CAPTCHA providers) untouched, so it doesn't look like a bot.
- **Up to date, as far as sites can tell**: JBrowser presents the newest stable Chrome version (Chrome 155 in
  JBrowser 1.5.2) in its user agent and client hints, instead of its engine's Chromium 140, so sites don't treat it
  as outdated. Every release records the then-current version, and between releases it keeps up by date.
- **Google sign-in works**: Google's sign-in server gets a Firefox user agent, as in other Qt WebEngine browsers,
  because Google refuses embedded browser engines ("This browser or app may not be secure"), and sign-in pages
  (Google, Microsoft, Apple) are exempt from ad and tracker blocking, which their security checks need.
- **Local files stay private**: a web page saved on your computer can show its own images but can't read your other
  files, as in Chrome.
- **Tracking codes removed from links** (`utm_*`, `fbclid`, `gclid`, `mc_eid`, …) before the page opens, plus
  "Copy link without trackers" for sharing.
- **HTTPS-first (optional)**: http links try the encrypted version first; if it fails, the page opens over http with
  a clear "not encrypted" warning.
- **Download protection**: programs and scripts (`.exe`, `.msi`, `.ps1`, `.bat`, …) ask before they are kept (louder
  over insecure connections), and every download is tagged with the Windows **Mark-of-the-Web** so SmartScreen and
  Office Protected View can check it.
- **Site information panel** (click the lock or warning in the address pill): connection security, look-alike address
  warnings, trackers blocked, per-site protection, cookies, permissions, zoom, "Clear site data" and **Forget this site**
  (history, cookies, permissions, zoom and storage for that site, in every space).
- Warnings when a password is typed into an insecure (http) page, and for internationalised addresses that imitate
  other sites.

### Built-in utilities
- **History** vault: search, filter by space and date range, delete entries, 1-click clear.
- **Archive** (Ctrl+Shift+Y, bottom-right of the sidebar): cards closed in the last 48 hours with their back/forward
  history; reopen with a click, Ctrl+Shift+T for the latest. Stored locally, never for incognito spaces, and cleared
  together with browsing history.
- **Password manager**: AES-256-GCM encrypted vault, key protected by Windows DPAPI or an optional master password (Scrypt).
  Offers to save/update logins, autofills (isolated script world, so pages can't read it), per-space or global logins,
  password generator, CSV import (Chrome/Edge/Firefox), **encrypted export** (a CSV inside a ZIP locked with a
  password you choose, AES-256; 7-Zip, WinRAR and JBrowser itself open it), never-save list, clipboard auto-clear and
  a local **password health check** that flags weak and reused passwords.
- **Downloads** manager with progress, speed/ETA, pause/resume/cancel, open file / show in folder.
- **DevTools** docked inside the card (F12 / Ctrl+Shift+I), **find in page** (Ctrl+F), **zoom** remembered per site
  (Ctrl+= / Ctrl+- / Ctrl+0), print, save page (HTML/MHTML), save as PDF, view source, card screenshots.
- **Cookies** and **site permissions** (camera, mic, location, notifications, clipboard, screen share…) managers, per space.
- **Settings** (Ctrl+, or click the logo): General, Appearance, Search, Privacy and security, Clear browsing data,
  Passwords, Performance, Network and DNS, Downloads, Advanced, Reset and About, with a search box that filters options.
  Clear browsing data works by time range (last hour to all time) and space, and can run automatically on exit.
  Reset offers "restore default settings" or a full factory reset.
- **Bookmarks bar** (Ctrl+Shift+B), bookmarks manager with Netscape HTML import/export.
- **User scripts & styles**: inject JS or CSS by domain pattern and per space.
- **Hotkey cheat sheet** (Ctrl+/ or F1), generated from the command registry.
- Session restore with full back/forward history, reopen closed cards (Ctrl+Shift+T), permission prompts,
  certificate-error interstitials, HTTP/proxy authentication, screen-share picker, web notifications (in-app + Windows),
  OAuth/payment popups that keep `window.opener`, HTML5 immersive fullscreen, single-instance URL forwarding.

## Keyboard shortcuts

Highlights only: press **Ctrl+/** (or F1) in JBrowser for the full, always-current list.

|||||
| New card (Lazy Toolbar) | Ctrl+T | Lazy Toolbar | Ctrl+K |
| Edit address | Ctrl+L, F6, Alt+D | Close card | Ctrl+W |
| Reopen closed card | Ctrl+Shift+T | Duplicate card | Ctrl+Shift+K |
| Previous / next card | Alt+← / Alt+→, Ctrl+Shift+Tab / Ctrl+Tab | Move card | Alt+Shift+← / → |
| Scale selected cards | Alt+1 … Alt+9 (10–90 %), Alt+0 (100 %) | Select all cards | Ctrl+Shift+A |
| Split 50/50 · 33×3 · 25×4 | Alt+Shift+D · T · Q | Pan canvas | Alt+Wheel |
| Previous / next space | Alt+↑ / Alt+↓ | New space / incognito | Ctrl+N / Ctrl+Shift+N |
| Back / forward | Ctrl+[ / Ctrl+], mouse side buttons | Reload / hard reload | F5 / Ctrl+F5 |
| Find in page | Ctrl+F | Zoom | Ctrl+= / Ctrl+- / Ctrl+0 |
| Developer tools | F12, Ctrl+Shift+I | Bookmark page | Ctrl+D |
| Toggle sidebar | Ctrl+B | Bookmarks bar | Ctrl+Shift+B |
| History / Downloads | Ctrl+H / Ctrl+J | Settings | Ctrl+, |
| Clear browsing data | Ctrl+Shift+Del | Full screen | F11 |
| Keyboard shortcuts | Ctrl+/, F1 | Quit | Ctrl+Shift+Q |
| Archive | Ctrl+Shift+Y | Home | Alt+Home |
| Gallery | Ctrl+Shift+G | Move a card | Alt + drag anywhere on it |
| Add a card at an end | Alt+← on the first card / Alt+→ on the last, twice | Next / previous card (wraps) | Ctrl+Tab / Ctrl+Shift+Tab |
