param(
    [Parameter(Mandatory = $true)]
    [string[]]$ArtifactPath,
    [string]$CertificateThumbprint = $env:VTS_SIGN_CERT_SHA1,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Security -Force -ErrorAction Stop

if ([string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    throw "VTS_SIGN_CERT_SHA1 or -CertificateThumbprint is required. Never use a self-signed certificate for a production release."
}
$thumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()

$certificate = $null
$certificateStore = $null
foreach ($store in @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")) {
    $candidate = Get-ChildItem -LiteralPath $store -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -eq $thumbprint -and $_.HasPrivateKey } |
        Select-Object -First 1
    if ($candidate) {
        $certificate = $candidate
        $certificateStore = $store
        break
    }
}
if (-not $certificate) {
    throw "A code-signing certificate with a private key was not found for thumbprint $thumbprint."
}
$now = Get-Date
if ($certificate.NotBefore -gt $now -or $certificate.NotAfter -lt $now) {
    throw "The code-signing certificate is outside its validity period."
}

$signTool = $env:VTS_SIGNTOOL_EXE
if ([string]::IsNullOrWhiteSpace($signTool)) {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        $signTool = $command.Source
    }
}
if ([string]::IsNullOrWhiteSpace($signTool)) {
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kitsRoot) {
        $signTool = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
}
if ([string]::IsNullOrWhiteSpace($signTool) -or -not (Test-Path -LiteralPath $signTool -PathType Leaf)) {
    throw "signtool.exe was not found. Install the Windows SDK or set VTS_SIGNTOOL_EXE."
}

foreach ($path in $ArtifactPath) {
    $resolved = (Resolve-Path -LiteralPath $path).Path
    $arguments = @("sign", "/sha1", $thumbprint, "/s", "My", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256")
    if ($certificateStore -eq "Cert:\LocalMachine\My") {
        $arguments += "/sm"
    }
    $arguments += $resolved
    & $signTool @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "signtool.exe failed for $resolved with exit code $LASTEXITCODE."
    }
    & (Join-Path $PSScriptRoot "verify_windows_release.ps1") -ArtifactPath $resolved
}
