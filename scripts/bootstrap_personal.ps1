[CmdletBinding()]
param(
    [string]$ManifestPath = "",
    [string]$BootstrapRoot = "",
    [string]$InstallRoot = "",
    [switch]$DownloadOnly,
    [switch]$NoLaunch,
    [switch]$AllowInsecureDownload
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"
$bootstrapMutex = $null
$bootstrapMutexOwned = $false

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

function Test-InstallerPayload {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$ExpectedBytes,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne $ExpectedBytes) {
        return $false
    }
    return (Get-Sha256 -Path $Path) -eq $ExpectedSha256.ToLowerInvariant()
}

function Save-JsonAtomically {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = "$Path.tmp.$PID"
    $replacementBackup = "$Path.bak.$PID"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth 6
        [System.IO.File]::WriteAllText($temporaryPath, $json, $utf8)
        if (Test-Path -LiteralPath $Path) {
            [System.IO.File]::Replace($temporaryPath, $Path, $replacementBackup, $true)
        }
        else {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
        if (Test-Path -LiteralPath $replacementBackup) {
            Remove-Item -LiteralPath $replacementBackup -Force
        }
    }
}

function Get-BootstrapState {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-InstalledExecutable {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [string]$ExplicitInstallRoot
    )

    $relativeExecutable = [string]$Manifest.install.relative_executable
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($ExplicitInstallRoot) {
        $candidates.Add((Join-Path $ExplicitInstallRoot $relativeExecutable))
    }

    $registryAppId = [string]$Manifest.install.registry_app_id
    foreach ($registryRoot in @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )) {
        $key = Join-Path $registryRoot $registryAppId
        try {
            $installLocation = [string](Get-ItemPropertyValue -LiteralPath $key -Name "InstallLocation" -ErrorAction Stop)
            if ($installLocation) {
                $candidates.Add((Join-Path $installLocation $relativeExecutable))
            }
        }
        catch {
            # The product may not have been installed on this machine yet.
        }
    }

    if ($env:LOCALAPPDATA) {
        $candidates.Add((Join-Path (Join-Path $env:LOCALAPPDATA ([string]$Manifest.install.default_relative_dir)) $relativeExecutable))
    }
    if ($env:ProgramFiles) {
        $candidates.Add((Join-Path (Join-Path $env:ProgramFiles "VisionTrainingStudio") $relativeExecutable))
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return $null
}

function Test-InstalledPackage {
    param(
        [string]$ExecutablePath,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion
    )

    if (-not $ExecutablePath -or -not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
        return $false
    }
    $versionPath = Join-Path (Split-Path -Parent $ExecutablePath) "_internal\version.json"
    if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
        return $false
    }
    try {
        $versionInfo = Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return ([string]$versionInfo.version) -eq $ExpectedVersion
    }
    catch {
        return $false
    }
}

function Receive-FileOnce {
    param(
        [Parameter(Mandatory = $true)][System.Uri]$Uri,
        [Parameter(Mandatory = $true)][string]$PartialPath,
        [Parameter(Mandatory = $true)][long]$ExpectedBytes
    )

    $existingBytes = 0L
    if (Test-Path -LiteralPath $PartialPath -PathType Leaf) {
        $existingBytes = (Get-Item -LiteralPath $PartialPath).Length
        if ($existingBytes -gt $ExpectedBytes) {
            Remove-Item -LiteralPath $PartialPath -Force
            $existingBytes = 0L
        }
    }
    if ($existingBytes -eq $ExpectedBytes) {
        return
    }

    $request = [System.Net.HttpWebRequest]::Create($Uri)
    $request.AllowAutoRedirect = $true
    $request.MaximumAutomaticRedirections = 10
    $request.UserAgent = "VisionTrainingStudio-PersonalBootstrap/1.0"
    $request.Timeout = 60000
    $request.ReadWriteTimeout = 60000
    if ($existingBytes -gt 0) {
        $request.AddRange($existingBytes)
    }

    $response = $request.GetResponse()
    $responseStream = $null
    $fileStream = $null
    try {
        $statusCode = [int]$response.StatusCode
        $append = $existingBytes -gt 0 -and $statusCode -eq 206
        if ($append) {
            $contentRange = [string]$response.Headers["Content-Range"]
            if ($contentRange -notmatch "^bytes\s+(\d+)-" -or [long]$Matches[1] -ne $existingBytes) {
                throw "The download server returned an invalid resume range."
            }
        }
        if (-not $append) {
            $existingBytes = 0L
        }
        $mode = if ($append) { [System.IO.FileMode]::Append } else { [System.IO.FileMode]::Create }
        $fileStream = New-Object System.IO.FileStream(
            $PartialPath,
            $mode,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $responseStream = $response.GetResponseStream()
        $buffer = New-Object byte[] (1024 * 1024)
        $receivedBytes = $existingBytes
        while (($count = $responseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if (($receivedBytes + $count) -gt $ExpectedBytes) {
                throw "The download exceeded the expected installer size."
            }
            $fileStream.Write($buffer, 0, $count)
            $receivedBytes += $count
            if ($ExpectedBytes -gt 0) {
                $percent = [Math]::Min(100, [int](($receivedBytes * 100L) / $ExpectedBytes))
                Write-Progress -Activity "Downloading Vision Training Studio" -Status "$percent%" -PercentComplete $percent
            }
        }
        $fileStream.Flush()
    }
    finally {
        Write-Progress -Activity "Downloading Vision Training Studio" -Completed
        if ($responseStream) { $responseStream.Dispose() }
        if ($fileStream) { $fileStream.Dispose() }
        $response.Dispose()
    }
}

function Get-VerifiedInstaller {
    param(
        [Parameter(Mandatory = $true)][System.Uri]$Uri,
        [Parameter(Mandatory = $true)][string]$DownloadDirectory,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][long]$ExpectedBytes,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null
    $installerPath = Join-Path $DownloadDirectory $FileName
    $partialPath = "$installerPath.part"
    if (Test-InstallerPayload -Path $installerPath -ExpectedBytes $ExpectedBytes -ExpectedSha256 $ExpectedSha256) {
        return $installerPath
    }
    if (Test-Path -LiteralPath $installerPath) {
        Remove-Item -LiteralPath $installerPath -Force
    }

    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "[Vision Training Studio] Downloading installer (attempt $attempt of 3)..."
            Receive-FileOnce -Uri $Uri -PartialPath $partialPath -ExpectedBytes $ExpectedBytes
            if (-not (Test-InstallerPayload -Path $partialPath -ExpectedBytes $ExpectedBytes -ExpectedSha256 $ExpectedSha256)) {
                if (Test-Path -LiteralPath $partialPath) {
                    Remove-Item -LiteralPath $partialPath -Force
                }
                throw "The downloaded installer did not pass the size and SHA-256 check."
            }
            Move-Item -LiteralPath $partialPath -Destination $installerPath -Force
            return $installerPath
        }
        catch {
            $lastError = $_.Exception
            if ($attempt -lt 3) {
                Write-Warning "Download was interrupted. Retrying without using an incomplete installer."
                Start-Sleep -Seconds 2
            }
        }
    }
    throw "Unable to download a verified installer after 3 attempts: $($lastError.Message)"
}

try {
    $bootstrapMutex = New-Object System.Threading.Mutex($false, "Local\VisionTrainingStudioPersonalBootstrap")
    try {
        $bootstrapMutexOwned = $bootstrapMutex.WaitOne(0, $false)
    }
    catch [System.Threading.AbandonedMutexException] {
        $bootstrapMutexOwned = $true
    }
    if (-not $bootstrapMutexOwned) {
        Write-Host "[Vision Training Studio] Startup is already running."
        exit 0
    }

    if (-not $ManifestPath) {
        $ManifestPath = Join-Path (Split-Path -Parent $PSScriptRoot) "bootstrap-manifest.json"
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "Bootstrap manifest was not found: $ManifestPath"
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$manifest.schema_version -ne 1) {
        throw "Unsupported bootstrap manifest schema."
    }
    if (-not ([string]$manifest.package_id)) {
        throw "The bootstrap manifest does not contain a package_id."
    }
    $installerBytes = [long]$manifest.installer.bytes
    $installerSha256 = ([string]$manifest.installer.sha256).ToLowerInvariant()
    $installerFileName = [string]$manifest.installer.file_name
    if ($installerBytes -le 0 -or $installerSha256 -notmatch "^[a-f0-9]{64}$") {
        throw "The bootstrap manifest contains an invalid installer identity."
    }
    if ([System.IO.Path]::GetFileName($installerFileName) -ne $installerFileName -or [System.IO.Path]::GetExtension($installerFileName) -ne ".exe") {
        throw "The bootstrap manifest contains an invalid installer filename."
    }
    $installerUri = [System.Uri]([string]$manifest.installer.url)
    if ($installerUri.Scheme -ne "https" -and -not $AllowInsecureDownload) {
        throw "The installer URL must use HTTPS."
    }
    if (-not $AllowInsecureDownload) {
        $expectedPrefix = "/kongbai0123/training/releases/download/"
        if ($installerUri.Host -ne "github.com" -or -not $installerUri.AbsolutePath.StartsWith($expectedPrefix, [System.StringComparison]::Ordinal)) {
            throw "The installer URL must identify the pinned Vision Training Studio GitHub Release."
        }
        $urlFileName = [System.Uri]::UnescapeDataString([System.IO.Path]::GetFileName($installerUri.AbsolutePath))
        if ($urlFileName -ne $installerFileName) {
            throw "The installer URL and filename do not match."
        }
    }

    if (-not $BootstrapRoot) {
        if (-not $env:LOCALAPPDATA) {
            throw "LOCALAPPDATA is unavailable."
        }
        $BootstrapRoot = Join-Path $env:LOCALAPPDATA "VisionTrainingStudio\bootstrap"
    }
    $BootstrapRoot = [System.IO.Path]::GetFullPath($BootstrapRoot)
    $statePath = Join-Path $BootstrapRoot "bootstrap-state.json"
    $state = Get-BootstrapState -Path $statePath
    $installedExecutable = $null
    if ($state -and ($state.PSObject.Properties.Name -contains "executable_path")) {
        $stateExecutable = [string]$state.executable_path
        if ($stateExecutable -and (Test-Path -LiteralPath $stateExecutable -PathType Leaf)) {
            $installedExecutable = [System.IO.Path]::GetFullPath($stateExecutable)
        }
    }
    if (-not $installedExecutable) {
        $installedExecutable = Get-InstalledExecutable -Manifest $manifest -ExplicitInstallRoot $InstallRoot
    }

    $stateMatches = $false
    if ($state -and $installedExecutable) {
        $stateMatches = (
            [string]$state.package_id -eq [string]$manifest.package_id -and
            [string]$state.installer_sha256 -eq $installerSha256
        )
    }
    if ($stateMatches -and (Test-InstalledPackage -ExecutablePath $installedExecutable -ExpectedVersion ([string]$manifest.version))) {
        Write-Host "[Vision Training Studio] Starting the installed application..."
        if (-not $NoLaunch) {
            Start-Process -FilePath $installedExecutable -WorkingDirectory (Split-Path -Parent $installedExecutable) | Out-Null
        }
        exit 0
    }

    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
    $downloadDirectory = Join-Path $BootstrapRoot "downloads"
    $installerPath = Get-VerifiedInstaller `
        -Uri $installerUri `
        -DownloadDirectory $downloadDirectory `
        -FileName $installerFileName `
        -ExpectedBytes $installerBytes `
        -ExpectedSha256 $installerSha256

    if ($DownloadOnly) {
        Write-Output "BOOTSTRAP_INSTALLER=$installerPath"
        exit 0
    }

    Write-Host "[Vision Training Studio] Installing the personal local application..."
    if (Get-Process -Name "VisionTrainingStudio" -ErrorAction SilentlyContinue) {
        throw "Vision Training Studio is already open. Close it before installing this package, then run the launcher again."
    }
    if (-not $InstallRoot) {
        if (-not $env:LOCALAPPDATA) {
            throw "LOCALAPPDATA is unavailable."
        }
        $InstallRoot = Join-Path $env:LOCALAPPDATA ([string]$manifest.install.default_relative_dir)
    }
    $InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
    $installerArguments = @(
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/TASKS=desktopicon",
        ('/DIR="{0}"' -f $InstallRoot)
    )
    $installerProcess = Start-Process -FilePath $installerPath -ArgumentList $installerArguments -Wait -PassThru
    if ($installerProcess.ExitCode -ne 0) {
        throw "The installer exited with code $($installerProcess.ExitCode)."
    }

    $installedExecutable = Get-InstalledExecutable -Manifest $manifest -ExplicitInstallRoot $InstallRoot
    if (-not (Test-InstalledPackage -ExecutablePath $installedExecutable -ExpectedVersion ([string]$manifest.version))) {
        throw "Installation finished, but the complete expected Vision Training Studio package was not found."
    }
    Save-JsonAtomically -Path $statePath -Value ([ordered]@{
        schema_version = 1
        product = [string]$manifest.product
        version = [string]$manifest.version
        package_id = [string]$manifest.package_id
        installer_sha256 = $installerSha256
        executable_path = $installedExecutable
        installed_at = [DateTime]::UtcNow.ToString("o")
    })

    if (Test-Path -LiteralPath $installerPath) {
        Remove-Item -LiteralPath $installerPath -Force
    }
    Write-Host "[Vision Training Studio] Installation is ready. Starting the application..."
    if (-not $NoLaunch) {
        Start-Process -FilePath $installedExecutable -WorkingDirectory (Split-Path -Parent $installedExecutable) | Out-Null
    }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "[Vision Training Studio] Startup failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "No incomplete download was installed. Run the launcher again after checking the internet connection."
    exit 1
}
finally {
    if ($bootstrapMutexOwned -and $bootstrapMutex) {
        try { $bootstrapMutex.ReleaseMutex() } catch { }
    }
    if ($bootstrapMutex) {
        $bootstrapMutex.Dispose()
    }
}
