param([string]$Variant = "app:assembleDebug", [string]$DeviceSerial = "", [switch]$NoBuild)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot
if (-not (Test-Path ".\gradlew.bat")) { throw "Not found: .\gradlew.bat" }
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")

if (-not $NoBuild) {
    Use-JavaHome | Out-Null
    Write-Host "Build: ./gradlew $Variant"
    & .\gradlew.bat $Variant
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed, exit code: $LASTEXITCODE" }
}
$apkPath = Join-Path $projectRoot "app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }
$adbPath = Resolve-AdbPath
if (-not $adbPath) { throw "adb not found. Install Android platform-tools." }

Write-Host "Checking adb devices..."
$ready = Get-ReadyDevices $adbPath
if ($ready.Count -eq 0) { Write-Host "No adb devices connected; skipping PHONE install."; exit 0 }

$target = $DeviceSerial.Trim()
if (-not $target) {
    $phones = @()
    foreach ($s in $ready) { if (-not (Test-IsWatch $adbPath $s)) { $phones += $s } }
    if ($phones.Count -eq 1) { $target = $phones[0] }
    elseif ($phones.Count -gt 1) {
        Write-Host "Multiple non-watch devices:"; for ($i=0;$i -lt $phones.Count;$i++){ Write-Host "  [$i] $($phones[$i])" }
        $target = (Read-Host "Enter the PHONE serial").Trim()
    } else {
        Write-Host "No PHONE (non-watch) device connected; skipping phone install."; exit 0
    }
}
Write-Host "Target phone: $target"
Write-Host "Installing phone APK..."
& $adbPath -s $target install -r "$apkPath"
if ($LASTEXITCODE -ne 0) { throw "Phone APK install failed, exit code: $LASTEXITCODE" }
Write-Host "Install complete on: $target"
