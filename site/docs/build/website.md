---
title: The website
only: main
description: How this website is built from the repository and published with GitHub Pages.
---

This website (home page, download page, changelog and these docs) is generated from the repository by
[tools/build_site.py](source:tools/build_site.py) and published with **GitHub Pages**.

## Building and previewing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-site.txt    # once: Markdown and Pygments
.\.venv\Scripts\python.exe tools\build_site.py --serve                 # build into _site\ and preview
```

`--serve` starts a local server at `http://localhost:8000/` after building (`--serve 8123` picks another port).
`--offline` skips the GitHub API, which the builder otherwise asks for release sizes and dates. `_site\` is ignored
by git.

## Screenshots

The home page uses real screenshots of the app, in `site/static/img/shots/`. Refresh them after a visible change:

```powershell
.\.venv\Scripts\python.exe tools\site_screenshots.py
```

[tools/site_screenshots.py](source:tools/site_screenshots.py) runs JBrowser from source with a throw-away profile,
downloads the filter lists if needed, opens a few real sites, puts a full-screen gradient behind a 1600 × 1000 window
and captures it from the screen<!-- if >= 2.0.3 -->. The same gradient is JBrowser's wallpaper for the run (`JBROWSER_WALLPAPER`), so the Frosted look is made from it and never from the PC's own wallpaper<!-- else -->, so Acrylic shows the gradient through the glass<!-- endif -->. It shoots the canvas, the Gallery,
the Lazy Toolbar, a split view, the site information panel, all ten colour tints (over a neutral backdrop), light
mode, an incognito space and the welcome, then writes WebP files at 1280 px, 1920 px and full size, plus
`og-image.jpg` for link previews. It takes about two and a half minutes; leave the mouse and keyboard alone while it
runs, because the window is kept in front of everything.

## Where things live

| Path | What |
|---|---|
| `site/templates/` | HTML templates: `home.html`, `changelog.html`, `download.html`, `docs.html`, `404.html` and shared parts (`_head.html`, `_topbar.html`, `_footer.html`) with `{{ value }}` placeholders and `{% include %}` |
| `site/static/` | CSS, JavaScript and images, copied as they are; `img/shots/` holds the screenshots |
| `site/docs/` | the documentation pages in Markdown, and `nav.json` (the navigation order) |
| `CHANGELOG.md` | the changelog page, one section per release |
| `.github/workflows/pages.yml` | builds and deploys the site |

## Documentation versions

Every release tag since 1.4.0 gets its own documentation (`docs/1.5.0/`, `docs/1.4.1/`, …), plus `docs/main/` for
the development branch and `docs/latest/` (the newest release again, for stable links). The version button switches
between them and stays on the same page when it exists in the other version.

- **Generated pages** (settings, commands, shortcuts, command line, data files and the Python API) are built from
  each version's own source code, read straight from its git tag with `git cat-file`. They are always exact.
- **Hand-written pages** are one set of Markdown files. Where versions differ, a page uses conditions:

  ```html
  <!--! if >= 1.5.0 -->
  The filter engine...
  <!--! elif == 1.4.1 -->
  ...
  <!--! else -->
  Domain blocking only...
  <!--! endif -->
  ```

  Conditions can also sit inside one line (`<!--! if >= 1.5.0 -->, the Gallery<!--! endif -->`), but must not wrap
  across lines; the builder warns if one is left over. Tests are `>=`, `<=`, `==`, `!=`, `>`, `<` against a version,
  `main`, `not main`, joined with `and`.
- **Front matter** can limit a whole page: `since: 1.5.0`, `until: 1.4.1`, or `only: main`.
- **Badges:** `[[!new 1.5.0]]`, `[[!changed 1.5.0]]`, `[[!removed 1.5.0]]`.
- **Showing this syntax literally**, as on this page: write `<!--!!`, `{{!!` or `[[!!`; one `!` is removed.

## Links in the docs

| Write | Becomes |
|---|---|
| `[text](../engine/profiles.md)` | a link to that page in the same version |
| `[text](source:jbrowser/app.py#L42)` | the file on GitHub at this version's tag (`main` for the development docs) |
| `[text](api:jbrowser.services.privacy.PrivacyService)` | the Python API page and anchor |
| `[text](repo:issues)` | a page of the GitHub repository |

`{{!version}}`, `{{!ref}}` and `{{!repo_url}}` are replaced as well. Admonitions use Python-Markdown's syntax
(`!!! note "Title"`, indented body).

## Writing a new page

1. Create `site/docs/<section>/<name>.md` with front matter (`title`, optionally `nav_title` and `description`).
2. Add it to `site/docs/nav.json`.
3. Link source files with `source:` and classes with `api:` rather than copying code that will change.
4. Build with `--serve` and check the page in both themes, and in an older version if it has conditions.

## Publishing

`.github/workflows/pages.yml` runs on every push to `main` that touches the site, the docs, `CHANGELOG.md` or the
code, and by hand. <!-- if >= 1.5.1 -->After publishing a release, `tools/release.ps1` starts it on `main` (`Update-Website` in `tools/common.ps1` runs `gh workflow run pages.yml --ref main`). There is no release trigger: a release event runs on its tag, and the `github-pages` environment only deploys from `main`.<!-- else -->It also runs for every published release.<!-- endif -->

It checks out the full history (for the tags), installs `requirements-site.txt`, runs `tools/build_site.py` and
deploys `_site/` with GitHub's Pages actions.

The download buttons are baked in at build time and refreshed in the browser from the GitHub API, so they point at a
new release even before the site is rebuilt. `download/` is a permanent link that always offers the newest version.

**How visitors install.** Every *Download* button opens the install window (`<dialog id="install-dialog">` in
`_footer.html`; `site.js` opens it). Its one big button downloads the installer; once clicked, the window shows three
steps to run it, including the SmartScreen "More info → Run anyway" note. The one-line PowerShell install is a
collapsed alternative, with the command always shown in full and a link to `install.ps1`; nothing is copied without a
click on *Copy*. The download page shows the same content (`_install_steps.html`, shared by both), with the steps
always visible. Links with `data-direct` download the file itself, and without JavaScript every button is a plain
download link.

## The domain and search engines

The site's address comes from the `SITE_URL` repository variable (`JBROWSER_SITE_URL` for `build_site.py`). Unset,
the site is built for `https://the-jbrowser-team.github.io/JBrowser/`; set to `https://jbrowser.app/`, the build uses
that address for canonical links, link previews, the sitemap and `robots.txt`, writes a `CNAME` file and roots the
404 page at `/`. Pages link to each other relatively, so a build works at either address.

What the build does for search engines:

| Piece | Why |
|---|---|
| `<link rel="canonical">`, `og:*` and `twitter:card` on every page | one address per page, and proper link previews |
| schema.org `SoftwareApplication` JSON-LD on the home page | tells Google and Bing that JBrowser is a free Windows browser, with its version and download page |
| `sitemap.xml` and `robots.txt` | the pages to index: home, download, changelog, policies and the latest docs |
| docs of the newest release point at `docs/latest/` (canonical); older versions and `main` are `noindex, follow` | searches land on the current documentation |
| `<key>.txt` and the `indexnow` job in `pages.yml` (`tools/indexnow.py`) | after each deploy on the custom domain, Bing, Yandex and others are told about every page (IndexNow) |
| `.well-known/security.txt` | where to report a vulnerability (RFC 9116) |

Moving to the domain, once its DNS points at GitHub Pages (four `A` records for `jbrowser.app`, `AAAA` records, and
`www` as a `CNAME` to `the-jbrowser-team.github.io`, all *DNS only* in Cloudflare):

```powershell
gh variable set SITE_URL --body "https://jbrowser.app/"
gh api -X PUT repos/The-JBrowser-Team/JBrowser/pages -f cname=jbrowser.app
gh workflow run pages.yml --ref main
# when GitHub has issued the certificate (a few minutes):
gh api -X PUT repos/The-JBrowser-Team/JBrowser/pages -F https_enforced=true
```

GitHub then redirects the old `github.io` address to the domain. Google needs the site added in Google Search
Console (a domain property verified with a DNS `TXT` record) and the sitemap submitted there; Bing Webmaster Tools can
import it from Search Console.
