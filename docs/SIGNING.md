# Code signing and SmartScreen

When someone downloads `JBrowser-Setup-<version>.exe` with a browser and runs it, Windows SmartScreen can stop it
with **"Windows protected your PC"** (*More info → Run anyway* continues). This page explains why, what removes the
warning, how JBrowser is set up to be signed by **SignPath Foundation** (free for open-source projects), and what the
Microsoft Security Intelligence portal can and can't do.

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
| [SignPath Foundation](https://signpath.org/) | Free for open-source projects | **JBrowser is ready for it** (next section). The certificate belongs to SignPath Foundation, which signs only builds made on GitHub's runners from this repository. |
| [Certum Open Source Code Signing](https://shop.certum.eu/open-source-code-signing.html) | From about €69 | For developers of free and open-source software; the publisher shows as "Open Source Developer, *name*". The key is on a smart card (a reader is included). Signs locally with `tools/sign.ps1`. |
| [Azure Artifact Signing](https://azure.microsoft.com/products/artifact-signing) (formerly Trusted Signing) | US$9.99 a month | Microsoft signs through an Azure account after identity validation. Individuals must be in the USA or Canada; organisations in the USA, Canada, the EU or the UK. |
| An OV code-signing certificate (Sectigo, DigiCert, GlobalSign, SSL.com and resellers) | A few hundred US$ a year | Keys must be on a hardware token or in a cloud HSM (a CA/Browser Forum rule since 2023). |

Publishing JBrowser in the **Microsoft Store** is another route: the Store signs the package itself and Store installs
never show SmartScreen. It would need an MSIX package and a (free, for individuals) Microsoft developer account.

## SignPath Foundation (the plan)

SignPath Foundation gives open-source projects a code-signing certificate for free. In return it signs only what it
can trace back to the project's public source code: builds made by a GitHub Actions workflow on GitHub-hosted
runners, approved by hand for every release. Programs signed this way show **SignPath Foundation** as the publisher.

### What is ready in the repository

| Piece | What it does |
|---|---|
| [`.github/workflows/release-build.yml`](../.github/workflows/release-build.yml) | Builds `JBrowser.exe` and the installer on a GitHub-hosted Windows runner from a release tag. With SignPath set up, it sends `JBrowser.exe` to SignPath before packing it into the installer, then the installer, checks both signatures, writes the checksums and the zip, attaches them to the release and publishes it. Without SignPath it makes the same build unsigned (that's how it is tested). |
| [`.signpath/artifact-configurations/`](../.signpath/artifact-configurations/) | The two SignPath artifact configurations (`app` and `installer`), which also check the product name (JBrowser) and version, as SignPath Foundation requires. |
| [`tools/release.ps1`](../tools/release.ps1) | When the repository has the `SIGNPATH_ORGANIZATION_ID` variable, it creates the release as a draft and starts the signed build instead of uploading a local, unsigned one. |
| The website's [code signing policy](https://the-jbrowser-team.github.io/JBrowser/code-signing/) and [privacy policy](https://the-jbrowser-team.github.io/JBrowser/privacy/) | Required by SignPath Foundation: what is signed, team roles, and every connection JBrowser makes. |
| The updater | Once the installed JBrowser is signed, it installs only updates signed by the same publisher (on top of the SHA-256 check). Unsigned copies keep updating as before. |

### What the project owner does (once)

These steps need the owner's identity and accounts, so they can't be automated:

1. **Turn on two-factor authentication** for the The-JBrowser-Team GitHub account, and for any other account with
   write access to the repository (SignPath Foundation requires it; *Settings → Password and authentication*).
2. **Apply** at [signpath.org/apply](https://signpath.org/apply). Give the project name (JBrowser), the repository
   (`https://github.com/The-JBrowser-Team/JBrowser`), the website, the licence (GPL-3.0), and the code signing policy
   page. Mention that releases are built by `release-build.yml` on GitHub-hosted runners.
3. When accepted, **sign in to SignPath** (app.signpath.io) and turn on multi-factor authentication there too.
4. **Install the [SignPath GitHub App](https://github.com/apps/signpath)** for the JBrowser repository.
5. In SignPath, **set up the project** (SignPath Foundation usually prepares most of this):
   - add the predefined *GitHub.com* trusted build system to the organization and link it to the project;
   - project slug `JBrowser`, linked to the repository;
   - artifact configurations `app` and `installer`: paste the two files from `.signpath/artifact-configurations/`;
   - a signing policy `release-signing` with the SignPath Foundation certificate, you as approver, and origin
     verification allowing only the `release-build.yml` workflow on `refs/tags/v*`.
6. **Give GitHub the keys.** Create an API token for a CI user with the *submitter* role, then, in the repository
   folder:
   ```powershell
   gh secret set SIGNPATH_API_TOKEN                       # paste the token when asked
   gh variable set SIGNPATH_ORGANIZATION_ID --body "<organization id>"
   # only if you chose other names in SignPath:
   gh variable set SIGNPATH_PROJECT_SLUG --body "JBrowser"
   gh variable set SIGNPATH_POLICY_SLUG --body "release-signing"
   ```
7. **Release as usual**: `.\master.ps1 -Version X.Y.Z -Publish`. It makes a draft release and starts the signed build;
   approve the two signing requests in SignPath when it asks (by e-mail), and the workflow publishes the release.

From then on every update is signed, and signed copies of JBrowser accept only signed updates.

**What to expect from SmartScreen:** SignPath Foundation's certificate is shared by many open-source projects, so it
is far more likely to be recognised quickly than a brand-new personal certificate. Microsoft decides reputation,
though, so the first signed releases may still show the warning for a while.

## The Microsoft Security Intelligence portal

Microsoft's [file submission portal](https://www.microsoft.com/wdsi/filesubmission) lets software developers ask
Microsoft to analyse a file they believe is wrongly flagged.

**Assessment: not a solid plan on its own, so it has not been done.** SmartScreen's "Windows protected your PC" for
JBrowser is not a malware detection; it means the file has no reputation yet. A submission can confirm that the
installer is clean, and Microsoft sometimes clears the warning for that exact file, but:

- it applies to **one file**: every release is a new file and would need a new submission, and the result isn't
  guaranteed or fast (days);
- it needs the publisher's Microsoft account, so it can't be part of the automated release;
- signing (above) fixes the cause for all future releases at once.

It is worth doing if Microsoft Defender ever **detects JBrowser as malware** (a false positive), which has not happened.
To submit a release anyway:

1. Download `JBrowser-Setup-<version>.exe` from the [latest release](https://github.com/The-JBrowser-Team/JBrowser/releases/latest).
2. Open the [submission portal](https://www.microsoft.com/wdsi/filesubmission), choose **Software developer**, and sign in
   with your Microsoft account.
3. Choose **Microsoft Defender SmartScreen** as the product if it is offered (otherwise *Microsoft Defender Antivirus*),
   select the installer, and choose **Incorrect detection** (the file is clean).
4. In the details, give the warning ("Windows protected your PC: unrecognized app"), the release page, the SHA-256 from
   the `.sha256` file, and say that JBrowser is open source (link the repository).
5. Submit, and follow the submission's status on the portal. Repeat for each release you want cleared.

## Signing on your own PC

[tools/sign.ps1](../tools/sign.ps1) signs locally built programs with a certificate of your own (Certum, Azure, OV):
`JBrowser.exe` (called by `tools\build_app.ps1`), and `JBrowser-Setup-<version>.exe` plus the uninstaller inside it
(Inno Setup runs it; `tools\build_installer.ps1` passes `/DSignSetup` and a `jbsign` sign tool). The installer's
`.sha256` is written after signing. Without a certificate it does nothing. Configure one with environment variables:

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
