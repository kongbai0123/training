param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [Parameter(Mandatory = $true)]
    [string[]]$Assets,
    [string]$Repository = "kongbai0123/training",
    [string]$NotesFile = "CHANGELOG.md",
    [string]$UpdaterBootstrapVersion = "0.1.4"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    if ($Tag -notmatch '^v\d+\.\d+\.\d+$') {
        throw "Tag must use vMAJOR.MINOR.PATCH."
    }
    $version = (Get-Content VERSION -Raw).Trim()
    $versionInfo = Get-Content version.json -Raw | ConvertFrom-Json
    if ($Tag -ne "v$version" -or $versionInfo.app_version -ne $version) {
        throw "Tag, VERSION, and version.json must match."
    }
    if (git status --porcelain) {
        throw "Working tree must be clean before creating a release draft."
    }
    gh auth status | Out-Null
    foreach ($asset in $Assets) {
        if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
            throw "Release asset not found: $asset"
        }
    }
    $updateName = "VisionTrainingStudio_Update_${version}_runtime-$($versionInfo.runtime_version).vtsupdate"
    $setupName = "VisionTrainingStudio_Setup_${version}.exe"
    $hasUpdate = [bool]($Assets | Where-Object { (Split-Path $_ -Leaf) -eq $updateName })
    $hasSetup = [bool]($Assets | Where-Object { (Split-Path $_ -Leaf) -eq $setupName })
    $hasChecksums = [bool]($Assets | Where-Object { (Split-Path $_ -Leaf) -match 'SHA256SUMS\.txt$' })
    if ($version -eq $UpdaterBootstrapVersion -and -not $hasSetup) {
        throw "Updater bootstrap releases must include the full installer: $setupName"
    }
    if ($version -ne $UpdaterBootstrapVersion -and -not $hasUpdate) {
        throw "Missing required signed update asset: $updateName"
    }
    if (-not $hasChecksums) {
        throw "Every release must include a SHA256SUMS.txt asset."
    }
    if (-not (git tag --list $Tag)) {
        git tag -a $Tag -m "Vision Training Studio $version"
    }
    git push origin $Tag
    gh release create $Tag $Assets --repo $Repository --draft --verify-tag --title "Vision Training Studio $version" --notes-file $NotesFile
    Write-Host "Draft release created. Verify every asset before publishing it as an immutable release."
}
finally {
    Pop-Location
}
