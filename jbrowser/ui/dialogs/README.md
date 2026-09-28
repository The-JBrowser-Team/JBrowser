# `jbrowser/ui/dialogs/`: Settings and tool windows

They are imported only when first opened, which keeps start-up fast. The PyInstaller spec collects them explicitly.
Tool windows subclass `ChromeWindow` (`../chrome_window.py`), and small prompts subclass `JDialog` (`base.py`).

| File | Window |
|---|---|
| `settings.py` | **Settings** (Ctrl+,): every page, search, and the *About* page with the updates card |
| `update.py` | **Update JBrowser**: release notes, download progress, *Install and restart* |
| `history.py` | History (Ctrl+H) |
| `bookmarks.py` | Bookmarks manager with HTML import and export |
| `downloads.py` | Downloads (Ctrl+J) |
| `passwords.py` | Passwords: the vault, generator, import and health check |
| `site_data.py` | Cookies and site permissions |
| `userscripts.py` | User scripts and styles editor |
| `network.py` | Proxies and the localhost developer toolkit |
| `space.py` | Create or edit a space |
| `auth.py` | HTTP and proxy sign-in prompt |
| `popup.py` | Pop-up windows opened by pages (OAuth, payments) |
| `media.py` | Screen and window picker for screen sharing |
| `base.py` | `JDialog`, the shared base for small modal dialogs |
