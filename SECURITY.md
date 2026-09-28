# Security policy

## Supported versions

Only the latest release receives fixes. Installed copies update themselves (see
[docs/AUTO_UPDATE.md](docs/AUTO_UPDATE.md)), so the latest release is what almost everyone runs.

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Older releases | ❌ Please update |

Web-engine (Chromium) security fixes reach JBrowser through new PyQt6-WebEngine releases. `tools/update_deps.py`
picks them up, and a new JBrowser release ships them.

## Report a vulnerability

Please **do not open a public issue**. Instead:

1. Use **[Report a vulnerability](https://github.com/The-JBrowser-Team/JBrowser/security/advisories/new)**
   (GitHub private vulnerability reporting, also on the repository's **Security** tab), or
2. If that isn't available, open an issue titled "Security contact request" that contains **no details**, and a
   maintainer will reach out privately.

Include the affected version, what an attacker could do, and the steps to reproduce. Expect an acknowledgement within
a few days. Once a fix is released you will be credited in the changelog, unless you prefer not to be.

## Scope

Examples that are in scope:
- The password vault (`jbrowser/services/vault.py`), autofill, or the isolated script world leaking data to pages.
- Spaces leaking cookies or storage into each other, or incognito spaces writing to disk.
- The auto-updater accepting an installer that was not published on this repository's Releases page, or skipping its
  SHA-256 check.
- Bypassing the phishing, malware or download-protection features.

Bugs in Chromium itself should also go to the [Chromium project](https://www.chromium.org/Home/chromium-security/reporting-security-bugs/).
