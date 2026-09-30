<#
.SYNOPSIS
    Code-signs JBrowser's programs (JBrowser.exe, the installer and its uninstaller) when a
    code-signing certificate is configured. Without one, it does nothing and builds stay unsigned.

.DESCRIPTION
    Windows SmartScreen shows "Windows protected your PC" for downloaded programs that are not
    signed by a certificate from a trusted certificate authority, and, for a new certificate, until
    it has earned reputation. tools\build_app.ps1 and tools\build_installer.ps1 call this script,
    so once a certificate is configured every build is signed. Configure it with environment
    variables (docs/SIGNING.md explains how to get a certificate):

      JBROWSER_SIGN_THUMBPRINT     The SHA-1 thumbprint of a code-signing certificate in
                                   Cert:\CurrentUser\My or Cert:\LocalMachine\My. Certificates on a
                                   hardware token or in a cloud HSM (Certum SimplySign, for example)
                                   appear there while their software is running.
      JBROWSER_SIGN_PFX            Or: the path to a .pfx file, with JBROWSER_SIGN_PFX_PASSWORD.
      JBROWSER_SIGN_AZURE          Or: the path to an Azure Artifact Signing (Trusted Signing)
                                   metadata.json, with JBROWSER_SIGN_AZURE_DLIB, the path to
                                   Azure.CodeSigning.Dlib.dll. Needs signtool.exe.
      JBROWSER_SIGN_TIMESTAMP      Optional: an RFC 3161 timestamp server. The default tries
                                   DigiCert, then Sectigo, then GlobalSign.
      JBROWSER_SIGN_TEST=1         Accept a certificate Windows doesn't trust (a self-signed one), to
                                   test the pipeline. master.ps1 refuses to publish such a build.

    signtool.exe (from the Windows SDK) is used when it is installed; otherwise PowerShell's
    Set-AuthenticodeSignature signs with the certificate or .pfx file. Every signature is
    timestamped, so it stays valid after the certificate expires, and checked afterwards.

.EXAMPLE
    .\tools\sign.ps1 -Status                          # how builds will be signed (empty: unsigned)
    .\tools\sign.ps1 C:\path\JBrowser-Setup-1.5.1.exe
#>
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Path,
    [switch]$Status
)
$ErrorActionPreference = "Stop"

$Description = "JBrowser"
$InfoUrl = "https://jbrowser.app/"
$TimestampServers = if ($env:JBROWSER_SIGN_TIMESTAMP) { @($env:JBROWSER_SIGN_TIMESTAMP) } else {
    @("http://timestamp.digicert.com", "http://timestamp.sectigo.com", "http://timestamp.globalsign.com/tsa/r6advanced1")
}
$Test = $env:JBROWSER_SIGN_TEST -eq "1"

function Find-SignTool {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $found = Get-ChildItem $kits -Directory -Filter "10.*" | Sort-Object { [version]$_.Name } -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($found) { return $found }
    }
    return $null
}

# The configured certificate: @{ Kind; Cert (X509Certificate2 or $null); Text }, or $null.
function Get-SigningConfig {
    if ($env:JBROWSER_SIGN_AZURE) {
        foreach ($p in @($env:JBROWSER_SIGN_AZURE, $env:JBROWSER_SIGN_AZURE_DLIB)) {
            if (-not $p -or -not (Test-Path $p)) { throw "Azure signing needs JBROWSER_SIGN_AZURE (metadata.json) and JBROWSER_SIGN_AZURE_DLIB; '$p' was not found." }
        }
        return @{ Kind = "azure"; Cert = $null; Text = "Azure Artifact Signing ($env:JBROWSER_SIGN_AZURE)" }
    }
    if ($env:JBROWSER_SIGN_THUMBPRINT) {
        $tp = ($env:JBROWSER_SIGN_THUMBPRINT -replace '[^0-9A-Fa-f]', '').ToUpper()
        $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My |
            Where-Object { $_.Thumbprint -eq $tp -and $_.HasPrivateKey } | Select-Object -First 1
        if (-not $cert) { throw "No certificate with a private key and thumbprint $tp in Cert:\CurrentUser\My or Cert:\LocalMachine\My." }
        return @{ Kind = "store"; Cert = $cert; Text = $cert.Subject }
    }
    if ($env:JBROWSER_SIGN_PFX) {
        if (-not (Test-Path $env:JBROWSER_SIGN_PFX)) { throw "JBROWSER_SIGN_PFX: $env:JBROWSER_SIGN_PFX was not found." }
        $flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
            (Resolve-Path $env:JBROWSER_SIGN_PFX).Path, $env:JBROWSER_SIGN_PFX_PASSWORD, $flags)
        return @{ Kind = "pfx"; Cert = $cert; Text = $cert.Subject }
    }
    return $null
}

function Invoke-SignTool($signtool, $config, $file, $server) {
    $argv = @("sign", "/fd", "SHA256", "/tr", $server, "/td", "SHA256", "/d", $Description, "/du", $InfoUrl)
    switch ($config.Kind) {
        "azure" { $argv += @("/dlib", $env:JBROWSER_SIGN_AZURE_DLIB, "/dmdf", $env:JBROWSER_SIGN_AZURE) }
        "store" { $argv += @("/sha1", $config.Cert.Thumbprint) }
        "pfx"   { $argv += @("/f", $env:JBROWSER_SIGN_PFX, "/p", $env:JBROWSER_SIGN_PFX_PASSWORD) }
    }
    & $signtool @argv $file | Out-Host
    return $LASTEXITCODE -eq 0
}

function Invoke-Authenticode($config, $file, $server) {
    $sig = Set-AuthenticodeSignature -FilePath $file -Certificate $config.Cert -HashAlgorithm SHA256 `
        -TimestampServer $server -IncludeChain NotRoot -ErrorAction Continue
    return $sig -and $sig.SignerCertificate -and $sig.TimeStamperCertificate
}

function Test-Signed($config, $file) {
    $sig = Get-AuthenticodeSignature -FilePath $file
    if ($sig.Status -eq "Valid") { return $true }
    # A self-signed test certificate isn't trusted, but the signature must still be there and ours.
    return $Test -and $config.Cert -and $sig.SignerCertificate -and $sig.SignerCertificate.Thumbprint -eq $config.Cert.Thumbprint
}

$config = Get-SigningConfig
if ($Status) {
    if ($config) {
        $tool = if (Find-SignTool) { "signtool" } elseif ($config.Kind -eq "azure") { "signtool (not installed!)" } else { "Set-AuthenticodeSignature" }
        $note = if ($Test) { ", TEST: untrusted certificates accepted" } else { "" }
        "$($config.Text) via $tool$note"
    }
    exit 0
}
if (-not $config) {
    Write-Host "    Not signing (no code-signing certificate configured; see tools\sign.ps1)" -ForegroundColor DarkGray
    exit 0
}
if (-not $Path) { throw "Give the files to sign." }

$signtool = Find-SignTool
if ($config.Kind -eq "azure" -and -not $signtool) {
    throw "Azure Artifact Signing needs signtool.exe: winget install Microsoft.WindowsSDK.10.0.26100"
}
if ($Test) { Write-Warning "JBROWSER_SIGN_TEST is set: untrusted certificates are accepted. Don't publish this build." }

foreach ($file in $Path) {
    $file = (Resolve-Path $file).Path
    $signed = $false
    foreach ($server in $TimestampServers) {   # timestamp servers are busy now and then
        for ($try = 1; $try -le 2 -and -not $signed; $try++) {
            $ok = if ($signtool) { Invoke-SignTool $signtool $config $file $server } else { Invoke-Authenticode $config $file $server }
            $signed = $ok -and (Test-Signed $config $file)
            if (-not $signed) { Start-Sleep -Seconds (3 * $try) }
        }
        if ($signed) { break }
    }
    if (-not $signed) {
        $sig = Get-AuthenticodeSignature -FilePath $file
        throw "Could not sign $file ($($sig.Status): $($sig.StatusMessage))"
    }
    Write-Host "    Signed $(Split-Path -Leaf $file) ($($config.Text))" -ForegroundColor Green
}
