<#
.SYNOPSIS
    The one command for building, packaging and publishing JBrowser.

.DESCRIPTION
    Runs the whole process in order:

      1. (-Version X.Y.Z) sets the new version everywhere (tools\version.py), and records the newest
         stable Chrome version, which JBrowser presents to websites (tools\chrome_version.py).
      2. Creates or updates .venv and every package, and checks every module imports (tools\update_deps.py).
      3. Builds the app and the installer (tools\build_installer.ps1), and signs them when a
         code-signing certificate is configured (tools\sign.ps1, docs\SIGNING.md).
      4. Packages them as distribution\JBrowser-<version>-<yyyy-MM-dd>.zip (+ .zip.sha256):
         the installer, its checksum, LICENSE and INSTALL.txt.
      5. (-Publish) commits any changes, pushes them, and publishes the GitHub release with the
         installer and the zip. Installed copies of JBrowser then update themselves, and the README's
         "Install the latest zip" command installs it. If this version is already released, its
         files are replaced by the new build instead.

    Before publishing a new version, describe it under "## [X.Y.Z]" in CHANGELOG.md and in the
    README's "Release notes" (see docs/RELEASING.md).

.EXAMPLE
    .\master.ps1                              # build and package the current version
    .\master.ps1 -Version 1.4.1 -Publish      # new version: build, package, commit, push, release
    .\master.ps1 -Publish                     # rebuild the current version and refresh its release files
    .\master.ps1 -SkipDeps -SkipBuild         # just re-package the last build
#>
param(
    [string]$Version,
    [switch]$Publish,
    [switch]$Draft,
    [switch]$SkipDeps,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tools\common.ps1")
Set-Location $Root
$started = Get-Date

if ($Publish) {
    Step "Checking GitHub sign-in"
    Initialize-GitHubTools
    if ($env:JBROWSER_SIGN_TEST -eq "1") { throw "JBROWSER_SIGN_TEST is set: test-signed builds must not be published. Remove it and run again." }
}
$signing = & (Join-Path $Root "tools\sign.ps1") -Status
Step $(if ($signing) { "Code signing: $signing" } else { "Code signing: none configured, the build will be unsigned (see docs\SIGNING.md)" })

# --- 1. Version ------------------------------------------------------------------------------
if (-not (Test-Path $Py)) {
    Step "Creating the Python environment (first run)"
    & py -3.14 tools\update_deps.py
    if ($LASTEXITCODE -ne 0) { throw "tools\update_deps.py failed" }
    $SkipDeps = $true
}
if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Use a version like 1.4.1 (major.minor.patch)." }
    Step "Setting the version to $Version"
    & $Py tools\version.py --set $Version
    if ($LASTEXITCODE -ne 0) { throw "tools\version.py failed" }
}
$ver = (& $Py tools\version.py).Trim()
$tag = "v$ver"
# Every update presents the Chrome that is current when it is built (jbrowser\engine\identity.py).
Step "Recording the newest Chrome version"
& $Py tools\chrome_version.py --update
if ($LASTEXITCODE -ne 0) { Write-Warning "Keeping the recorded Chrome version (the app still estimates newer ones by date)." }
if ($Publish) {
    $changelog = Get-Content CHANGELOG.md -Raw -Encoding utf8
    if ($changelog -notmatch "(?m)^## \[$([regex]::Escape($ver))\]") {
        throw "CHANGELOG.md has no '## [$ver]' section. Describe the release there (and in the README's Release notes), then run again."
    }
}

# --- 2 and 3. Dependencies and build ------------------------------------------------------------
if (-not $SkipDeps) {
    Step "Updating packages and checking every import"
    & $Py tools\update_deps.py
    if ($LASTEXITCODE -ne 0) { throw "tools\update_deps.py failed" }
}
if (-not $SkipBuild) {
    & (Join-Path $Root "tools\build_installer.ps1") -SkipDeps
}
$setup = Join-Path $DistDir "installer\JBrowser-Setup-$ver.exe"
if (-not (Test-Path $setup) -or -not (Test-Path "$setup.sha256")) {
    throw "No installer for $ver in $DistDir\installer. Run without -SkipBuild."
}

# --- 4. Package ------------------------------------------------------------------------------
$zip = & (Join-Path $Root "tools\package.ps1") | Select-Object -Last 1
$zipName = Split-Path -Leaf $zip
$setupSigned = (Get-AuthenticodeSignature $setup).Status -eq "Valid"

# --- 5. Publish ------------------------------------------------------------------------------
if ($Publish) {
    $changes = & $Git status --porcelain
    if ($changes) {
        Step "Committing changes for JBrowser $ver"
        $changes | ForEach-Object { Write-Host "    $_" }
        & $Git add -A
        & $Git commit -q -m "JBrowser $ver"
        if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
    }
    if (Test-GitHubRelease $tag) {
        Step "Release $tag exists: pushing and replacing its files with this build"
        & $Git @GitAuth push origin HEAD
        if ($LASTEXITCODE -ne 0) { throw "Could not push the branch" }
        & $Gh release upload $tag $setup "$setup.sha256" $zip "$zip.sha256" --clobber
        if ($LASTEXITCODE -ne 0) { throw "gh release upload failed" }
        # Keep one zip per release: remove zips from earlier builds of this version.
        $old = & $Gh release view $tag --json assets --jq ".assets[].name" |
            Where-Object { $_ -match '^JBrowser-.*\.zip(\.sha256)?$' -and $_ -notlike "$zipName*" }
        foreach ($name in $old) { & $Gh release delete-asset $tag $name --yes | Out-Null }
        Update-Website
    } else {
        & (Join-Path $Root "tools\release.ps1") -SkipBuild -Draft:$Draft -ExtraAssets @($zip, "$zip.sha256")
    }
}

$mb = "{0:N0} MB" -f ((Get-Item $zip).Length / 1MB)
$took = [int]((Get-Date) - $started).TotalMinutes
Write-Host ""
Write-Host "JBrowser $ver is ready ($took min)" -ForegroundColor Green
Write-Host "  Zip:       $zip ($mb)"
Write-Host "  Installer: $setup ($(if ($setupSigned) { 'signed' } else { 'not signed' }))"
if ($Publish) {
    Write-Host "  Release:   https://github.com/The-JBrowser-Team/JBrowser/releases/tag/$tag"
} else {
    Write-Host "  Not published. Run again with -Publish to release it on GitHub."
}
