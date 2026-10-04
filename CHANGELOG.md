# Changelog

All notable changes to JBrowser. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/) (`major.minor.patch`).

Each release section below becomes the release notes on GitHub (see [docs/RELEASING.md](docs/RELEASING.md)).

## [2.0.1] - 2026-10-04

Cards get a width button, JBrowser can open your PDF files, and Settings is easier to find your way around.

### Added
- **Card width button on the ribbon.** It shows the selected card's width. Click it for **20%**, **40%**, **50%**,
  **60%**, **80%** or **full width**, each listed with its shortcut (**Alt+2**, **Alt+4**, **Alt+5**, **Alt+6**,
  **Alt+8**, **Alt+0**). With several cards selected, it sizes them all. It's on by default; right-click the ribbon
  to hide it.
- **JBrowser for PDF files.** The installer now also registers JBrowser as a PDF viewer, so you can choose it for
  `.pdf` files in Windows' Default apps or under **Open with**. PDFs open in the built-in viewer, where you can zoom,
  search, print and save them.
- **Settings › Default apps.** Shows whether JBrowser opens your links and your PDF files, and takes you straight to
  the right place in Windows' settings to change it.

### Changed
- **Settings, reorganised.** Pages are grouped into *Browsing*, *Look and feel*, *Privacy and safety* and *System*,
  and the longer pages have headings. Every ribbon and sidebar option now lives on one new page, **Ribbon and
  sidebar**. Searching settings hides empty headings, and **Esc** clears the search before it closes Settings.
- **The reading mode button is off the ribbon by default.** It's still on every card's title bar whenever a page
  looks like an article, and **F9** works as always. Turn the ribbon button back on in Settings › Ribbon and sidebar,
  or by right-clicking the ribbon.
- **A smaller app.** Debug-only copies of web-engine files and Qt plugins JBrowser never uses are no longer installed.
- The welcome tour shows the card width button.

### Fixed
- **Local links open again.** Typing or pasting a file or folder location into the address bar searched the web
  instead of opening it: `C:\Users\…\page.html`, paths with spaces or `#`, quoted paths from *Copy as path*,
  `D:/…`, `%USERPROFILE%\…`, network locations like `\\server\share` and `file:///` addresses with backslashes. They
  open in a card now, and are never sent for search suggestions. A computer on your network with a port
  (`nas:5000`) opens too.
- **Files from Windows open as files.** Opening a saved page or a PDF with JBrowser (Open with, double-click, the
  command line) searched the web for its location instead of opening it, also when JBrowser was already running.
  Relative paths on the command line work too.
- Steadier window colours on more PCs.

## [2.0.0] - 2026-10-02

JBrowser 2.0 is the biggest update yet: cards can now stack in columns, articles open in a calm reading mode, and
downloads are watched over more carefully, all in a cleaner ribbon.

### Added
- **Stack cards in columns.** Put up to three cards on top of each other in one column. Drag a card onto the lower
  part of another (or its top edge to go above), or press the new **stack** button on the ribbon (**Alt+Shift+S**).
  The button opens a space right below the current card where you choose what goes there: a new page, a card that is
  already open, a favourite or a bookmark. Cards in a column always share one width, so changing one changes them
  all, and the picker sets the column's width in one click. Drag a card out, or press **Alt+Shift+U**, to take it out
  of its column. Columns are saved with your session. The stack button replaces the old layout button: right-click it
  (or use the button in the picker) for split views and card widths.
- **Reading mode.** Shows an article's text and pictures without ads, menus or clutter, in a clear layout with a
  choice of serif or sans-serif text, four colour themes (matching JBrowser, light, sepia, dark) and adjustable text
  size. Turn it on with the reading button on the ribbon or on a card, or press **F9**. It's off until you ask for it;
  when JBrowser sees you reading an article it suggests it once, with **Don't show again** if you'd rather it didn't.
  Articles are shown in a separate page where no script from the website runs, and trackers stay blocked. (Powered by
  Mozilla's Readability, the engine behind Firefox Reader View.)
- **Download protection levels** (Settings › Downloads). JBrowser now warns about programs and scripts, files from
  sites on its dangerous-sites list, and files from sites without a secure connection (no HTTPS).
  - **Standard** (the default) warns you and lets you **Keep** the file or **Delete** it. Until you decide, the file is
    saved so it can't be opened by accident.
  - **Strict** blocks those downloads entirely.
  - **Off** turns the warnings off.
- **Download progress at a glance.** While files download, the Downloads button shows the percentage over a progress
  bar.

### Changed
- **A cleaner ribbon.** The privacy shield moved into the right side of the address bar, next to the star. The
  Downloads button only appears once you download something (Settings › Appearance can show it all the time).
- **Click anywhere on a finished download** in the Downloads window to open it, not just the small button.
- **Favourites reopen as wide as you left them.** Closing a card opened from a favourite remembers its width; reopening
  the favourite opens it at that width again. (Cards brought back from the Archive keep their width too.)
- **Google sign-in fixes itself.** When Google says it couldn't sign you in, press **Fix and sign in again**. JBrowser
  then presents itself as Firefox until you've signed in, and goes back to its usual settings by itself afterwards.
- **Easier to read.** Settings, messages and the welcome tour were rewritten in plainer, shorter language. Advanced
  options keep their names and explain more.
- **Solid notifications over pages.** Toasts and the link preview are no longer see-through over web pages, so the
  page's text can't show through them.
- **The welcome tour** shows what's new: stacking, reading mode and the shield in the address bar.

### Fixed
- **No more colour warp when minimising or maximising.** On some PCs the window briefly turned the wrong colour while
  Windows animated it. JBrowser now paints the window solid for the moment Windows takes its snapshot (from the
  ribbon buttons, the taskbar, keyboard shortcuts or double-clicking the title bar), repaints once the animation ends,
  and sets the window's frosted backdrop again when it comes back from the taskbar. If your PC still flickers, Settings
  › Appearance › **Animate minimising and maximising** turns Windows' animation off for JBrowser.

## [1.6.2] - 2026-10-02

### Fixed
- **Windows that keep their colours, rebuilt.** On some PCs the window still turned pale behind dark text (or the
  other way round), left a stale rectangle over the title bar after maximising, stopped dragging after switching
  between light and dark, or flashed black or white and stopped responding when Settings opened. The way JBrowser
  looks after its windows was redesigned rather than patched:
  - one part of JBrowser now owns each window's frosted backdrop and light/dark mode. It sets them when they change,
    puts the mode back after anything that can disturb it, and nothing else: it no longer reads the state back from
    Windows, rebuilds the backdrop, refreshes the window frame on activation (which could interrupt dragging) or
    restyles the whole app when Windows reports a hiccup (the loop behind the black or white flashing);
  - JBrowser paints its own base colour under its content, so dark stays dark and light stays light whatever Windows
    draws behind the window;
  - the new colours reach Qt before the new light/dark mode does, so Qt never sees a half-switched theme;
  - menus run their action after they have closed, so opening Settings from the menu no longer overlaps with the
    menu's own event loop.
- **Google sign-in, more of it.** JBrowser now keeps presenting Firefox through the whole sign-in hand-off (Google's
  country sign-in servers and YouTube's sign-in step included) and waits longer before going back to Chrome. If Google
  still says "Couldn't sign you in", JBrowser offers to introduce itself as Firefox everywhere, and tries again.
- **The update window keeps its size.** It is sized to your screen and no longer grows with long messages.

### Added
- **Settings → Advanced → How JBrowser introduces itself → Firefox**: every site sees Firefox, all the time. For PCs
  where Google refuses the sign-in whatever else JBrowser does.

### Changed
- **Frosted menus.** Right-click menus and the ··· menu are translucent, like the window and the Archive.
- **Website:** the full-screen logo animation is gone; the small JBrowser logo in the top bar catches the light when
  you arrive (and when you point at it).

## [1.6.1] - 2026-10-01

### Fixed
- **Scrolling up and down no longer slides to the next card.** When a page reached its top or bottom, the rest of an
  up-and-down scroll moved the canvas sideways to the next card. Now only sideways scrolling (a tilting wheel, a
  touchpad swipe, or the wheel with **Shift** held) moves along the canvas; **Alt + wheel** still pans from anywhere.
  A mostly vertical touchpad swipe with a little sideways wobble no longer nudges the canvas either.

## [1.6.0] - 2026-10-01

### Fixed
- **Dark mode stays dark on Acrylic.** On PCs where Windows itself is set to light mode (or the other way round),
  the frosted window could turn washed-out and pale behind light text, most often after maximising and switching
  windows, sometimes leaving a pale rectangle where the window used to be. Qt quietly re-applied Windows' own
  light/dark setting to the window whenever Windows changed a setting (an accent colour, energy saver, …). JBrowser
  now tells Qt which mode it shows, restores its own mode if anything else changes it, and redraws the whole backdrop
  when it does. Light mode on a dark Windows is fixed the same way.
- **Google sign-in, for good.** Some PCs still couldn't sign in to Google until the browser was switched to Firefox in
  DevTools. JBrowser now does that switch itself: while a page is on Google's sign-in page (in a card or a "Sign in
  with Google" popup), its space presents itself as Firefox everywhere a site can look (the user agent, JavaScript
  and the browser hints), and a few seconds after sign-in it goes back to Chrome. The sign-in page loads with the
  switch already made.
- **Fewer "I'm not a robot" checks when you're not signed in to Google.** Google's reCAPTCHA now keeps its own
  cookies on the sites that use it, so it recognises you instead of treating every visit as a stranger's, and Google's
  own pages are no longer filtered when they talk to Google. Google's other third-party cookies stay blocked.
- **Smoother horizontal scrolling,** especially on slower PCs (such as laptops with Ryzen 5 chips) and large or
  high-DPI screens. Scrolling now eases continuously instead of restarting with every wheel notch, touchpad scrolling
  moves the canvas once per frame instead of once per event, card shadows are drawn from a ready-made image, and the
  window no longer repaints its background under the canvas on every frame. Together that more than halves the work
  of each frame.

### Added
- **Settings → Advanced → Graphics acceleration.** If websites flicker or draw glitches (it happens with some graphics
  cards and drivers, often dedicated ones), choose *Compatible*, which draws pages through OpenGL like Qt WebEngine
  did before 6.5, or *Off* as a last resort. *Restart now* applies it.
- **Settings → Advanced → How JBrowser introduces itself.** The newest Chrome (as before), or the version of
  Chromium really inside JBrowser, which can help on sites that ask "I'm not a robot" often.
- **Settings → Advanced → Explain videos JBrowser can't play.** The note about videos in formats JBrowser can't play
  (such as H.264) is now off by default, as it could get in the way; turn it on here.

### Changed
- **A translucent Archive.** The Archive opens on frosted glass (Acrylic) with your colour tint, like the main window.
- **A cleaner right-click menu.** Back, Forward and Reload are gone from the menu on web pages (they're on every card
  already), and the remaining items use JBrowser's own icons.
- The Gallery no longer shows the "Click a card to open it…" line; the tips are in the filter box's tooltip.
- **Website:** the home page opens with the JBrowser logo catching the light before the page fades in, moves more
  smoothly as you scroll (softer reveals, a drifting glow, gentle depth on the screenshots), and "Ready in a minute"
  now has the picture on the left. Proper icons for search results (PNG favicons in the sizes Google asks for, a web
  app manifest, the logo in the site's structured data) help Google show the JBrowser logo.
- JBrowser is made by **The JBrowser Team**, a small group of developers; the website and documentation say so.
- Packages checked and up to date; the newest stable Chrome version is recorded as usual.

## [1.5.4] - 2026-09-30

### Added
- **Export your passwords, safely.** *Passwords → Export…* saves every login as a spreadsheet file (CSV, in the same
  layout Chrome, Edge and Firefox use) inside a ZIP locked with a password you choose, using AES-256 encryption. The
  passwords never touch the disk unencrypted. Open the ZIP with 7-Zip, WinRAR or PeaZip, or import it into JBrowser
  on another computer: *Import…* now reads these encrypted ZIPs as well as plain CSV files.

### Changed
- **A calmer Archive.** The explanations are gone: one header line ("Archive · last 48 hours") with the *Clear*
  button, the search box, and your closed cards with just the site and when you closed them. The details are in each
  card's tooltip.
- **Python 3.14.7.** JBrowser now ships with the latest Python 3.14 (it had 3.14.0), with seven releases of bug and
  security fixes. Python 3.15 is still a release candidate; JBrowser will move to it once it's final and proven.
- All packages checked and up to date.

## [1.5.3] - 2026-09-30

### Fixed
- **The one-line PowerShell install works again.** It stopped with *"Cannot validate argument on parameter
  'ArgumentList'"* in Windows PowerShell (the version built into Windows) right before opening the installer.
- Pasted into a PowerShell window opened *as administrator*, the install command now opens the installer with your
  normal rights, so JBrowser never ends up running as administrator. If JBrowser is ever started as administrator
  anyway, it says so and suggests opening it normally.

### Changed
- **Simpler downloading.** The website's *Download* buttons open a short, clear window with one big *Download for
  Windows* button. Once the download starts it shows three steps to install, including what to click if Windows
  says "Windows protected your PC". Installing with one PowerShell command is still there as an option.
- **A new "Nothing hidden" section on the website** about JBrowser being open source: all code public, nothing sent
  about you, checked downloads, free under the GPL.
- **Ready for jbrowser.app.** The website can move to its own domain with a single setting, and it now helps search
  engines: a structured description of JBrowser for Google and Bing, link previews on every page, old documentation
  versions kept out of search results, automatic notifications to Bing when pages change (IndexNow), and a
  `security.txt` for security researchers.
- Packages updated; the newest stable Chrome version is recorded as usual.
- The website and the app credit **The JBrowser Team**.

## [1.5.2] - 2026-09-29

### Changed
- **JBrowser presents itself as the current Chrome.** Websites now see Chrome 155, the newest stable version, instead
  of the year-old Chromium 140 that JBrowser's engine is built on, so no site treats JBrowser as outdated. The user
  agent is `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0
  Safari/537.36`, and the browser details sites can ask for (client hints) match it. Every release records the Chrome
  version that is current when it is built, and between releases JBrowser keeps up by date.
- **The active card's outline takes your colour.** Instead of the blue outline, the card you're using is outlined in
  a soft, washed version of your colour tint, or grey with *No colour*.
- The engine's real Chromium version is shown in *Settings → About JBrowser*.

### Fixed
- **Google sign-in, second round.** JBrowser's ad and tracker filters blocked two requests on Google's sign-in page
  that Google's security check relies on, so Google could still refuse with *"Couldn't sign you in"*. Sign-in pages
  (Google, YouTube, Microsoft and Apple) are no longer filtered; dangerous sites are still blocked everywhere.
- **Security: local files.** A web page saved on your computer and opened in JBrowser could read your other files (Qt
  allows this by default, unlike Chrome). Local pages can now show their own images and styles but can't read other
  files.
- Videos and sounds in a format JBrowser can't play yet (H.264 and AAC, which JBrowser's engine doesn't include) no
  longer just stay black: a bar explains why and offers to copy the link to open it in another browser.
- The loading spinner draws half as often (30 times a second), and not at all when its card is out of sight.

### Security
- A master password for the password vault now uses a stronger key derivation (Scrypt N=2^17, OWASP's
  recommendation). Existing vaults keep working and move up when the password is changed.
- Once JBrowser is code-signed, it installs only updates signed by the same publisher, on top of the SHA-256 check.

### Added
- **Ready for free code signing by SignPath Foundation**, which will remove *"Windows protected your PC"*: releases
  can now be built on GitHub's own Windows machines (`release-build.yml`), sent to SignPath for signing, and published
  from there. The website has the required [code signing policy](https://jbrowser.app/code-signing/)
  and a [privacy policy](https://jbrowser.app/privacy/) listing every connection JBrowser makes.
  [docs/SIGNING.md](docs/SIGNING.md) lists the steps left for the project owner. This release is still unsigned.

## [1.5.1] - 2026-09-29

### Fixed
- **Signing in to Google works.** Google stopped JBrowser with *"Couldn't sign you in. This browser or app may not
  be secure"*, because it refuses browser engines built into other apps, which is what Qt WebEngine looks like to it.
  Like other Qt WebEngine browsers, JBrowser now presents a current Firefox user agent to Google's sign-in server
  (`accounts.google.com`) only. Every other site, Google's other services included, still sees Chrome.

### Added
- **Code signing.** The build can now sign `JBrowser.exe`, the installer and its uninstaller with a code-signing
  certificate, which is what removes SmartScreen's *"Windows protected your PC"* warning. `tools/sign.ps1` works with
  a certificate in the Windows certificate store (including hardware tokens and cloud keys), a `.pfx` file or Azure
  Artifact Signing, timestamps every signature and checks it. `master.ps1` shows whether a build is signed, and the
  release notes and `INSTALL.txt` follow. [docs/SIGNING.md](docs/SIGNING.md) explains why the warning appears and
  compares the ways to get a certificate. This release is still unsigned: a certificate from a trusted authority has
  to be requested by the publisher first.
- **A website** at [jbrowser.app](https://jbrowser.app/): a home page
  with a direct download of the newest installer, a permanent download link, this changelog, and developer
  documentation for every release (architecture, web engine, privacy, UI, building and releasing, and references
  generated from each version's code), with a version switcher and search. It is built by `tools/build_site.py`
  and published by GitHub Actions on every push and release.
- The home page shows real, high-resolution screenshots of JBrowser, with a feature tour to click through, a colour
  picker that shows each tint on the real window, and screenshots that follow the site's light or dark mode.
  `tools/site_screenshots.py` retakes them all in one command.

### Changed
- The download page and the home page explain SmartScreen's warning and offer the PowerShell install, which checks
  the download and doesn't trigger the warning, with a *Copy* button.

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
