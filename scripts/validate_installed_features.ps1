param(
    [Parameter(Mandatory = $true)]
    [string]$AppExe,
    [int]$Port = 18116
)

$ErrorActionPreference = "Stop"
$resolvedExe = (Resolve-Path -LiteralPath $AppExe).Path
$baseUrl = "http://127.0.0.1:$Port"
$process = Start-Process `
    -FilePath $resolvedExe `
    -ArgumentList @("--host", "127.0.0.1", "--port", "$Port", "--shell", "none") `
    -WindowStyle Hidden `
    -PassThru

try {
    $deadline = (Get-Date).AddSeconds(60)
    $version = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $version = Invoke-RestMethod -Uri "$baseUrl/api/version" -TimeoutSec 2
            break
        }
        catch {
            Start-Sleep -Milliseconds 700
        }
    }
    if ($null -eq $version) {
        throw "Installed API startup timed out."
    }
    $bootstrap = Invoke-RestMethod -Uri "$baseUrl/api/bootstrap" -TimeoutSec 5
    if ([string]::IsNullOrWhiteSpace([string]$bootstrap.token)) {
        throw "Installed bootstrap did not return a local session token."
    }
    $headers = @{ "X-VTS-Token" = [string]$bootstrap.token }

    $projectId = "installed_acceptance_013_$(Get-Date -Format 'yyyyMMddHHmmss')"
    $chatBody = @{
        message = "Explain the current project status"
        locale = "zh-TW"
        conversation_state = @()
    } | ConvertTo-Json -Depth 5
    $chat = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/project-assistant/chat?project_id=$projectId" `
        -ContentType "application/json; charset=utf-8" `
        -Headers $headers `
        -Body $chatBody

    $filename = "VTS_0.1.3_installed_download_acceptance_$(Get-Date -Format 'yyyyMMdd_HHmmss').svg"
    $svg = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><text x="4" y="24">VTS 0.1.3</text></svg>'
    $downloadBody = @{
        filename = $filename
        content = $svg
    } | ConvertTo-Json -Compress
    $download = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/downloads/text" `
        -ContentType "application/json; charset=utf-8" `
        -Headers $headers `
        -Body $downloadBody

    $savedPath = [System.IO.Path]::GetFullPath([string]$download.saved_path)
    if (-not (Test-Path -LiteralPath $savedPath)) {
        throw "Downloaded file is missing: $savedPath"
    }
    if ($savedPath -match "\\AppData\\") {
        throw "Download was incorrectly saved under AppData: $savedPath"
    }
    if ([string]::IsNullOrWhiteSpace([string]$chat.answer)) {
        throw "Assistant response was empty."
    }
    if ([string]$chat.answer -match "No project knowledge sources|sync project artifacts first") {
        throw "Assistant response remained in English: $($chat.answer)"
    }

    Write-Output "VERSION=$($version.version)"
    Write-Output "ASSISTANT_ANSWER=$($chat.answer)"
    Write-Output "ASSISTANT_SOURCES=$(@($chat.sources).Count)"
    Write-Output "DOWNLOAD_SAVED=$savedPath"
    Write-Output "DOWNLOAD_BYTES=$((Get-Item -LiteralPath $savedPath).Length)"
}
finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}
