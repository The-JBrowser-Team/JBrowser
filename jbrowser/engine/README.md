# `jbrowser/engine/`: Qt WebEngine integration

Everything that talks to Chromium through Qt WebEngine. It turns `BrowserState` into live pages and turns page
events back into `Tab` updates.

| File | Purpose |
|---|---|
| `profiles.py` | `ProfileManager`: **one `QWebEngineProfile` per space** (separate cookies, storage, cache and permissions; off-the-record for incognito), plus reading mode's script-free, in-memory profile and the "Fix and sign in again" identity switch |
| `registry.py` | `EngineRegistry`: creates and destroys a `TabController` as cards come and go |
| `tab_controller.py` | `TabController`: owns one card's page and handles navigation, permissions, downloads, find, zoom, crashes and so on |
| `page.py` | The `QWebEnginePage` subclass and the isolated-world bridge used by password autofill |
| `signin.py` | `SigninIdentity`: presents Firefox while a page is on Google's sign-in servers, and reports when a sign-in has worked (`signedIn`) |
| `identity.py` | The browser JBrowser presents to sites: the newest Chrome, the engine's version, or Firefox |
| `reader.py` | Reading mode: article detection and extraction with Mozilla Readability (isolated world), and the reading-mode page with its strict CSP |
| `vendor/readability/` | Mozilla Readability 0.6.0 (`Readability.js`, `Readability-readerable.js`), Apache License 2.0, unmodified |
| `lifecycle.py` | Stops rendering out-of-sight cards and runs the memory saver, with its "never sleep" protections |
| `js.py` | JavaScript injected into pages, kept as Python strings so the build needs no data files: `privacy_js` (canvas noise, GPC / DNT signals; the only main-world script, with every patch reporting itself as native code), `cosmetic_js` (element hiding), the memory-saver guard, form detection and autofill (isolated world) |
