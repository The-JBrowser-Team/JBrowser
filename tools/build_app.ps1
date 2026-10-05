<#
.SYNOPSIS
    Builds JBrowser.exe with PyInstaller.

.DESCRIPTION
    1. Makes sure .venv exists and is up to date (tools\update_deps.py) unless -SkipDeps.
    2. Regenerates the icon and the exe's version resource from jbrowser\__init__.py.
    3. Runs PyInstaller with JBrowser.spec (one-folder, recommended) or as a single file.
    4. Signs JBrowser.exe when a code-signing certificate is configured (tools\sign.ps1).

    Output: <dist>\JBrowser\JBrowser.exe  (or <dist>\JBrowser.exe with -OneFile), where <dist> is
    dist\ in the repository, or %LOCALAPPDATA%\JBrowser-build\dist when the repository is inside
    OneDrive (see tools\common.ps1).

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
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

if (-not $SkipDeps -or -not (Test-Path $Py)) {
    Step "Installing / checking dependencies (tools\update_deps.py)"
    if (Test-Path $Py) { & $Py tools\update_deps.py } else { & py -3.14 tools\update_deps.py }
    if ($LASTEXITCODE -ne 0) { throw "Dependency check failed" }
}

# A running copy from the output folder locks its files and makes PyInstaller fail half-way.
$running = Get-Process JBrowser -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$DistDir\*" }
if ($running) { throw "JBrowser is running from $DistDir. Close it, then build again." }

# Start from empty folders. PyInstaller clears them too, but if that silently fails (a file locked by
# an antivirus scan, for example) old files stay and end up in the installer.
Step "Clearing the previous build"
foreach ($old in @((Join-Path $DistDir "JBrowser"), (Join-Path $DistDir "JBrowser.exe"), (Join-Path $WorkDir "JBrowser"))) {
    for ($try = 0; $try -lt 10 -and (Test-Path $old); $try++) {   # scanners hold new files for a moment
        Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $old) { Start-Sleep -Milliseconds 700 }
    }
    if (Test-Path $old) { throw "Could not delete $old. Close anything using it (Explorer, JBrowser), then build again." }
}

Step "Rendering the icon and version resource"
& $Py tools\make_icon.py
& $Py tools\version.py --sync
$version = (& $Py tools\version.py).Trim()
$outputs = @("--distpath", $DistDir, "--workpath", $WorkDir)

if ($OneFile) {
    Step "Building single-file JBrowser.exe $version into $DistDir"
    # --specpath keeps the generated spec out of the repository (JBrowser.spec is hand-written),
    # which is also why every path below is absolute.
    & $Py -m PyInstaller main.py --noconfirm --clean --onefile --windowed @outputs --specpath $WorkDir `
        --name JBrowser --icon "$Root\assets\jbrowser.ico" --version-file "$Root\tools\version_info.txt" `
        --add-data "$Root\assets\jbrowser.ico;assets" --add-data "$Root\assets\jbrowser.png;assets" `
        --add-data "$Root\assets\sounds\intro.wav;assets\sounds" --add-data "$Root\assets\sounds\click.wav;assets\sounds" `
        --collect-submodules jbrowser `
        --hidden-import PyQt6.QtWebChannel --hidden-import PyQt6.QtPrintSupport `
        --hidden-import PyQt6.QtNetwork --hidden-import PyQt6.QtMultimedia `
        --exclude-module tkinter --exclude-module PyQt5 --noupx
    $out = Join-Path $DistDir "JBrowser.exe"
} else {
    Step "Building JBrowser $version (one-folder) into $DistDir"
    & $Py -m PyInstaller JBrowser.spec --noconfirm --clean @outputs
    $out = Join-Path $DistDir "JBrowser\JBrowser.exe"
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) { throw "PyInstaller build failed" }

Step "Code signing"
& (Join-Path $PSScriptRoot "sign.ps1") $out
Write-Host "Built $out ($version)" -ForegroundColor Green
