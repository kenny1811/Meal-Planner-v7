# Auto-detect the watch and screencap the current screen to a PNG in this folder.
$ErrorActionPreference = "Continue"
$outDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$outPng = Join-Path $outDir "watchface_capture.png"
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
foreach ($line in (& $adb devices)) { $t="$line".Trim(); if ($t -match '^(.+?)\s+device$'){ $ready += $Matches[1] } }
if ($ready.Count -eq 0) { Write-Host "No adb devices."; exit 1 }
$watch = $null
foreach ($s in $ready) { $ch=(& $adb -s $s shell getprop ro.build.characteristics) 2>$null; if ("$ch" -match 'watch'){ $watch=$s; break } }
if (-not $watch) { if ($ready.Count -eq 1){ $watch=$ready[0] } else { Write-Host "Cannot pick watch among: $($ready -join ', ')"; exit 1 } }
Write-Host "Capturing from watch: $watch"
# exec-out keeps binary intact (plain shell screencap corrupts PNG on Windows)
& $adb -s $watch exec-out screencap -p > "$outPng"
if ((Test-Path $outPng) -and ((Get-Item $outPng).Length -gt 0)) {
    Write-Host "Saved: $outPng ($((Get-Item $outPng).Length) bytes)"
} else {
    Write-Host "Capture failed (empty file)."; exit 1
}
