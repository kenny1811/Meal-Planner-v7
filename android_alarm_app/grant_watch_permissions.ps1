# Restore watch app permissions that a clean reinstall wipes (overlay + notifications).
$ErrorActionPreference = "Continue"
$pkg = "com.example.oneshotalarm"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")
$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }
$watch = Get-WatchSerial $adb -AllowSoloFallback
if (-not $watch) { Write-Host "Cannot pick watch."; exit 1 }
Write-Host "Granting permissions to $pkg on $watch ..."
Write-Host "- SYSTEM_ALERT_WINDOW (full-screen alarm overlay)"
& $adb -s $watch shell appops set $pkg SYSTEM_ALERT_WINDOW allow 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "- POST_NOTIFICATIONS"
& $adb -s $watch shell pm grant $pkg android.permission.POST_NOTIFICATIONS 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "Done. Test an alarm again; the full-screen watch alarm should now appear."
