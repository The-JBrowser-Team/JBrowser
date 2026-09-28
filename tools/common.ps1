<#
.SYNOPSIS
    Shared settings for the build and release scripts (dot-sourced: . "$PSScriptRoot\common.ps1").

.DESCRIPTION
    Defines $Root (the repository), $Py (the .venv Python), the Step helper, and where build
    output goes:

      $DistDir   finished builds: JBrowser\JBrowser.exe and installer\JBrowser-Setup-<v>.exe
      $WorkDir   PyInstaller's temporary files

    Normally both live in the repository (dist\ and build\, ignored by git). When the repository
    is inside OneDrive they go to %LOCALAPPDATA%\JBrowser-build instead: OneDrive would otherwise
    upload ~700 MB per build and lock files while PyInstaller is still writing them. Set
    JBROWSER_BUILD_DIR to choose another folder.
#>
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Get-BuildRoot {
    if ($env:JBROWSER_BUILD_DIR) { return $env:JBROWSER_BUILD_DIR }
    foreach ($oneDrive in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
        if ($oneDrive -and $Root.StartsWith($oneDrive.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return Join-Path $env:LOCALAPPDATA "JBrowser-build"
        }
    }
    return $Root
}

# Finds git (Git for Windows, or the copy bundled with GitHub Desktop) and GitHub CLI, and sets
# $Git, $Gh and $GitAuth (arguments that make git push with GitHub CLI's sign-in).
function Initialize-GitHubTools {
    function Find-Tool($name, [string[]]$candidates) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return $p } }
        return $null
    }
    $desktopGit = Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop" -Directory -Filter "app-*" -ErrorAction SilentlyContinue |
        Sort-Object Name | Select-Object -Last 1 | ForEach-Object { Join-Path $_.FullName "resources\app\git\cmd\git.exe" }
    $script:Git = Find-Tool "git.exe" @($desktopGit, "$env:ProgramFiles\Git\cmd\git.exe")
    $script:Gh = Find-Tool "gh.exe" @("$env:ProgramFiles\GitHub CLI\gh.exe", "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe")
    if (-not $script:Git) { throw "git was not found (install Git, or GitHub Desktop which bundles it)." }
    if (-not $script:Gh) { throw "GitHub CLI was not found. Install it with: winget install GitHub.cli" }
    # gh calls git itself (to find the repository), and GitHub Desktop's git is not on PATH.
    $env:PATH = (Split-Path -Parent $script:Git) + ";" + $env:PATH
    $script:GitAuth = @("-c", "credential.helper=",
                        "-c", "credential.helper=!'$($script:Gh -replace '\\', '/')' auth git-credential")
    & $script:Gh auth status --hostname github.com | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not signed in. Run: gh auth login" }
}

# True when the GitHub release for this tag exists. (Windows PowerShell turns a redirected native
# error stream into an exception under "Stop", hence the temporary "Continue".)
function Test-GitHubRelease($tag) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $script:Gh release view $tag 2>&1 | Out-Null
    $exists = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $saved
    return $exists
}

$BuildRoot = Get-BuildRoot
$DistDir = Join-Path $BuildRoot "dist"
$WorkDir = Join-Path $BuildRoot "build"
