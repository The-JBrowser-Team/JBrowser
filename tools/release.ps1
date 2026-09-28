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
    .\tools\release.ps1 -SkipBuild      # reuse dist\installer from a previous build
#>
param(
    [switch]$SkipBuild,
    [switch]$Draft
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Find-Tool($name, [string[]]$candidates) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}

$desktopGit = Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop" -Directory -Filter "app-*" -ErrorAction SilentlyContinue |
    Sort-Object Name | Select-Object -Last 1 | ForEach-Object { Join-Path $_.FullName "resources\app\git\cmd\git.exe" }
$git = Find-Tool "git.exe" @($desktopGit, "$env:ProgramFiles\Git\cmd\git.exe")
$gh = Find-Tool "gh.exe" @("$env:ProgramFiles\GitHub CLI\gh.exe", "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe")
if (-not $git) { throw "git was not found (install Git, or GitHub Desktop which bundles it)." }
if (-not $gh) { throw "GitHub CLI was not found. Install it with: winget install GitHub.cli" }

Step "Checking GitHub sign-in"
& $gh auth status --hostname github.com | Out-Null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not signed in. Run: gh auth login" }

$version = (& $py tools\version.py).Trim()
$tag = "v$version"

Step "Checking the working tree"
$dirty = & $git status --porcelain
if ($dirty) { throw "There are uncommitted changes. Commit them first:`n$dirty" }
# (Windows PowerShell turns a redirected native error stream into an exception under "Stop".)
$ErrorActionPreference = "Continue"
& $gh release view $tag 2>&1 | Out-Null
$releaseExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"
if ($releaseExists) { throw "Release $tag already exists. Set a new version with: python tools\version.py --set X.Y.Z" }

Step "Reading the release notes for $version from CHANGELOG.md"
$changelog = Get-Content CHANGELOG.md -Raw -Encoding utf8
$pattern = "(?ms)^## \[$([regex]::Escape($version))\][^\n]*\n(.*?)(?=^## \[|\z)"
$match = [regex]::Match($changelog, $pattern)
if (-not $match.Success) { throw "CHANGELOG.md has no '## [$version]' section. Describe the release first." }
$notesFile = Join-Path $env:TEMP "jbrowser-release-notes-$version.md"
$notes = $match.Groups[1].Value.Trim() + "`n`n---`nInstall: download **JBrowser-Setup-$version.exe** below and run it. " +
         "Existing installations update themselves automatically.`n"
[System.IO.File]::WriteAllText($notesFile, $notes)

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build_installer.ps1")
}
$setup = Join-Path $Root "dist\installer\JBrowser-Setup-$version.exe"
if (-not (Test-Path $setup) -or -not (Test-Path "$setup.sha256")) { throw "Installer for $version not found in dist\installer." }

Step "Tagging $tag and pushing"
& $git tag -a $tag -m "JBrowser $version"
if ($LASTEXITCODE -ne 0) { throw "Could not create tag $tag" }
# Push with GitHub CLI's sign-in (for these commands only), so git needs no credentials of its own.
$gitAuth = @("-c", "credential.helper=", "-c", "credential.helper=!'$($gh -replace '\\', '/')' auth git-credential")
& $git @gitAuth push origin HEAD
if ($LASTEXITCODE -ne 0) { throw "Could not push the branch" }
& $git @gitAuth push origin $tag
if ($LASTEXITCODE -ne 0) { throw "Could not push the tag" }

Step "Creating the GitHub release"
$ghArgs = @("release", "create", $tag, $setup, "$setup.sha256", "--title", "JBrowser $version", "--notes-file",
          $notesFile, "--verify-tag")
if ($Draft) { $ghArgs += "--draft" }
& $gh @ghArgs
if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
Write-Host "Released JBrowser $version" -ForegroundColor Green
