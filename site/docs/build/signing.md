---
title: Code signing and SmartScreen
nav_title: Code signing
description: Why Windows says "Windows protected your PC", what removes the warning, how the build signs JBrowser with a certificate, and the SignPath workflow.
since: 1.5.1
---

[[new 1.5.1]] When someone downloads `JBrowser-Setup-<version>.exe` with a browser and runs it, Windows SmartScreen
can stop it with **"Windows protected your PC"**. The build can sign JBrowser's programs with a code-signing
certificate; this page explains what that does and doesn't change.

## Why the warning appears

SmartScreen checks programs that carry the **Mark-of-the-Web**, the tag browsers add to downloaded files (extracting
a downloaded zip passes it on). A program runs without a warning when it has a **reputation**: enough people have run
it, or it is signed with a certificate that has.

| Situation | Warning? |
|---|---|
| Unsigned installer, downloaded with a browser | **Yes**, until that exact file has been run by enough people. Every release is a new file and starts again. |
| Signed with a certificate from a trusted certificate authority | At first, sometimes. The reputation belongs to the **certificate**, so it builds up over releases and new versions inherit it. |
| Signed with a self-signed certificate | **Yes**: Windows doesn't trust the certificate. |
| Installed with the one-command install (`install.ps1`) | **No**: PowerShell's download has no Mark-of-the-Web, and the script removes it after checking the SHA-256. |
| Updated by JBrowser's [updater](auto-update.md) | **No**: the installer is checked against its SHA-256 and run without the Mark-of-the-Web. |

EV certificates no longer skip the reputation stage (since 2024). With *Smart App Control* on (a Windows 11 option,
off on most PCs), unsigned programs are blocked outright.

## Getting a certificate

Every option checks the publisher's identity first, so it has to be requested by the project's owner.
[docs/SIGNING.md](repo:docs/SIGNING.md) compares them: SignPath Foundation (free for open-source projects, for builds
made by CI), Certum Open Source Code Signing (from about €69, on a smart card), Azure Artifact Signing (US$9.99 a
month; individuals in the USA and Canada only) and commercial OV certificates. A Microsoft Store listing (MSIX,
signed by the Store) avoids SmartScreen entirely.
<!-- if >= 1.5.2 -->

## Signed builds on GitHub Actions (SignPath Foundation)

[[new 1.5.2]] SignPath Foundation signs open-source releases for free, but only builds it can trace to the public
repository: made by a workflow on GitHub-hosted runners, and approved by hand for each release. JBrowser is set up for
it; the project owner applies and connects the accounts ([docs/SIGNING.md](repo:docs/SIGNING.md) lists the steps).

```text
master.ps1 -Publish ──► release.ps1 ──► draft release vX.Y.Z (notes only)
                                   └──► release-build.yml on windows-latest (GitHub-hosted)
                                          build JBrowser.exe ──► SignPath "app" ──► signed JBrowser.exe
                                          build the installer ─► SignPath "installer" ─► signed Setup
                                          check signatures, write .sha256, package the zip (tools/package.ps1)
                                          attach the files, publish the release, rebuild the website
```

| Piece | Role |
|---|---|
| [release-build.yml](source:.github/workflows/release-build.yml) | The build. Inputs: `ref` (a tag) and `publish`. With the `SIGNPATH_ORGANIZATION_ID` variable and `SIGNPATH_API_TOKEN` secret it submits signing requests (`signpath/github-action-submit-signing-request@v3`, waiting up to a day for approval); without them it builds unsigned, which is how the workflow is tested. |
| [.signpath/artifact-configurations](source:.signpath/artifact-configurations/app.xml) | `app.xml` and `installer.xml`, pasted into SignPath. They restrict signing to files whose product name is JBrowser and whose version is the release's. |
| `Test-SignPath` in [tools/common.ps1](source:tools/common.ps1) | Asks GitHub whether the variable exists; `release.ps1` then creates a draft and starts the workflow instead of uploading a local build. |
| [tools/package.ps1](source:tools/package.ps1) | Makes the zip, the same way on the PC and in the workflow. |
| `Updater.signature_problem()` in [services/updater.py](source:jbrowser/services/updater.py) | Once the running JBrowser is signed, an update must be validly signed by the same publisher (`win.authenticode()`), on top of the SHA-256 check. |

The installer's version resource carries the same product name and version as `JBrowser.exe`
(`VersionInfoProductName`, `VersionInfoProductTextVersion` in the `.iss`), so both pass SignPath's metadata checks.
SignPath signs the installer after Inno Setup has built it, so the uninstaller inside stays unsigned; Windows never
checks an uninstaller's reputation.
<!-- endif -->

## How the build signs

[tools/sign.ps1](source:tools/sign.ps1) does the signing. It is called for:

| File | Called by |
|---|---|
| `dist\JBrowser\JBrowser.exe` | `tools\build_app.ps1`, right after PyInstaller |
| the uninstaller inside Setup | Inno Setup, while compiling (`SignedUninstaller=yes`) |
| `JBrowser-Setup-<version>.exe` | Inno Setup, at the end; the `.sha256` is written after it |

`tools\build_installer.ps1` asks `sign.ps1 -Status` whether a certificate is configured. If one is, it passes
`/DSignSetup` (which turns on `SignTool=jbsign` in [installer/JBrowser.iss](source:installer/JBrowser.iss)) and
defines the `jbsign` tool as `powershell.exe -File tools\sign.ps1 $f`. With nothing configured, `sign.ps1` does
nothing and builds are unsigned.

The certificate comes from environment variables:

| Variable | Meaning |
|---|---|
| `JBROWSER_SIGN_THUMBPRINT` | SHA-1 thumbprint of a certificate in `Cert:\CurrentUser\My` or `Cert:\LocalMachine\My`, including hardware tokens and cloud HSMs |
| `JBROWSER_SIGN_PFX`, `JBROWSER_SIGN_PFX_PASSWORD` | a `.pfx` file and its password |
| `JBROWSER_SIGN_AZURE`, `JBROWSER_SIGN_AZURE_DLIB` | Azure Artifact Signing: `metadata.json` and `Azure.CodeSigning.Dlib.dll` |
| `JBROWSER_SIGN_TIMESTAMP` | a timestamp server (default: DigiCert, then Sectigo, then GlobalSign) |
| `JBROWSER_SIGN_TEST=1` | accept an untrusted (self-signed) certificate, for testing; `master.ps1 -Publish` refuses to run with it |

```powershell
$env:JBROWSER_SIGN_THUMBPRINT = "0123456789ABCDEF0123456789ABCDEF01234567"
.\tools\sign.ps1 -Status          # the certificate and tool that will be used
.\master.ps1 -Version 1.5.2 -Publish
```

`sign.ps1` uses signtool.exe from the Windows SDK when it is installed (required for Azure), and otherwise
`Set-AuthenticodeSignature`. Signatures are SHA-256 and timestamped, so they stay valid after the certificate
expires. Timestamp servers are retried, and each file is checked afterwards: the signature must be `Valid` (or, in
test mode, present and made by the configured certificate).

`master.ps1` shows before building whether signing is configured, and afterwards whether Setup is signed. A signed
build's release notes and `INSTALL.txt` name the publisher instead of explaining the SmartScreen warning.

!!! note "PyInstaller and signing"
    Signing appends a certificate table to `JBrowser.exe`. PyInstaller's bootloader finds its archive from the end of
    the file and copes with that; a signed build starts normally. Check with a throw-away profile after changing how
    the exe is built.

## Testing without a real certificate

Create a self-signed code-signing certificate in memory and export it as a `.pfx` (`CertificateRequest` in .NET), so
nothing is added to Windows' certificate stores. Then set `JBROWSER_SIGN_PFX`, `JBROWSER_SIGN_PFX_PASSWORD` and
`JBROWSER_SIGN_TEST=1`, build or sign a copy, check `Get-AuthenticodeSignature` (it reports `UnknownError`: the
certificate isn't trusted), and delete the `.pfx`. Never publish a build signed this way.
