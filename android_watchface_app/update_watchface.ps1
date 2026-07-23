param([switch]$Clean, [switch]$NoBuild)
$ErrorActionPreference = "Stop"
$pkg = "com.kenny.watchface"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot
if (-not (Test-Path ".\gradlew.bat")) { throw "Not found: .\gradlew.bat" }
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")

if (-not $NoBuild) {
    Use-JavaHome | Out-Null
    Write-Host "Build: ./gradlew :watchface:assembleDebug"
    & .\gradlew.bat :watchface:assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed, exit code: $LASTEXITCODE" }
}
$apkPath = Join-Path $projectRoot "watchface\build\outputs\apk\debug\watchface-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }
$adb = Resolve-AdbPath
if (-not $adb) { throw "adb not found. Install Android platform-tools." }

$ready = Get-ReadyDevices $adb
if ($ready.Count -eq 0) { Write-Host "No adb devices; skipping."; exit 0 }
$watch = Get-WatchSerial $adb -AllowSoloFallback
if (-not $watch) { Write-Host "Cannot pick watch among: $($ready -join ', ')"; exit 1 }

$ErrorActionPreference = "Continue"
if ($Clean) {
    Write-Host "CLEAN: uninstalling $pkg from $watch (resets complication slots)..."
    (& $adb -s $watch uninstall $pkg 2>&1) | ForEach-Object { Write-Host $_ }
    Write-Host "Installing fresh..."
    (& $adb -s $watch install "$apkPath" 2>&1) | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Installing (keep data) to $watch..."
    (& $adb -s $watch install -r "$apkPath" 2>&1) | ForEach-Object { Write-Host $_ }
}
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: watchface install failed (rc=$LASTEXITCODE)."; exit 1 }
Write-Host "Watchface install complete on: $watch"
if ($Clean) { Write-Host "NOTE: watch reverted to default face. Re-select the Kenny face to rebind complications." }
