# `jbrowser/engine/`: Qt WebEngine integration

Everything that talks to Chromium through Qt WebEngine. It turns `BrowserState` into live pages and turns page
events back into `Tab` updates.

| File | Purpose |
|---|---|
| `profiles.py` | `ProfileManager`: **one `QWebEngineProfile` per space** (separate cookies, storage, cache and permissions; off-the-record for incognito) |
| `registry.py` | `EngineRegistry`: creates and destroys a `TabController` as cards come and go |
| `tab_controller.py` | `TabController`: owns one card's page and handles navigation, permissions, downloads, find, zoom, crashes and so on |
| `page.py` | The `QWebEnginePage` subclass and the isolated-world bridge used by password autofill |
| `lifecycle.py` | Stops rendering out-of-sight cards and runs the memory saver, with its "never sleep" protections |
| `js.py` | JavaScript injected into pages, kept as Python strings so the build needs no data files: `privacy_js` (canvas noise, GPC / DNT signals; the only main-world script, with every patch reporting itself as native code), `cosmetic_js` (element hiding), the memory-saver guard, form detection and autofill (isolated world) |
