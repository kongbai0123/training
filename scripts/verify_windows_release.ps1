param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,
    [long]$MaximumBytes = 2147483648,
    [switch]$InternalQa
)

$ErrorActionPreference = "Stop"
$authenticodeCommand = Get-Command Get-AuthenticodeSignature -ErrorAction SilentlyContinue
if (-not $authenticodeCommand -and -not $InternalQa) {
    throw "Get-AuthenticodeSignature is unavailable. Run release validation in Windows PowerShell with Microsoft.PowerShell.Security installed."
}
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

$signature = if ($authenticodeCommand) { Get-AuthenticodeSignature -LiteralPath $artifact } else { $null }
if (-not $signature) {
    if (-not $InternalQa) {
        throw "Authenticode signature is required for publication: $artifact (unavailable)."
    }
    $signature = [pscustomobject]@{ Status = "Unavailable"; SignerCertificate = $null }
}
if ($signature.Status -ne "Valid") {
    if (-not $InternalQa) {
        throw "Authenticode signature is required for publication: $artifact ($($signature.Status))."
    }
    Write-Warning "Unsigned or unverifiable artifact accepted for isolated internal QA only: $artifact"
    $signatureLabel = if ($signature.Status -eq "Unavailable") { "UNVERIFIED_INTERNAL_QA" } else { "UNSIGNED_INTERNAL_QA" }
    $signer = ""
} else {
    $signatureLabel = "VALID"
    $signer = [string]$signature.SignerCertificate.Thumbprint
}

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$stream = [System.IO.File]::OpenRead($artifact)
try {
    $hashBytes = $sha256.ComputeHash($stream)
    $hash = ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
}
finally {
    $stream.Dispose()
    $sha256.Dispose()
}
Write-Output "ARTIFACT=$artifact"
Write-Output "BYTES=$($item.Length)"
Write-Output "SHA256=$hash"
Write-Output "AUTHENTICODE=$signatureLabel"
if ($signer) {
    Write-Output "SIGNER_THUMBPRINT=$signer"
}
