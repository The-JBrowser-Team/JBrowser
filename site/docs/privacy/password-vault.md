---
title: The password vault and autofill
nav_title: Password vault
description: How saved passwords are encrypted, unlocked, captured and filled.
---

[`PasswordVault`](api:jbrowser.services.vault.PasswordVault) ([services/vault.py](source:jbrowser/services/vault.py))
stores logins in `vault.bin`. Nothing sensitive is ever written to disk in plain text.

## Encryption

```text
vault.bin (JSON header)
├── mode: "dpapi" | "master"
├── wrapped_key ── the 256-bit vault key, protected by DPAPI or by a key derived from the master password
├── salt, kdf, key_nonce          (master-password mode only)
└── nonce, data ── the entries, sealed with AES-256-GCM under the vault key
```

- The **vault key** is a random 256-bit AES key generated when the vault is created.
- The **entries** (origin, username, password, space, note, timestamps) and the *never save* list are serialised to
  JSON and encrypted with **AES-256-GCM** (`cryptography`), with a fresh random nonce on every save and the
  associated data `jbrowser-vault-data-v1`.
- The **vault key** itself is stored wrapped:
    - **DPAPI mode** (the default): `CryptProtectData` ties it to the Windows user account
      ([platform/win.py](source:jbrowser/platform/win.py)). The vault unlocks transparently; another Windows user,
      or the file copied to another PC, can't decrypt it.
    - **Master-password mode**: a key-encryption key is derived from the password with **Scrypt** (n = <!-- if >= 1.5.2 -->2^17 for passwords set since 1.5.2 (older vaults keep their stored n = 2^15)<!-- else -->2^15<!-- endif -->, r = 8,
      p = 1, a random salt), and wraps the vault key with AES-GCM (associated data `jbrowser-vault-key-v1`). The
      vault is locked until the password is entered.
- Switching modes re-wraps the same vault key; entries are not re-encrypted.
- The file is written with `atomic_write_bytes()`, so a crash can't corrupt it.

## Capturing and filling

The password logic in the page runs in JBrowser's **isolated world** (`AUTOFILL_JS`,
[page scripts](../engine/page-scripts.md)), so the page's own scripts can't read the bridge, the fill function or a
credential before it is placed in the form.

1. When a visible password field appears, the script calls `jbBridge.loginFormDetected(count)`.
2. `TabController.on_login_form()` looks up saved logins for the page's origin (and space). With exactly one match
   and `passwords.autofill` on, it calls `window.__jbFill(username, password)` in the isolated world.
3. When a login form is submitted, the script calls `jbBridge.credentialsSubmitted(username, password)`.
4. `on_credentials()` offers *Save* or *Update* in an info bar (`passwords.offer_save`), unless the space is
   incognito, the site is on the never list, or the login is already saved.

Logins can be saved for one space or for all spaces (`Credential.space_id == ""`).

## Other features

- **CSV import** from Chrome, Edge and Firefox exports (`import_csv`).<!-- if >= 1.5.4 --> It also reads a ZIP: plain, or AES-encrypted (it asks for the password), such as JBrowser's own export.<!-- endif -->
<!-- if >= 1.5.4 -->
- [[new 1.5.4]] **Encrypted export.** *Export…* in the password manager writes every login as CSV (the
  `name,url,username,password,note` columns Chrome, Edge and Firefox use, from `export_csv()`) inside a ZIP locked with
  a password the user chooses (at least 10 characters, typed twice). With a master password, it is asked for first.
  The CSV never touches the disk unencrypted. See [the encrypted ZIP format](#the-encrypted-zip-format) below.
<!-- endif -->
- **Password health**: `password_problems()` flags **weak** passwords (shorter than 8 characters, a common password,
  3 or fewer distinct characters, or shorter than 12 with only one kind of character) and passwords **reused** on
  more than one site, all locally.
- **Generator** and **clipboard auto-clear** in the password manager window
  ([ui/dialogs/passwords.py](source:jbrowser/ui/dialogs/passwords.py)).

<!-- if >= 1.5.4 -->
## The encrypted ZIP format

[[new 1.5.4]] Python's `zipfile` only writes the old *ZipCrypto* encryption, which a known-plaintext attack breaks, so
[core/aeszip.py](source:jbrowser/core/aeszip.py) writes **WinZip AES (AE-2) with AES-256** itself, on top of
`cryptography`:

| Part | Value |
|---|---|
| Compression method | 99, with the `0x9901` extra field: vendor version 2 (AE-2), `AE`, strength 3 (256-bit), real method 8 (deflate) |
| Key derivation | PBKDF2-HMAC-SHA1(password, random 16-byte salt, 1000 iterations) → 66 bytes: AES key, HMAC key, 2-byte password check |
| Encryption | AES-256 in counter mode with a 128-bit **little-endian** counter starting at 1 (the key stream is made with ECB, because `cryptography`'s CTR counts big-endian) |
| Authentication | the first 10 bytes of HMAC-SHA1 over the encrypted data; AE-2 stores no CRC |

7-Zip, WinRAR, PeaZip, Keka, The Unarchiver and libarchive (Windows' `tar.exe`) open these files; Windows Explorer's
*Extract All* doesn't support AES. The format's 1000 PBKDF2 iterations are fixed, so the password's strength matters,
hence the 10-character minimum. `read_zip()` reads plain and AES (AE-1/AE-2, any key strength) ZIPs, checks the
password and the HMAC, and refuses ZipCrypto. It was checked against `pyzipper` in both directions and against
`tar.exe`.
<!-- endif -->

## Security boundaries

- Anything that reads decrypted passwords runs in the main process; the renderer only sees a password when it is
  filled into a form the user is looking at.
- Master-password mode protects against someone using the same Windows account; DPAPI mode does not, by design,
  in exchange for no prompts.
- Report vault issues privately ([SECURITY.md](source:SECURITY.md)); they are explicitly in scope.
