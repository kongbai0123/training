param(
    [ValidateSet("Installed", "Portable")]
    [string]$Mode = "Installed",
    [int]$Port = 18105,
    [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exe = if ($ExePath) {
    [System.IO.Path]::GetFullPath($ExePath)
} else {
    Join-Path $repoRoot "dist\VisionTrainingStudio\VisionTrainingStudio.exe"
}
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Dist executable not found: $exe. Run scripts\package.bat first."
}

$packageRoot = Split-Path -Parent $exe
$portableMarker = Join-Path $packageRoot "portable.mode"
$userDirectoryNames = @("projects", "models", "logs", "config", "licenses", "cache", "tmp", "components", "exports")
$packageUserDirectories = @($userDirectoryNames | ForEach-Object { Join-Path $packageRoot $_ })
foreach ($path in $packageUserDirectories) {
    if (Test-Path -LiteralPath $path) {
        throw "Package is not factory clean before smoke: $path"
    }
}
if ($Mode -eq "Installed" -and (Test-Path -LiteralPath $portableMarker)) {
    throw "Unexpected portable.mode marker in the installed dist folder."
}
$portableMarkerPreexisting = Test-Path -LiteralPath $portableMarker

$smokeRoot = Join-Path $repoRoot ("tmp\dist-smoke-" + $Mode.ToLowerInvariant())
if (Test-Path -LiteralPath $smokeRoot) {
    Remove-Item -LiteralPath $smokeRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null

$environmentNames = @(
    "LOCALAPPDATA", "VTS_USER_DATA_DIR", "VTS_PROJECTS_DIR",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"
)
$savedEnvironment = @{}
foreach ($name in $environmentNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$proc = $null
try {
    Remove-Item Env:VTS_USER_DATA_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:VTS_PROJECTS_DIR -ErrorAction SilentlyContinue
    $env:HTTP_PROXY = "http://127.0.0.1:9"
    $env:HTTPS_PROXY = "http://127.0.0.1:9"
    $env:ALL_PROXY = "http://127.0.0.1:9"
    $env:NO_PROXY = "127.0.0.1,localhost,::1"

    if ($Mode -eq "Portable") {
        if (-not $portableMarkerPreexisting) {
            New-Item -ItemType File -Path $portableMarker -Force | Out-Null
        }
        $expectedUserData = $packageRoot
    } else {
        $env:LOCALAPPDATA = $smokeRoot
        $expectedUserData = Join-Path $smokeRoot "VisionTrainingStudio"
    }
    $expectedProjects = (Join-Path $expectedUserData "projects").Replace("\", "/")

    Write-Host "[Vision Training Studio] Starting $Mode offline smoke on port $Port..."
    $proc = Start-Process -FilePath $exe -ArgumentList @(
        "--port", $Port, "--env", "production", "--shell", "none"
    ) -PassThru -WindowStyle Hidden

    $health = $null
    $version = $null
    $capabilities = $null
    $projects = $null
    $catalog = $null
    $labelme = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $baseUrl = "http://127.0.0.1:$Port"
            $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 2
            $version = Invoke-RestMethod -Uri "$baseUrl/api/version" -TimeoutSec 2
            $capabilities = Invoke-RestMethod -Uri "$baseUrl/api/system/capabilities" -TimeoutSec 2
            $projects = Invoke-RestMethod -Uri "$baseUrl/api/projects" -TimeoutSec 2
            $catalog = Invoke-RestMethod -Uri "$baseUrl/api/models/catalog?usage=all" -TimeoutSec 3
            $labelme = Invoke-RestMethod -Uri "$baseUrl/api/components/labelme" -TimeoutSec 2
            break
        } catch {
            $health = $null
        }
    }

    if ($null -eq $health) { throw "Health endpoint did not respond." }
    if ($null -eq $version) { throw "Version endpoint did not respond." }
    if ($null -eq $capabilities) { throw "Capabilities endpoint did not respond." }
    if ($health.directories.projects_dir -ne $expectedProjects) {
        throw "Packaged projects path is not isolated: $($health.directories.projects_dir)"
    }
    if (@($projects).Count -ne 0) {
        throw "Factory-clean package exposed $(@($projects).Count) project(s)."
    }
    if (-not ($capabilities.runtime.opencv -like "5.*")) {
        throw "Unexpected OpenCV runtime: $($capabilities.runtime.opencv)"
    }
    if ($catalog.summary.total -lt 1) {
        throw "Local model catalog is unavailable in offline mode."
    }
    if ($labelme.component_id -ne "labelme") {
        throw "Local LabelMe component status is unavailable in offline mode."
    }

    $modelsDir = Join-Path $expectedUserData "models"
    $downloadedModels = if (Test-Path -LiteralPath $modelsDir) {
        @(Get-ChildItem -LiteralPath $modelsDir -File -Recurse -ErrorAction SilentlyContinue)
    } else { @() }
    if ($downloadedModels.Count -ne 0) {
        throw "Offline first-run smoke downloaded $($downloadedModels.Count) model file(s) without consent."
    }

    $packageProcesses = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($packageRoot, [System.StringComparison]::OrdinalIgnoreCase)
    })
    $packageProcessIds = @($packageProcesses | Select-Object -ExpandProperty ProcessId)
    $externalConnections = if ($packageProcessIds.Count) {
        @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object {
            $packageProcessIds -contains $_.OwningProcess -and
            $_.RemoteAddress -notin @("127.0.0.1", "::1")
        })
    } else { @() }
    if ($externalConnections.Count -ne 0) {
        throw "Packaged smoke opened $($externalConnections.Count) external connection(s)."
    }

    Write-Host ("health=" + ($health | ConvertTo-Json -Compress))
    Write-Host ("version=" + ($version | ConvertTo-Json -Compress))
    Write-Host "mode=$Mode"
    Write-Host "opencv=$($capabilities.runtime.opencv)"
    Write-Host "factory_projects=$(@($projects).Count)"
    Write-Host "automatic_model_downloads=$($downloadedModels.Count)"
    Write-Host "external_connections=$($externalConnections.Count)"
} finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($packageRoot, [System.StringComparison]::OrdinalIgnoreCase)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 700

    if (-not $portableMarkerPreexisting -and (Test-Path -LiteralPath $portableMarker)) {
        Remove-Item -LiteralPath $portableMarker -Force
    }
    foreach ($path in $packageUserDirectories) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
    foreach ($name in $environmentNames) {
        $value = $savedEnvironment[$name]
        if ($null -eq $value) {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        } else {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$remainingProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith($packageRoot, [System.StringComparison]::OrdinalIgnoreCase)
})
if ($remainingProcesses.Count -ne 0) {
    throw "Packaged processes remained after smoke: $($remainingProcesses.ProcessId -join ',')"
}
foreach ($path in $packageUserDirectories) {
    if (Test-Path -LiteralPath $path) {
        throw "Smoke left user data inside the package: $path"
    }
}

Write-Host "[Vision Training Studio] $Mode offline smoke passed."
