<#
.SYNOPSIS
    Publishes a JBrowser release on GitHub (which is what the in-app auto-updater looks for).

.DESCRIPTION
    Before running: set the version (python tools\version.py --set X.Y.Z), describe it in
    CHANGELOG.md under "## [X.Y.Z]", and commit everything.

    The script then:
      1. checks GitHub CLI is signed in and the working tree is clean,
      2. builds the installer (tools\build_installer.ps1) unless -SkipBuild,
      3. tags the commit vX.Y.Z and pushes the branch and the tag,
      4. creates the GitHub release with the CHANGELOG section as its notes and uploads
         JBrowser-Setup-X.Y.Z.exe and its .sha256 checksum.

    Installed copies of JBrowser find the new release within a day (or at once with
    Settings > About > Check now) and update themselves.

.EXAMPLE
    .\tools\release.ps1
    .\tools\release.ps1 -Draft          # create the release as a draft to review on github.com first
    .\tools\release.ps1 -SkipBuild      # reuse the installer from a previous build
#>
param(
    [switch]$SkipBuild,
    [switch]$Draft,
    [string[]]$ExtraAssets = @()     # more files to attach (master.ps1 passes the zip)
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

Step "Checking GitHub sign-in"
Initialize-GitHubTools
$git, $gh = $Git, $Gh

$version = (& $Py tools\version.py).Trim()
$tag = "v$version"

Step "Checking the working tree"
$dirty = & $git status --porcelain
if ($dirty) { throw "There are uncommitted changes. Commit them first:`n$dirty" }
if (Test-GitHubRelease $tag) { throw "Release $tag already exists. Set a new version with: python tools\version.py --set X.Y.Z" }

Step "Reading the release notes for $version from CHANGELOG.md"
$changelog = Get-Content CHANGELOG.md -Raw -Encoding utf8
$pattern = "(?ms)^## \[$([regex]::Escape($version))\][^\n]*\n(.*?)(?=^## \[|\z)"
$match = [regex]::Match($changelog, $pattern)
if (-not $match.Success) { throw "CHANGELOG.md has no '## [$version]' section. Describe the release first." }

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build_installer.ps1")
}
$setup = Join-Path $DistDir "installer\JBrowser-Setup-$version.exe"
if (-not (Test-Path $setup) -or -not (Test-Path "$setup.sha256")) { throw "Installer for $version not found in $DistDir\installer." }

$signer = Get-AuthenticodeSignature $setup
$smartScreen = if ($signer.Status -eq "Valid") {
    "The installer is signed by *$($signer.SignerCertificate.GetNameInfo('SimpleName', $false))*. "
} else {
    "The installer is not code-signed, so Windows SmartScreen may warn about it: choose *More info* → *Run anyway*. " +
    "The one-command install in the README avoids the warning. "
}
$notesFile = Join-Path $env:TEMP "jbrowser-release-notes-$version.md"
$notes = $match.Groups[1].Value.Trim() + "`n`n---`nInstall: download **JBrowser-Setup-$version.exe** below and run it. " +
         "Existing installations update themselves automatically.`n`n" + $smartScreen +
         "You can check the download against **JBrowser-Setup-$version.exe.sha256**.`n"
[System.IO.File]::WriteAllText($notesFile, $notes)

Step "Tagging $tag and pushing"
$tagCommit = & $git rev-parse -q --verify "refs/tags/$tag^{commit}"
if ($tagCommit) {
    # Resuming a run that stopped after tagging: fine as long as the tag is on this commit.
    if ($tagCommit -ne (& $git rev-parse HEAD)) { throw "Tag $tag already exists on a different commit." }
    Write-Host "Tag $tag already exists on this commit; reusing it."
} else {
    & $git tag -a $tag -m "JBrowser $version"
    if ($LASTEXITCODE -ne 0) { throw "Could not create tag $tag" }
}
# Push with GitHub CLI's sign-in (for these commands only), so git needs no credentials of its own.
& $git @GitAuth push origin HEAD
if ($LASTEXITCODE -ne 0) { throw "Could not push the branch" }
& $git @GitAuth push origin $tag
if ($LASTEXITCODE -ne 0) { throw "Could not push the tag" }

Step "Creating the GitHub release"
foreach ($f in $ExtraAssets) { if (-not (Test-Path $f)) { throw "Extra asset not found: $f" } }
$ghArgs = @("release", "create", $tag, $setup, "$setup.sha256") + @($ExtraAssets) +
          @("--title", "JBrowser $version", "--notes-file", $notesFile, "--verify-tag")
if ($Draft) { $ghArgs += "--draft" }
& $gh @ghArgs
if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
Write-Host "Released JBrowser $version" -ForegroundColor Green
