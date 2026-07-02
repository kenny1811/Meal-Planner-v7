# Exempt the watch alarm app from Doze / battery optimization so exact alarms fire on time.
$ErrorActionPreference = "Continue"
$pkg = "com.example.oneshotalarm"
function Resolve-AdbPath {
    $f = Get-Command adb -ErrorAction SilentlyContinue
    if ($f) { return $f.Source }
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
        (Join-Path $env:ANDROID_HOME  "platform-tools\adb.exe"),
        "C:\Android\Sdk\platform-tools\adb.exe")) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}
$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }
$ready=@(); foreach ($l in (& $adb devices)){ $t="$l".Trim(); if($t -match '^(.+?)\s+device$'){ $ready+=$Matches[1] } }
if ($ready.Count -eq 0){ Write-Host "No adb devices."; exit 1 }
$watch=$null
foreach($s in $ready){ $ch=(& $adb -s $s shell getprop ro.build.characteristics) 2>$null; if("$ch" -match 'watch'){ $watch=$s; break } }
if(-not $watch){ if($ready.Count -eq 1){ $watch=$ready[0] } else { Write-Host "Cannot pick watch."; exit 1 } }

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
