# Auto-detect the watch and capture its screen to a clean PNG (no PowerShell binary corruption).
$ErrorActionPreference = "Continue"
$outDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$outPng = Join-Path $outDir "watchface_capture.png"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")
$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }
$watch = Get-WatchSerial $adb -AllowSoloFallback
if (-not $watch) { Write-Host "Cannot pick watch."; exit 1 }
Write-Host "Waking watch: $watch"
& $adb -s $watch shell input keyevent KEYCODE_WAKEUP 2>$null | Out-Null
Start-Sleep -Milliseconds 900
Write-Host "Capturing from watch: $watch"
$devPath = "/sdcard/watchface_capture.png"
# screencap to a file ON the device, then pull it (pull writes binary correctly; avoids PS '>' corruption)
& $adb -s $watch shell screencap -p $devPath
if (Test-Path $outPng) { Remove-Item $outPng -Force -ErrorAction SilentlyContinue }
& $adb -s $watch pull $devPath "$outPng" | Out-Null
& $adb -s $watch shell rm -f $devPath 2>$null | Out-Null
if ((Test-Path $outPng) -and ((Get-Item $outPng).Length -gt 0)) {
    Write-Host "Saved: $outPng ($((Get-Item $outPng).Length) bytes)"
} else {
    Write-Host "Capture failed (empty file)."; exit 1
}
