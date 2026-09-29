# Code signing and SmartScreen

When someone downloads `JBrowser-Setup-<version>.exe` with a browser and runs it, Windows SmartScreen can stop it
with **"Windows protected your PC"** (*More info → Run anyway* continues). This page explains why, what removes the
warning, and how JBrowser's build signs its programs once a certificate is available.

## Why the warning appears

SmartScreen checks programs that carry the **Mark-of-the-Web**, the tag browsers add to downloaded files (extracting
a downloaded zip passes it on). It lets a program run without a warning when the program has a **reputation**: many
people have run it, or it is signed with a certificate that has.

| Situation | Warning? |
|---|---|
| Unsigned installer, downloaded with a browser | **Yes**, until that exact file has been run by enough people. Every release is a new file and starts again. |
| Signed with a code-signing certificate from a trusted certificate authority | At first, sometimes. The reputation belongs to the **certificate**, so it builds up over releases and new versions inherit it. |
| Signed with a self-signed certificate | **Yes.** Windows doesn't trust it, so it counts as unsigned (or worse). |
| Installed with the [one-command install](../README.md#one-command-recommended) (`install.ps1`) | **No**: PowerShell's download has no Mark-of-the-Web, and the script removes it anyway after checking the SHA-256. |
| Updated by JBrowser's own updater | **No**: the updater checks the installer's SHA-256 and runs it without the Mark-of-the-Web. |

Since 2024, EV (extended validation) certificates no longer skip the reputation stage either; they build it the same
way as ordinary (OV) certificates. With *Smart App Control* switched on (a Windows 11 option, off on most PCs),
unsigned programs are blocked outright, which only a trusted signature fixes.

## Getting a certificate

A code-signing certificate proves who published a program, so every option below checks the publisher's identity
first. Prices and eligibility change (these are from September 2026); check the provider's page, and Microsoft's
[code signing options for Windows app developers](https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options).

| Option | Cost | Notes |
|---|---|---|
| [SignPath Foundation](https://signpath.org/) | Free for open-source projects | The certificate belongs to SignPath Foundation, which signs builds made by CI from the public repository. JBrowser would first need its release build to run on GitHub Actions. Apply on their site. |
| [Certum Open Source Code Signing](https://shop.certum.eu/open-source-code-signing.html) | From about €69 | For developers of free and open-source software; the publisher shows as "Open Source Developer, *name*". The key is on a smart card (a reader is included), and the certificate appears in Windows' certificate store while the card is in. |
| [Azure Artifact Signing](https://azure.microsoft.com/products/artifact-signing) (formerly Trusted Signing) | US$9.99 a month | Microsoft signs through an Azure account after identity validation. Individuals must be in the USA or Canada; organisations in the USA, Canada, the EU or the UK. Needs signtool. |
| An OV code-signing certificate (Sectigo, DigiCert, GlobalSign, SSL.com and resellers) | A few hundred US$ a year | Keys must be on a hardware token or in a cloud HSM (a CA/Browser Forum rule since 2023). |

Publishing JBrowser in the **Microsoft Store** is another route: the Store signs the package itself and Store installs
never show SmartScreen. It would need an MSIX package and a (free, for individuals) Microsoft developer account.

## Signing a build

[tools/sign.ps1](../tools/sign.ps1) signs `JBrowser.exe` (called by `tools\build_app.ps1`), and Inno Setup calls it
for `JBrowser-Setup-<version>.exe` and the uninstaller inside it (`tools\build_installer.ps1` passes
`/DSignSetup` and a `jbsign` sign tool). The installer's `.sha256` is written after signing. Without a certificate it
does nothing, and builds are unsigned as before. Configure one with environment variables:

| Variable | Meaning |
|---|---|
| `JBROWSER_SIGN_THUMBPRINT` | The SHA-1 thumbprint of a certificate in `Cert:\CurrentUser\My` or `Cert:\LocalMachine\My` (hardware tokens and cloud HSMs appear there) |
| `JBROWSER_SIGN_PFX`, `JBROWSER_SIGN_PFX_PASSWORD` | Or a `.pfx` file and its password |
| `JBROWSER_SIGN_AZURE`, `JBROWSER_SIGN_AZURE_DLIB` | Or Azure Artifact Signing: the `metadata.json` and the path to `Azure.CodeSigning.Dlib.dll` |
| `JBROWSER_SIGN_TIMESTAMP` | Optional timestamp server (by default DigiCert, then Sectigo, then GlobalSign) |
| `JBROWSER_SIGN_TEST=1` | Accept a certificate Windows doesn't trust, to test the pipeline. `master.ps1 -Publish` refuses to run with it. |

```powershell
$env:JBROWSER_SIGN_THUMBPRINT = "0123456789ABCDEF0123456789ABCDEF01234567"
.\tools\sign.ps1 -Status          # prints the certificate and tool that will be used
.\master.ps1 -Version 1.5.2 -Publish
```

`master.ps1` prints whether signing is configured before it builds, and whether the installer came out signed. The
release notes and `INSTALL.txt` then name the publisher instead of explaining the SmartScreen warning.

signtool.exe (Windows SDK: `winget install Microsoft.WindowsSDK.10.0.26100`) is used when it is installed, and is
required for Azure. Without it, `Set-AuthenticodeSignature` signs with a certificate or `.pfx` file. Every signature
is SHA-256 and timestamped, so it stays valid after the certificate expires, and each file is checked after signing.

### Testing the pipeline without a real certificate

Make a throw-away self-signed certificate as a `.pfx` (in memory, so nothing is added to Windows' certificate
stores), sign with `JBROWSER_SIGN_TEST=1`, check the result, and delete the `.pfx`. Never publish a build signed this
way: `Get-AuthenticodeSignature` reports it as `UnknownError` because the certificate isn't trusted.
