<#
.SYNOPSIS
    Builds the Windows installer: dist\installer\JBrowser-Setup-<version>.exe (+ .sha256).

.DESCRIPTION
    1. Builds the app with tools\build_app.ps1 (skip with -SkipAppBuild to reuse dist\JBrowser).
    2. Compiles installer\JBrowser.iss with Inno Setup 6 (ISCC.exe).
    3. Writes JBrowser-Setup-<version>.exe.sha256, which the auto-updater uses to verify
       downloads. Both files are what tools\release.ps1 uploads to GitHub.

    Inno Setup: winget install JRSoftware.InnoSetup

.EXAMPLE
    .\tools\build_installer.ps1
    .\tools\build_installer.ps1 -SkipAppBuild
#>
param(
    [switch]$SkipAppBuild,
    [switch]$SkipDeps
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Find-ISCC {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { return $p }
    }
    throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup"
}

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "build_app.ps1") -SkipDeps:$SkipDeps
}
if (-not (Test-Path "dist\JBrowser\JBrowser.exe")) { throw "dist\JBrowser is missing. Build the app first." }

$version = (& $py tools\version.py).Trim()
$outDir = Join-Path $Root "dist\installer"
New-Item -ItemType Directory -Force $outDir | Out-Null
$iscc = Find-ISCC

Step "Compiling the installer for JBrowser $version (this takes a few minutes)"
& $iscc /Q "/DAppVersion=$version" "/DSourceDir=$Root\dist\JBrowser" "/DOutputDir=$outDir" "installer\JBrowser.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = Join-Path $outDir "JBrowser-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
$name = Split-Path -Leaf $setup
# sha256sum format: "<hash>  <file name>"
[System.IO.File]::WriteAllText("$setup.sha256", "$hash  $name`n")

$size = "{0:N0} MB" -f ((Get-Item $setup).Length / 1MB)
Write-Host "Installer: $setup ($size)" -ForegroundColor Green
Write-Host "SHA-256:   $hash" -ForegroundColor Green
