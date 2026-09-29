"""JBrowser: a spatial, privacy-focused web browser for Windows 11.

This module is the single source of truth for the application's identity. The version
below is read by the build scripts (``tools/version.py``), the Windows installer and the
auto-updater, so a release only ever needs this one line changed.
"""

APP_NAME = "JBrowser"
APP_ID = "JBrowser.Browser.1"             # Windows AppUserModelID (taskbar grouping)
ORG_NAME = "JBrowser"                     # Qt organisation name (do not change: it names data folders)
COMPANY = "The JBrowser Company"
__version__ = "1.5.0"

# Where releases are published. The auto-updater asks the GitHub Releases API for the
# latest release of this repository.
GITHUB_REPO = "The-JBrowser-Team/JBrowser"
HOMEPAGE = f"https://github.com/{GITHUB_REPO}"
RELEASES_PAGE = f"{HOMEPAGE}/releases"

# Named mutex held while JBrowser runs; the installer uses it to detect a running copy.
APP_MUTEX = "JBrowser.AppMutex"
