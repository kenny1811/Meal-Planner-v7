# Auto-detect the Wear device and reboot it (no typing needed).
$ErrorActionPreference = "Continue"
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

$ready = @()
foreach ($line in (& $adb devices)) {
    $t = "$line".Trim()
    if ($t -match '^(.+?)\s+device$') { $ready += $Matches[1] }
}
if ($ready.Count -eq 0) { Write-Host "No adb devices connected."; exit 1 }

$watch = $null
foreach ($s in $ready) {
    $ch = (& $adb -s $s shell getprop ro.build.characteristics) 2>$null
    if ("$ch" -match 'watch') { $watch = $s; break }
}
if (-not $watch) {
    if ($ready.Count -eq 1) { $watch = $ready[0] }
    else { Write-Host "Could not auto-detect the watch among: $($ready -join ', ')"; exit 1 }
}
Write-Host "Rebooting watch: $watch"
& $adb -s $watch reboot
Write-Host "Reboot command sent. The watch will restart in a few seconds."
Write-Host "After it boots: prev/next complications rebind, and E(b) boot catch-up runs."
