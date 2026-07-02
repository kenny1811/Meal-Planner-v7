# Restore watch app permissions that a clean reinstall wipes (overlay + notifications).
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
Write-Host "Granting permissions to $pkg on $watch ..."
Write-Host "- SYSTEM_ALERT_WINDOW (full-screen alarm overlay)"
& $adb -s $watch shell appops set $pkg SYSTEM_ALERT_WINDOW allow 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "- POST_NOTIFICATIONS"
& $adb -s $watch shell pm grant $pkg android.permission.POST_NOTIFICATIONS 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host "Done. Test an alarm again; the full-screen watch alarm should now appear."
