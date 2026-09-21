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
    # 唔會自動 uninstall 自癒：uninstall 會甩 SYSTEM_ALERT_WINDOW／POST_NOTIFICATIONS 權限，
    # 錶面 complication slot 亦會 orphan（見 CLAUDE.md）。downgrade 錯誤＝versionCode 未跟 phone 對齊，改 build.gradle。
    Write-Host "ERROR: watch install failed (rc=$LASTEXITCODE). Not uninstalling $pkg (would drop permissions/complications)."
    exit 1
}
Write-Host "Install complete on: $target"
