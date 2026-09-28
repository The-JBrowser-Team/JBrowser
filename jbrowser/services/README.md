# `jbrowser/services/`: features without widgets

Each service owns one feature's data and logic, and exposes Qt signals for the UI. `jbrowser/context.py` creates them.
None of them imports `jbrowser.ui`.

| File | Purpose |
|---|---|
| `updater.py` | **Automatic updates** from GitHub Releases: check, download, SHA-256 check, install ([docs/AUTO_UPDATE.md](../../docs/AUTO_UPDATE.md)) |
| `session.py` | Saves and restores spaces, card layout and each card's back/forward history (including the 1.0 → 1.1 migration) |
| `history.py` | Browsing history in SQLite, tagged by space and ranked by frecency |
| `bookmarks.py` | Bookmarks and the bookmarks bar |
| `favourites.py` | Sidebar favourites: sites pinned above the spaces that work in every space |
| `archive.py` | The Archive: cards closed in the last 48 hours |
| `downloads.py` | Accepts downloads, tracks progress, adds Mark-of-the-Web, keeps the list |
| `vault.py` | The encrypted password vault (AES-256-GCM; key protected by DPAPI or a master password) |
| `privacy.py` | Tracker blocking, Global Privacy Control / Do Not Track, link cleaning, HTTPS-first, dev-host routing |
| `blocklist_data.py` | The built-in tracker and ad domain list |
| `threats.py` | Phishing and malware protection (local URLhaus / Phishing Army lists) |
| `network.py` | Secure DNS (DoH), proxies and the localhost developer toolkit |
| `search.py` | Search engines, keyword shortcuts (`yt`, `gh`, …) and live suggestions |
| `favicons.py` | The on-disk favicon cache (never used by incognito spaces) |
| `cookies.py` | Mirrors each space's cookies so they can be browsed and deleted |
| `permissions.py` | Plain-language names for web permissions |
| `userscripts.py` | User scripts (JS) and styles (CSS) by domain and space |
