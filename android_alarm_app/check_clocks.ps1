# Compare phone vs watch clocks (epoch ms) to see the skew.
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
$ready=@(); foreach ($l in (& $adb devices)){ $t="$l".Trim(); if($t -match '^(.+?)\s+device$'){ $ready+=$Matches[1] } }
if ($ready.Count -eq 0){ Write-Host "No adb devices."; exit 1 }

$rows=@()
foreach($s in $ready){
    $ch=(& $adb -s $s shell getprop ro.build.characteristics) 2>$null
    $kind = ("$ch" -match 'watch') ? "WATCH" : "PHONE"
    $ms = (& $adb -s $s shell date +%s%3N) 2>$null
    $ms = "$ms".Trim()
    $human = (& $adb -s $s shell date +"%H:%M:%S.%3N") 2>$null
    $rows += [PSCustomObject]@{ Kind=$kind; Serial=$s; Ms=[int64]($ms -replace '[^\d]',''); Human="$human".Trim() }
}
foreach($r in $rows){ Write-Host ("{0,-6} {1,-24} {2}" -f $r.Kind, $r.Serial, $r.Human) }
if ($rows.Count -ge 2){
    $diff = [math]::Abs($rows[0].Ms - $rows[1].Ms)
    Write-Host ""
    Write-Host ("Clock difference: {0} ms  (~{1:N1} s)" -f $diff, ($diff/1000.0))
    Write-Host "(note: includes a small adb round-trip gap between the two reads, usually < 100 ms)"
}
