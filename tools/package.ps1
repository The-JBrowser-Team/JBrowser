<#
.SYNOPSIS
    Packages the built installer as JBrowser-<version>-<yyyy-MM-dd>.zip (+ .zip.sha256).

.DESCRIPTION
    The zip holds JBrowser-Setup-<version>.exe, its .sha256, LICENSE and INSTALL.txt. INSTALL.txt
    explains SmartScreen's warning when the installer isn't signed, or names the publisher when it
    is. master.ps1 runs this after building, and so does the release-build workflow on GitHub
    Actions (.github/workflows/release-build.yml), so both make the same zip.

    Writes to distribution\ in the repository (or -OutDir) and prints the zip's path.

.EXAMPLE
    .\tools\package.ps1
    .\tools\package.ps1 -OutDir C:\temp\out
#>
param(
    [string]$OutDir
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

$ver = (& $Py tools\version.py).Trim()
$setup = Join-Path $DistDir "installer\JBrowser-Setup-$ver.exe"
if (-not (Test-Path $setup) -or -not (Test-Path "$setup.sha256")) {
    throw "No installer for $ver in $DistDir\installer. Build it first (tools\build_installer.ps1)."
}
$date = Get-Date -Format "yyyy-MM-dd"
$distribution = if ($OutDir) { $OutDir } else { Join-Path $Root "distribution" }
$zipName = "JBrowser-$ver-$date.zip"
$zip = Join-Path $distribution $zipName
Step "Packaging $zipName"
New-Item -ItemType Directory -Force $distribution | Out-Null
$stage = Join-Path $WorkDir "package"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item $setup, "$setup.sha256", (Join-Path $Root "LICENSE") $stage

$signature = Get-AuthenticodeSignature $setup
$smartScreen = if ($signature.Status -eq "Valid") {
    $publisher = $signature.SignerCertificate.GetNameInfo("SimpleName", $false)
    "  2. Windows shows the publisher as `"$publisher`". If SmartScreen still warns (a new version can take`r`n" +
    "     a little while to be recognised), choose `"More info`", check the publisher, then `"Run anyway`"."
} else {
    "  2. If Windows SmartScreen warns about an unrecognised app, choose `"More info`", then `"Run anyway`"`r`n" +
    "     (this installer is not code-signed)."
}
$installText = @"
JBrowser $ver ($date)
Welcome to the internet - again.

To install or update:
  1. Run JBrowser-Setup-$ver.exe.
$smartScreen
  3. Follow the steps. No administrator rights are needed. Your data is kept when updating.

Check the installer (optional), in PowerShell in this folder:
  (Get-FileHash .\JBrowser-Setup-$ver.exe -Algorithm SHA256).Hash
It must match the first word in JBrowser-Setup-$ver.exe.sha256.

Once installed, JBrowser updates itself from GitHub. Uninstall from Settings > Apps > Installed apps.
Source, help and release notes: https://github.com/The-JBrowser-Team/JBrowser
JBrowser is free software under the GNU General Public License v3 (see LICENSE).
"@
[System.IO.File]::WriteAllText((Join-Path $stage "INSTALL.txt"), ($installText -replace "`r?`n", "`r`n"))
if (Test-Path $zip) { Remove-Item $zip -Force -Confirm:$false }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText("$zip.sha256", "$zipHash  $zipName`n")
Remove-Item $stage -Recurse -Force -Confirm:$false
$zip
