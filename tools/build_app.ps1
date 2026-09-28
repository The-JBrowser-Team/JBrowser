<#
.SYNOPSIS
    Builds JBrowser.exe with PyInstaller.

.DESCRIPTION
    1. Makes sure .venv exists and is up to date (tools\update_deps.py) unless -SkipDeps.
    2. Regenerates the icon and the exe's version resource from jbrowser\__init__.py.
    3. Runs PyInstaller with JBrowser.spec (one-folder, recommended) or as a single file.

    Output: dist\JBrowser\JBrowser.exe  (or dist\JBrowser.exe with -OneFile)

.EXAMPLE
    .\tools\build_app.ps1
    .\tools\build_app.ps1 -SkipDeps
    .\tools\build_app.ps1 -OneFile
#>
param(
    [switch]$OneFile,
    [switch]$SkipDeps
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

if (-not $SkipDeps -or -not (Test-Path $py)) {
    Step "Installing / checking dependencies (tools\update_deps.py)"
    $bootstrap = if (Test-Path $py) { $py } else { "py" }
    if ($bootstrap -eq "py") { & py -3.14 tools\update_deps.py } else { & $py tools\update_deps.py }
    if ($LASTEXITCODE -ne 0) { throw "Dependency check failed" }
}

# A running copy from dist\ locks its files and makes PyInstaller fail half-way.
$running = Get-Process JBrowser -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root\dist\*" }
if ($running) { throw "JBrowser is running from $Root\dist. Close it, then build again." }

Step "Rendering the icon and version resource"
& $py tools\make_icon.py
& $py tools\version.py --sync
$version = (& $py tools\version.py).Trim()

if ($OneFile) {
    Step "Building single-file JBrowser.exe $version"
    & $py -m PyInstaller main.py --noconfirm --clean --onefile --windowed `
        --name JBrowser --icon assets\jbrowser.ico --version-file tools\version_info.txt `
        --add-data "assets\jbrowser.ico;assets" --add-data "assets\jbrowser.png;assets" `
        --add-data "assets\sounds\intro.wav;assets\sounds" --add-data "assets\sounds\click.wav;assets\sounds" `
        --collect-submodules jbrowser `
        --hidden-import PyQt6.QtWebChannel --hidden-import PyQt6.QtPrintSupport `
        --hidden-import PyQt6.QtNetwork --hidden-import PyQt6.QtMultimedia --hidden-import pywinstyles `
        --exclude-module tkinter --exclude-module PyQt5 --noupx
    $out = "dist\JBrowser.exe"
} else {
    Step "Building JBrowser $version (one-folder)"
    & $py -m PyInstaller JBrowser.spec --noconfirm --clean
    $out = "dist\JBrowser\JBrowser.exe"
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) { throw "PyInstaller build failed" }
Write-Host "Built $out ($version)" -ForegroundColor Green
