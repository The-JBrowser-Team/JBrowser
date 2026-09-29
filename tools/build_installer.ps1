<#
.SYNOPSIS
    Builds the Windows installer: <dist>\installer\JBrowser-Setup-<version>.exe (+ .sha256).

.DESCRIPTION
    1. Builds the app with tools\build_app.ps1 (skip with -SkipAppBuild to reuse <dist>\JBrowser).
    2. Compiles installer\JBrowser.iss with Inno Setup 6 (ISCC.exe). When a code-signing
       certificate is configured (tools\sign.ps1), Setup and its uninstaller are signed.
    3. Writes JBrowser-Setup-<version>.exe.sha256, which the auto-updater uses to verify
       downloads. Both files are what tools\release.ps1 uploads to GitHub.

    <dist> is dist\ in the repository, or %LOCALAPPDATA%\JBrowser-build\dist when the repository
    is inside OneDrive (see tools\common.ps1).

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
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

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
$appDir = Join-Path $DistDir "JBrowser"
if (-not (Test-Path "$appDir\JBrowser.exe")) { throw "$appDir is missing. Build the app first." }

$version = (& $Py tools\version.py).Trim()
$outDir = Join-Path $DistDir "installer"
New-Item -ItemType Directory -Force $outDir | Out-Null
$iscc = Find-ISCC
$isccArgs = @("/Q", "/DAppVersion=$version", "/DSourceDir=$appDir", "/DOutputDir=$outDir")

# With a code-signing certificate, Inno Setup signs Setup and the uninstaller it contains by
# running tools\sign.ps1 on each ($q is a quote and $f the quoted file name, in Inno's syntax).
$signing = & (Join-Path $PSScriptRoot "sign.ps1") -Status
if ($signing) {
    $signScript = Join-Path $PSScriptRoot "sign.ps1"
    $isccArgs += @("/DSignSetup", ('/Sjbsign=powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' + $signScript + '$q $f'))
}

$how = if ($signing) { "signed with $signing" } else { "unsigned" }
Step "Compiling the installer for JBrowser $version, $how (this takes a few minutes)"
& $iscc @isccArgs "installer\JBrowser.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

# The checksum is taken last: signing changes the file.
$setup = Join-Path $outDir "JBrowser-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
$name = Split-Path -Leaf $setup
# sha256sum format: "<hash>  <file name>"
[System.IO.File]::WriteAllText("$setup.sha256", "$hash  $name`n")

$size = "{0:N0} MB" -f ((Get-Item $setup).Length / 1MB)
Write-Host "Installer: $setup ($size)" -ForegroundColor Green
Write-Host "SHA-256:   $hash" -ForegroundColor Green
