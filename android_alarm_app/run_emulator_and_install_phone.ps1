param(
    [string]$AvdName = "",
    [switch]$NoBuild,
    [int]$BootTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Resolve-AdbPath {
    $candidates = @()
    if ($env:ANDROID_HOME) {
        $candidates += Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    }
    if ($env:ANDROID_SDK_ROOT) {
        $candidates += Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe"
    }
    $candidates += "C:\Users\Kenny\AppData\Local\Android\Sdk\platform-tools\adb.exe"
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $fromCmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($fromCmd) {
        return $fromCmd.Source
    }
    return $null
}

function Resolve-EmulatorPath {
    $candidates = @(
        "C:\Users\Kenny\AppData\Local\Android\Sdk\emulator\emulator.exe",
        (Join-Path $env:LOCALAPPDATA "Android\Sdk\emulator\emulator.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Get-ConnectedDevices([string]$AdbPath) {
    $output = & $AdbPath devices
    return ($output -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object {
        $_ -and $_ -notmatch '^List of devices' -and $_ -match '\s+(device|unauthorized|offline|host)$'
    })
}

function Pick-Avd([string]$RequestedAvd, [string[]]$AvailableAvds) {
    if ($AvailableAvds.Count -eq 0) {
        throw "No AVD found. Create one in Android Studio > Device Manager first."
    }
    if ([string]::IsNullOrWhiteSpace($RequestedAvd)) {
        if ($AvailableAvds.Count -eq 1) {
            return $AvailableAvds[0]
        }
        Write-Host "AVD list:"
        $AvailableAvds | ForEach-Object { Write-Host " - $_" }
        throw "More than one AVD exists. Pass -AvdName to pick one."
    }
    if ($AvailableAvds -notcontains $RequestedAvd) {
        Write-Host "Available AVDs:"
        $AvailableAvds | ForEach-Object { Write-Host " - $_" }
        throw "AVD '$RequestedAvd' not found."
    }
    return $RequestedAvd
}

function Wait-ForEmulatorBoot([string]$AdbPath, [int]$TimeoutSeconds) {
    Write-Host "Waiting for emulator boot..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $lines = Get-ConnectedDevices $AdbPath
        foreach ($line in $lines) {
            if ($line -match '^emulator-\d+\s+device$') {
                $serial = ($line -split '\s+')[0]
                $boot = & $AdbPath -s $serial shell getprop sys.boot_completed 2>$null | ForEach-Object { $_.Trim() }
                if ($boot -eq "1") {
                    return $serial
                }
            }
        }
        Start-Sleep -Milliseconds 1000
    }
    throw "Emulator boot timeout after $TimeoutSeconds seconds."
}

$adbPath = Resolve-AdbPath
if (-not $adbPath) {
    throw "adb not found. Please install Android platform-tools and add adb to PATH."
}

$emulatorPath = Resolve-EmulatorPath
if (-not $emulatorPath) {
    throw "Android emulator binary not found (emulator.exe)."
}

$avdOutput = & $emulatorPath -list-avds
$avds = @($avdOutput | Where-Object { $_ -and $_.Trim() -ne "" } | ForEach-Object { $_.Trim() })
$targetAvd = Pick-Avd -RequestedAvd $AvdName -AvailableAvds $avds
Write-Host "Target AVD: $targetAvd"

$existing = Get-ConnectedDevices $adbPath
$isEmulatorRunning = $false
foreach ($line in $existing) {
    if ($line -match '^emulator-\d+\s+device$') {
        $isEmulatorRunning = $true
        break
    }
}

if (-not $isEmulatorRunning) {
    Write-Host "Launching emulator..."
    Start-Process -FilePath $emulatorPath -ArgumentList @("-avd", $targetAvd) -WindowStyle Minimized
}

$deviceSerial = Wait-ForEmulatorBoot -AdbPath $adbPath -TimeoutSeconds $BootTimeoutSeconds
Write-Host "Emulator ready: $deviceSerial"

if ($NoBuild) {
    Write-Host "NoBuild set, skipping app build."
} else {
    Write-Host "Building and installing via existing install script..."
}

& "$projectRoot\build_and_install_phone.ps1" -NoBuild:$NoBuild
if ($LASTEXITCODE -ne 0) {
    throw "Build/install script failed, exit code: $LASTEXITCODE"
}
