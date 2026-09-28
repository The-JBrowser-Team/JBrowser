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

$BuildRoot = Get-BuildRoot
$DistDir = Join-Path $BuildRoot "dist"
$WorkDir = Join-Path $BuildRoot "build"
