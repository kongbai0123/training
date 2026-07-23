param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [Parameter(Mandatory = $true)]
    [string[]]$Assets,
    [string]$Repository = "kongbai0123/training",
    [string]$NotesFile = "CHANGELOG.md"
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
    if (-not ($Assets | Where-Object { (Split-Path $_ -Leaf) -eq $updateName })) {
        throw "Missing required signed update asset: $updateName"
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
