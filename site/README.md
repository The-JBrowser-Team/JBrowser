# `site/`: the website

The JBrowser website, published with GitHub Pages at
**[the-jbrowser-team.github.io/JBrowser](https://the-jbrowser-team.github.io/JBrowser/)**: a home page with the
newest download, a permanent download link, the changelog, and the developer documentation for every release.

[`tools/build_site.py`](../tools/build_site.py) builds it; [`.github/workflows/pages.yml`](../.github/workflows/pages.yml)
publishes it on every push to `main` that touches it and on every release.

| Path | What's inside |
|---|---|
| `templates/` | The HTML pages (`home.html`, `download.html`, `changelog.html`, `docs.html`, `404.html`, `redirect.html`) and shared parts (`_head.html`, `_topbar.html`, `_footer.html`). `{{ value }}` placeholders, `{% include file %}`. |
| `static/css/` | `site.css` (shared), `home.css`, `docs.css`. `pygments.css` (code colours) is generated at build time. |
| `static/js/` | `site.js` (light/dark, copy buttons, the newest release from the GitHub API), `home.js` (the tint picker, animations), `docs.js` (version switcher, search, "On this page") |
| `static/img/` | `logo.svg` (the app's logo, as drawn by `paint_logo()` in `jbrowser/ui/icons.py`) and `shots/`, real screenshots of the app made by [`tools/site_screenshots.py`](../tools/site_screenshots.py) (WebP in three sizes, plus `og-image.jpg` for link previews) |
| `docs/` | The documentation pages in Markdown, and `nav.json`, the order of the navigation |

## Build and preview

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-site.txt    # once
.\.venv\Scripts\python.exe tools\build_site.py --serve                 # build, then http://localhost:8000/
```

The output goes to `_site\`, or to `%LOCALAPPDATA%\JBrowser-build\site` when the repository is inside OneDrive
(like the other build output). The build checks every internal link and anchor and prints any that are broken.

## Writing documentation

Every release tag since 1.4.0 gets its own copy of the docs. Generated pages (settings, commands, shortcuts, command
line, data files and the Python API) come from each tag's own code. Hand-written pages are shared, and mark what
differs between versions:

```html
<!-- if >= 1.5.0 -->
Text for 1.5.0 and later.
<!-- else -->
Text for older versions.
<!-- endif -->
```

Front matter can limit a page (`since: 1.5.0`, `until: 1.4.1`, `only: main`). Link other pages with relative `.md`
links, source files with `source:path`, and classes with `api:jbrowser.module.Class`. The full guide is the
[website page](https://the-jbrowser-team.github.io/JBrowser/docs/main/build/website.html) (`docs/build/website.md`).
