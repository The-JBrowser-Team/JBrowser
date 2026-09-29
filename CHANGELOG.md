# Changelog

All notable changes to JBrowser. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/) (`major.minor.patch`).

Each release section below becomes the release notes on GitHub (see [docs/RELEASING.md](docs/RELEASING.md)).

## [Unreleased]

### Added
- **A website** at [the-jbrowser-team.github.io/JBrowser](https://the-jbrowser-team.github.io/JBrowser/): a home page
  with a direct download of the newest installer, a permanent download link, this changelog, and developer
  documentation for every release (architecture, web engine, privacy, UI, building and releasing, and references
  generated from each version's code), with a version switcher and search. It is built by `tools/build_site.py`
  and published by GitHub Actions on every push and release.
- The home page shows real, high-resolution screenshots of JBrowser, with a feature tour to click through, a colour
  picker that shows each tint on the real window, and screenshots that follow the site's light or dark mode.
  `tools/site_screenshots.py` retakes them all in one command.

## [1.5.0] - 2026-09-29

### Added
- **Gallery.** The new *Gallery* button on the ribbon (or Ctrl+Shift+G) spreads every card in the space out as a
  grid of live thumbnails that pop in one after another. Click a card to jump to it, type to filter by title or
  address, use the arrow keys and Enter, close cards with ×, drag them to reorder, and add a card from the
  *New card* tile. The **This space / All spaces** switch shows the cards of every space at once, grouped under each
  space's name and colour; drag a card into another group to move it to that space. It works with the keyboard
  and screen readers.
- **Colour tints.** Settings → Appearance → *Colour tint* has 10 colours (rose, coral, amber, lime, mint, teal, sky,
  indigo, violet and slate) and *No colour*. With Acrylic or Mica the colour is a light wash over the window; with
  *Solid* the window takes on the colour fully. Incognito spaces always stay black. You can also pick a colour in
  the welcome setup.
- **Drag cards anywhere.** Hold a card's ribbon and drag it along the canvas to reorder it, or drop it onto a space
  in the sidebar to move it there. Hold **Alt** and drag anywhere on a card to do the same. Cards in the sidebar
  list can be dragged too: a line shows where the card will land, and dropping it on a space moves it.
- The welcome setup has a new page about the Gallery, a colour picker on the *Look* page, and a Gallery step in the
  tour. It shows once more after updating so you can try them.
- The sidebar menu has *Gallery of all spaces*, and the main menu and command palette have *Gallery*. The command
  palette can also switch the colour tint (type "colour") and the *New card* button.

### Changed
- **Tracker and ad blocking works properly now.** JBrowser reads the full Adblock Plus rules in EasyList and
  EasyPrivacy (address patterns, exceptions and per-site rules), not only whole domains, and hides the empty ad
  boxes that are left behind. A site on your allowed list is left completely alone. Settings shows how many rules
  are active. The rules download in the background the first time JBrowser starts after updating.
- **Fewer "unusual traffic" and "Checking your browser" pages.** JBrowser now looks like the Chrome it is built on:
  it sends the same language header, no longer changes the reported processor, memory or graphics card, and
  leaves Google, Cloudflare, Microsoft, Apple, PayPal and CAPTCHA pages untouched. Fingerprinting protection now
  only scrambles canvas images, where it helps most.
- The clock sits in the middle of the sidebar header.
- The *New card* button is always at the bottom of the sidebar list, even in an empty space. Turn it off with
  Settings → Appearance → *Always show the "New card" button*.
- The memory saver still keeps chats, calls and screen shares awake, but now finds them without adding anything
  to the page itself.
- Settings describes tracker blocking and fingerprinting protection more accurately.
- Packages updated to their latest versions; `requirements.lock.txt` lists the exact versions of this release.
  No known vulnerabilities in any of them (checked against the OSV database).

### Fixed
- A card that scrolled out of view or went to sleep before its page had drawn showed a blank white picture. It now
  shows the page's title until a real picture is taken.

## [1.4.1] - 2026-09-29

### Fixed
- **Setup no longer stops with "JBrowser is currently running".** If JBrowser is open, Setup now offers to close it
  for you: JBrowser saves your cards and spaces, closes, and the last page offers to start it again. You can install
  this version straight over an open JBrowser 1.4.0.
- Setup no longer asks whether to install "for me" or "for all users". It installs for your account, as before.
- When Windows or an installer asks JBrowser to close (for example when you sign out), it now saves everything and
  shuts down in order, instead of quitting without saving the latest changes.
- Saving settings, the session and other data no longer fails with "Access is denied" when an antivirus scan or
  the search indexer briefly holds the file. Before, that save was lost and "Something went wrong" appeared.
- Update window: after closing it during a download, *Install* no longer downloads the update a second time, and
  *Check for updates* during a download now shows its progress instead of leaving a stray message for later.

### Changed
- **30 MB smaller download** (108 MB instead of 138 MB, and 344 MB instead of 523 MB installed). Parts of Qt that
  JBrowser never uses, non-English translations and a debug copy of the DevTools files are no longer included.
- The build scripts start from empty output folders, so files from an earlier build can never end up in an installer.
- GitHub: private vulnerability reporting is switched on (the *Report a vulnerability* link in SECURITY.md works now),
  a code of conduct was added, and the page links to the latest release.

## [1.4.0] - 2026-09-28

### Added
- **Automatic updates.** JBrowser checks GitHub Releases once a day. When a new version is out, an **Update**
  button appears on the ribbon; one click shows what's new, downloads the installer, verifies its SHA-256
  fingerprint and restarts JBrowser on the new version. Settings → About has *Check now* and an on/off switch, and
  the Lazy Toolbar has *Check for updates*.
- **A proper Windows installer** (`JBrowser-Setup-<version>.exe`, built with Inno Setup): installs for the current
  user without an administrator prompt, adds a Start menu entry and an optional desktop icon, can register
  JBrowser as a Windows web browser (so it can be chosen as the default), and uninstalls from *Apps & features*.
- JBrowser now lives on GitHub (`The-JBrowser-Team/JBrowser`) under the **GNU GPL v3** licence, with a README
  for every folder, guides in `docs/`, issue templates and a lint check on every push.
- `tools/update_deps.py`: creates or refreshes the virtual environment, updates every package the app and build
  need, then imports every module to prove they work (`--check`, `--lock`).
- `tools/version.py`, `tools/build_app.ps1`, `tools/build_installer.ps1` and `tools/release.ps1` for a one-command
  build and release.
- `master.ps1` runs the whole process: packages, build, installer, a dated zip in `distribution\`, and (with
  `-Publish`) the GitHub release.
- One-command install and update from PowerShell: `irm https://raw.githubusercontent.com/The-JBrowser-Team/JBrowser/main/install.ps1 | iex`.

### Changed
- The welcome intro is livelier: three brand-coloured orbs swirl in on comet trails, pulse on the sound's first
  hit and merge into a bloom of sparkles; the logo springs out of it with a little twist and then floats; the
  *JBrowser* letters hop in one by one under a travelling colour wave.
- The welcome screen uses a softer mouse-click sound at half the volume, and no longer clicks on the first slide
  straight after the intro. (These changes were made after 1.2.0; there was no separate 1.3.0 release.)
- `build.ps1` moved to `tools/build_app.ps1`.

### Fixed
- After a restart, a removed HTTPS proxy could stay in use until JBrowser was closed and opened again.

## [1.2.0] - 2026-09-28

### Added
- **A first-run welcome**: an animated intro timed to its sound, three story slides, setup pages for look, search,
  protection, spaces and finishing touches, then a guided tour with a gliding spotlight. Replay it from
  Settings → About or the Lazy Toolbar ("Replay the welcome tour").
- **Pull to add a card**: keep scrolling past the first or last card and a "+" grows in the gap; when its ring
  fills, a new card opens there. Alt+← on the first card (or Alt+→ on the last) twice does the same.
- **Favourites and pinned cards**: sites pinned above the spaces (Arc-style tiles that work in every space; drag to
  reorder), and pinned cards that stay at the start of their space with no close button.
- **The Archive** (Ctrl+Shift+Y): cards closed in the last 48 hours, searchable and one click from coming back
  with their history. Clearing browsing history clears it too.
- An optional **Home button** on the ribbon that opens the Lazy Toolbar or a page you choose.

### Changed
- The sidebar's hide button hides it completely; point at the left edge of the window to peek at it, or press
  Ctrl+B. Right-clicking the ribbon or sidebar offers show and hide options.
- The address bar is narrower and centred; the new-card button moved to a "New card" row under the last card;
  the "Cards in" label is gone.
- The old "favorites bar" is now the **bookmarks bar**.

## [1.1.0] - 2026-09-28

### Added
- New security features: phishing and malware protection with a warning page, fingerprinting protection, removal
  of tracking codes from links, an HTTPS-first mode that falls back safely, download protection with Windows
  Mark-of-the-Web tagging, warnings for insecure password forms and look-alike (IDN) addresses, a site information
  panel, "Forget this site", "Copy link without trackers" and a password health check (weak / reused).
- Settings pages **Clear browsing data** (by time range and space, plus clear on exit) and **Reset** (default
  settings or a full factory reset).

### Changed
- Settings rebuilt as a translucent window with plain-language explanations under every option.
- Acrylic by default, Segoe UI, far less bold text, a 12-hour clock beside the logo (the logo opens Settings),
  Chrome-style grouped ribbon buttons, a subtle grey focus ring on spaces, and a Lazy Toolbar that stays empty
  until you type.
- History, Bookmarks, Downloads, Passwords, Cookies, Permissions, User scripts and the developer toolkit open as
  translucent windows.
- Default spaces are Home, Work and Other; 1.0 profiles are upgraded automatically.

## [1.0.0] - 2026-09-28

### Added
- First release: the infinite horizontal card canvas, isolated Spaces with per-space profiles and incognito
  spaces, the Lazy Toolbar command palette, memory saver and render throttling, secure DNS (Quad9 / Cloudflare),
  per-space proxies, tracker blocking, an encrypted password manager, downloads, history, bookmarks, DevTools and
  user scripts, on a Windows 11 Mica / Acrylic window. See [docs/FEATURES.md](docs/FEATURES.md).

[1.4.1]: https://github.com/The-JBrowser-Team/JBrowser/releases/tag/v1.4.1
[1.4.0]: https://github.com/The-JBrowser-Team/JBrowser/releases/tag/v1.4.0
[1.2.0]: https://github.com/The-JBrowser-Team/JBrowser/blob/main/CHANGELOG.md#120---2026-09-28
[1.1.0]: https://github.com/The-JBrowser-Team/JBrowser/blob/main/CHANGELOG.md#110---2026-09-28
[1.0.0]: https://github.com/The-JBrowser-Team/JBrowser/blob/main/CHANGELOG.md#100---2026-09-28
