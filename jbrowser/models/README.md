# `jbrowser/models/`: the browser state

Plain Qt objects that describe *what is open*: no widgets and no web engine. The UI and the engine both observe them.

| File | Purpose |
|---|---|
| `state.py` | `BrowserState`: **the single source of truth** for spaces, cards, focus and selection. Emits signals when any of them change. |
| `space.py` | `Space`: an isolated workspace (name, icon, colour, incognito, proxy) |
| `tab.py` | `Tab` (one card's title, URL, favicon, progress, audio and so on) and `TabUpdatePipeline`, which batches engine updates into one UI refresh per frame |
| `infobar.py` | `InfoBarSpec`: the data for an in-card bar (permission request, save password, crash, and so on) |
