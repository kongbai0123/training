[CmdletBinding()]
param(
    [string]$InstallerPath = "",
    [string]$ManifestPath = "",
    [string]$Repository = "kongbai0123/training",
    [string]$ReleaseTag = "personal-v0.2.0-20260902"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$ManifestPath = if ($ManifestPath) { $ManifestPath } else { Join-Path $root "bootstrap-manifest.json" }
$version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw -Encoding UTF8).Trim()
if (-not $InstallerPath) {
    $InstallerPath = Join-Path $root "installer\output\VisionTrainingStudio_Setup_$version.exe"
}
$installer = Get-Item -LiteralPath $InstallerPath -ErrorAction Stop
if ($installer.Extension -ne ".exe" -or $installer.Length -le 0) {
    throw "InstallerPath must identify a non-empty EXE."
}

$algorithm = [System.Security.Cryptography.SHA256]::Create()
$stream = [System.IO.File]::OpenRead($installer.FullName)
try {
    $hashBytes = $algorithm.ComputeHash($stream)
    $hash = ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
}
finally {
    $stream.Dispose()
    $algorithm.Dispose()
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$manifest.version = $version
$manifest.package_id = $ReleaseTag
$manifest.installer.file_name = $installer.Name
$manifest.installer.url = "https://github.com/$Repository/releases/download/$ReleaseTag/$($installer.Name)"
$manifest.installer.bytes = $installer.Length
$manifest.installer.sha256 = $hash

$resolvedManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$temporaryPath = "$resolvedManifestPath.tmp.$PID"
$replacementBackup = "$resolvedManifestPath.bak.$PID"
$utf8 = New-Object System.Text.UTF8Encoding($false)
try {
    [System.IO.File]::WriteAllText($temporaryPath, ($manifest | ConvertTo-Json -Depth 6) + [Environment]::NewLine, $utf8)
    [System.IO.File]::Replace($temporaryPath, $resolvedManifestPath, $replacementBackup, $true)
}
finally {
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
    if (Test-Path -LiteralPath $replacementBackup) {
        Remove-Item -LiteralPath $replacementBackup -Force
    }
}

$checksumPath = Join-Path $installer.DirectoryName "SHA256SUMS.txt"
[System.IO.File]::WriteAllText($checksumPath, "$hash  $($installer.Name)$([Environment]::NewLine)", $utf8)
Write-Output "MANIFEST=$ManifestPath"
Write-Output "INSTALLER=$($installer.FullName)"
Write-Output "BYTES=$($installer.Length)"
Write-Output "SHA256=$hash"
Write-Output "CHECKSUM=$checksumPath"
