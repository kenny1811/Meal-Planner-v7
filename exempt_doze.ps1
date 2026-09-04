# 一次過豁免所有「要喺背景長跑」嘅自製 app（兩部機）。
# 背景：2026-08-22 com.kenny.watchface.wear（電話）俾 Adaptive Battery 降到 RESTRICTED
# 兼 DISABLED_UNTIL_USED，phone battery 同 HKO sun times 靜靜哋斷咗 53 個鐘先發現。
# 根治靠白名單（bucket 釘死喺 5 = EXEMPTED，唔理幾耐冇開過都唔會降級）。
# clean reinstall 會清走呢啲設定，所以每次 reinstall 之後跑一次。
$ErrorActionPreference = "Continue"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "adb_common.ps1")

$watchPkgs = @("com.example.oneshotalarm", "com.kenny.watchface.wear")
$phonePkgs = @("com.example.oneshotalarm", "com.kenny.watchface.wear")

$adb = Resolve-AdbPath
if (-not $adb) { Write-Host "adb not found."; exit 1 }

function Exempt-Package($adb, $serial, $pkg) {
    $installed = (& $adb -s $serial shell pm list packages $pkg) 2>$null
    if ("$installed" -notmatch [regex]::Escape($pkg)) {
        Write-Host "  - $pkg : not installed, skipped"
        return
    }
    (& $adb -s $serial shell dumpsys deviceidle whitelist +$pkg) 2>&1 | Out-Null
    (& $adb -s $serial shell am set-standby-bucket $pkg active) 2>&1 | Out-Null
    (& $adb -s $serial shell cmd appops set $pkg RUN_ANY_IN_BACKGROUND allow) 2>&1 | Out-Null
    $bucket = ((& $adb -s $serial shell am get-standby-bucket $pkg) 2>$null) -join ""
    $wl = (& $adb -s $serial shell dumpsys deviceidle whitelist) 2>$null
    $inList = if (($wl -join "`n") -match ",$([regex]::Escape($pkg)),") { "yes" } else { "NO" }
    Write-Host "  - $pkg : bucket=$($bucket.Trim())  whitelisted=$inList"
}

$ready = Get-ReadyDevices $adb
if ($ready.Count -eq 0) { Write-Host "No adb devices connected."; exit 1 }

# 同一部機成日有幾條通道（Tailscale / 無線偵錯 / 5555 / mDNS），唔按硬件序號去重
# 就會當咗係幾部機，跟住為咗安全而跳過——所以先 collapse 返做一部機一條通道。
$byDevice = @{}
foreach ($s in $ready) {
    $sn = ((& $adb -s $s shell getprop ro.serialno) 2>$null) -join ""
    $sn = $sn.Trim()
    if (-not $sn) { $sn = $s }
    if (-not $byDevice.ContainsKey($sn)) { $byDevice[$sn] = $s }
}

$watch = $null; $phones = @()
foreach ($s in $byDevice.Values) {
    if (Test-IsWatch $adb $s) { if (-not $watch) { $watch = $s } } else { $phones += $s }
}

if ($watch) {
    Write-Host "WATCH ($watch):"
    foreach ($p in $watchPkgs) { Exempt-Package $adb $watch $p }
} else {
    Write-Host "WATCH: not connected, skipped."
}

if ($phones.Count -eq 1) {
    Write-Host "PHONE ($($phones[0])):"
    foreach ($p in $phonePkgs) { Exempt-Package $adb $phones[0] $p }
} elseif ($phones.Count -gt 1) {
    Write-Host "PHONE: multiple non-watch devices ($($phones -join ', ')); skipped to avoid touching the wrong one."
} else {
    Write-Host "PHONE: not connected, skipped."
}

Write-Host ""
Write-Host "Done. bucket=5 means EXEMPTED (App Standby will never demote it again)."
Write-Host "bucket=10 with whitelisted=yes settles to 5 shortly; bucket=45 means it failed."
