# `assets/`: files bundled with the app

| File | Purpose | Made by |
|---|---|---|
| `jbrowser.ico` | Window, taskbar, exe and installer icon (16–256 px) | `tools/make_icon.py` (from the vector logo in `jbrowser/ui/icons.py`) |
| `jbrowser.png` | The logo at 256 px (README, About page) | `tools/make_icon.py` |
| [`sounds/`](sounds/README.md) | Welcome-screen sound effects | `tools/convert_sounds.py` |

The code finds these through `jbrowser.paths.resource_path("assets", …)`, which works from source and from the built
exe. When you add a file here, also add it to `datas` in [JBrowser.spec](../JBrowser.spec) (and to `--add-data` in
`tools/build_app.ps1` for `-OneFile` builds).
