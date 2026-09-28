# Installs, or updates, JBrowser from the latest release zip on GitHub.
#
#   irm https://raw.githubusercontent.com/The-JBrowser-Team/JBrowser/main/install.ps1 | iex
#
# It downloads JBrowser-<version>-<date>.zip, checks it and the installer inside against their
# SHA-256 files, then runs the installer. Run it again at any time to update. Set
# $env:JBROWSER_SILENT = "1" first to install without the setup wizard.
# Everything happens inside one function so that `iex` never closes your PowerShell window.

function Install-JBrowser {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"                     # the progress bar slows downloads a lot
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $repo = "The-JBrowser-Team/JBrowser"
    $headers = @{ "User-Agent" = "JBrowser-install"; "Accept" = "application/vnd.github+json" }

    Write-Host "Looking for the latest JBrowser release..." -ForegroundColor Cyan
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
    $zip = $release.assets | Where-Object { $_.name -match '^JBrowser-\d+\.\d+\.\d+-\d{4}-\d{2}-\d{2}\.zip$' } |
        Select-Object -First 1
    if (-not $zip) { throw "The latest release ($($release.tag_name)) has no zip. Download it from $($release.html_url)" }
    $version = $release.tag_name.TrimStart("v")

    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{7A42C612-1FC3-4E3F-9B05-30CBB1CCD542}_is1"
    $installed = (Get-ItemProperty $key -ErrorAction SilentlyContinue).DisplayVersion
    if ($installed -and ([version]$installed -ge [version]$version) -and -not $env:JBROWSER_FORCE) {
        Write-Host "JBrowser $installed is installed, which is the latest version. Nothing to do." -ForegroundColor Green
        return
    }

    $work = Join-Path $env:TEMP "JBrowser-Install"
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
    New-Item -ItemType Directory $work | Out-Null
    $zipPath = Join-Path $work $zip.name
    Write-Host ("Downloading {0} ({1:N0} MB)..." -f $zip.name, ($zip.size / 1MB)) -ForegroundColor Cyan
    Invoke-WebRequest $zip.browser_download_url -OutFile $zipPath -UseBasicParsing -Headers @{ "User-Agent" = "JBrowser-install" }

    $sumAsset = $release.assets | Where-Object { $_.name -eq "$($zip.name).sha256" } | Select-Object -First 1
    if ($sumAsset) {
        $expected = ((Invoke-WebRequest $sumAsset.browser_download_url -UseBasicParsing -Headers @{ "User-Agent" = "JBrowser-install" }).Content -split '\s+')[0]
        if ((Get-FileHash $zipPath -Algorithm SHA256).Hash -ne $expected) { throw "The download is damaged or has been changed (SHA-256 mismatch). Nothing was installed." }
    }

    Expand-Archive $zipPath -DestinationPath $work -Force
    $setup = Get-ChildItem $work -Filter "JBrowser-Setup-*.exe" | Select-Object -First 1
    if (-not $setup) { throw "The zip does not contain JBrowser-Setup-*.exe." }
    $expected = ((Get-Content "$($setup.FullName).sha256" -Raw) -split '\s+')[0]
    if ((Get-FileHash $setup.FullName -Algorithm SHA256).Hash -ne $expected) { throw "The installer failed its SHA-256 check. Nothing was installed." }

    $action = if ($installed) { "Updating JBrowser $installed to $version" } else { "Installing JBrowser $version" }
    Write-Host "$action..." -ForegroundColor Cyan
    Unblock-File $setup.FullName
    $arguments = if ($env:JBROWSER_SILENT) { @("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") } else { @() }
    $p = Start-Process $setup.FullName -ArgumentList $arguments -PassThru -Wait
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -eq 0) {
        Write-Host "Done. JBrowser $version is installed and will keep itself up to date." -ForegroundColor Green
    } else {
        Write-Host "Setup ended with code $($p.ExitCode) (cancelled or failed)." -ForegroundColor Yellow
    }
}

Install-JBrowser
