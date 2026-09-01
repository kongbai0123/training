param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,
    [long]$MaximumBytes = 2147483648,
    [switch]$InternalQa
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Security -Force -ErrorAction Stop
$artifact = (Resolve-Path -LiteralPath $ArtifactPath).Path
$item = Get-Item -LiteralPath $artifact

if ($item.Extension -ne ".exe") {
    throw "Windows release artifact must be an EXE: $artifact"
}
if ($item.Length -le 0) {
    throw "Windows release artifact is empty: $artifact"
}
if ($item.Length -gt $MaximumBytes) {
    throw "Windows release artifact exceeds the $MaximumBytes byte limit: $($item.Length) bytes."
}

$signature = Get-AuthenticodeSignature -LiteralPath $artifact
if ($signature.Status -ne "Valid") {
    if (-not $InternalQa) {
        throw "Authenticode signature is required for publication: $artifact ($($signature.Status))."
    }
    Write-Warning "Unsigned artifact accepted for isolated internal QA only: $artifact"
    $signatureLabel = "UNSIGNED_INTERNAL_QA"
    $signer = ""
} else {
    $signatureLabel = "VALID"
    $signer = [string]$signature.SignerCertificate.Thumbprint
}

$hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "ARTIFACT=$artifact"
Write-Output "BYTES=$($item.Length)"
Write-Output "SHA256=$hash"
Write-Output "AUTHENTICODE=$signatureLabel"
if ($signer) {
    Write-Output "SIGNER_THUMBPRINT=$signer"
}
