# 兩個 Android app 目錄共用嘅 adb / gradle helper（Resolve-AdbPath 之前散喺 9 個腳本，
# 嚴格 phone/watch 偵測散喺 8 個——而家得呢一份，唔會再 drift）。
# 用法（腳本頭一行）：. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")
# 注意：.ps1 必須 UTF-8 BOM（PS 5.1 冇 BOM 會當 Big5 讀，仲可能食埋下一行）。

function Resolve-AdbPath {
    $fromCmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($fromCmd) { return $fromCmd.Source }
    $candidates = @()
    if ($env:LOCALAPPDATA)     { $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe" }
    if ($env:ANDROID_HOME)     { $candidates += Join-Path $env:ANDROID_HOME "platform-tools\adb.exe" }
    if ($env:ANDROID_SDK_ROOT) { $candidates += Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe" }
    $candidates += "C:\Android\Sdk\platform-tools\adb.exe"
    foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}

function Resolve-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return $env:JAVA_HOME }
    foreach ($exact in @(
        "C:\Program Files\Android\Android Studio\jbr",
        "C:\Program Files (x86)\Android\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android\Android Studio\jbr"
    )) { if (Test-Path (Join-Path $exact "bin\java.exe")) { return $exact } }
    if ($env:ProgramFiles) {
        foreach ($c in (Get-ChildItem -Path (Join-Path $env:ProgramFiles "Eclipse Adoptium\jdk-*") -Directory -ErrorAction SilentlyContinue)) {
            if (Test-Path (Join-Path $c.FullName "bin\java.exe")) { return $c.FullName }
        }
    }
    $direct = Get-Command java -ErrorAction SilentlyContinue
    if ($direct) { $g = Split-Path -Parent (Split-Path -Parent $direct.Source); if (Test-Path (Join-Path $g "bin\java.exe")) { return $g } }
    return $null
}

function Use-JavaHome {
    # 設定 JAVA_HOME + PATH；搵唔到就 throw。
    $javaHome = Resolve-JavaHome
    if (-not $javaHome) { throw "JAVA_HOME not found. Install JDK or set JAVA_HOME." }
    $env:JAVA_HOME = $javaHome
    if ($env:PATH -notmatch [regex]::Escape("$javaHome\bin")) { $env:PATH = "$javaHome\bin;" + $env:PATH }
    return $javaHome
}

function Get-ReadyDevices($adb) {
    $ready = @()
    foreach ($line in (& $adb devices)) {
        $t = "$line".Trim()
        if ($t -match '^(.+?)\s+device$') { $ready += $Matches[1] }
    }
    return ,$ready
}

function Test-IsWatch($adb, $serial) {
    # 嚴格用 ro.build.characteristics 分 phone/watch——防止裝錯機（裝錯會甩權限/complication）。
    $ch = (& $adb -s $serial shell getprop ro.build.characteristics) 2>$null
    return ("$ch" -match 'watch')
}

function Get-WatchSerial($adb, [switch]$AllowSoloFallback) {
    # 揀手錶：有 watch 特徵嗰部；冇 watch 但淨係得一部機兼 AllowSoloFallback 先肯回傳佢。
    $ready = Get-ReadyDevices $adb
    if ($ready.Count -eq 0) { return $null }
    foreach ($s in $ready) { if (Test-IsWatch $adb $s) { return $s } }
    if ($AllowSoloFallback -and $ready.Count -eq 1) { return $ready[0] }
    return $null
}
