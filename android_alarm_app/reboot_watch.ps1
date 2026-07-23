# Auto-detect the Wear device and reboot it (no typing needed).
$ErrorActionPreference = "Continue"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")
$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }
$watch = Get-WatchSerial $adb -AllowSoloFallback
if (-not $watch) { Write-Host "Cannot pick watch."; exit 1 }
Write-Host "Rebooting watch: $watch"
& $adb -s $watch reboot
Write-Host "Reboot command sent. The watch will restart in a few seconds."
Write-Host "After it boots: prev/next complications rebind, and E(b) boot catch-up runs."
