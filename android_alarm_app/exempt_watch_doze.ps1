# Exempt the watch alarm app from Doze / battery optimization so exact alarms fire on time.
$ErrorActionPreference = "Continue"
$pkg = "com.example.oneshotalarm"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")
$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }
$watch = Get-WatchSerial $adb -AllowSoloFallback
if (-not $watch) { Write-Host "Cannot pick watch."; exit 1 }

Write-Host "Exempting $pkg from Doze / battery optimization on $watch ..."
Write-Host "- Add to Doze battery-optimization whitelist"
(& $adb -s $watch shell dumpsys deviceidle whitelist +$pkg) 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "- Set App Standby bucket to active"
(& $adb -s $watch shell am set-standby-bucket $pkg active) 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "- Verify it is in the whitelist:"
$wl = (& $adb -s $watch shell dumpsys deviceidle whitelist) 2>&1
$wl | Select-String -SimpleMatch $pkg | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Done. Now test WITHOUT adb attached: wear it, screen off, wait for an alarm,"
Write-Host "and compare phone vs watch ring timing."
