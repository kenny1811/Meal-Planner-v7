param([string]$Variant = "wear:assembleDebug", [string]$DeviceSerial = "", [switch]$NoBuild)
$ErrorActionPreference = "Stop"
$pkg = "com.example.oneshotalarm"
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
$apkPath = Join-Path $projectRoot "wear\build\outputs\apk\debug\wear-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }
$adbPath = Resolve-AdbPath
if (-not $adbPath) { throw "adb not found. Install Android platform-tools." }

Write-Host "Checking adb devices..."
$ready = Get-ReadyDevices $adbPath
if ($ready.Count -eq 0) { Write-Host "No adb devices connected; skipping WATCH install."; exit 0 }

$target = $DeviceSerial.Trim()
if (-not $target) {
    $watches = @()
    foreach ($s in $ready) { if (Test-IsWatch $adbPath $s) { $watches += $s } }
    if ($watches.Count -eq 1) { $target = $watches[0]; Write-Host "Detected watch: $target" }
    elseif ($watches.Count -gt 1) {
        Write-Host "Multiple watches:"; for ($i=0;$i -lt $watches.Count;$i++){ Write-Host "  [$i] $($watches[$i])" }
        $target = (Read-Host "Enter the WATCH serial").Trim()
    } else {
        Write-Host "No WATCH device detected; skipping watch install."; exit 0
    }
}
Write-Host "Target watch: $target"
$ErrorActionPreference = "Continue"   # adb 寫 stderr 唔應該當 terminating error
Write-Host "Installing wear APK..."
$out = & $adbPath -s $target install -r "$apkPath" 2>&1
$out | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    if ("$out" -match 'VERSION_DOWNGRADE|UPDATE_INCOMPATIBLE|signatures do not match') {
        Write-Host "Install blocked (downgrade/incompatible). Uninstalling $pkg from watch and retrying clean..."
        & $adbPath -s $target uninstall $pkg | ForEach-Object { Write-Host $_ }
        & $adbPath -s $target install "$apkPath"
        if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: clean reinstall failed (rc=$LASTEXITCODE)."; exit 1 }
    } else {
        Write-Host "ERROR: watch install failed (rc=$LASTEXITCODE)."; exit 1
    }
}
Write-Host "Install complete on: $target"
