param([switch]$Clean, [switch]$NoBuild)
$ErrorActionPreference = "Stop"
$pkg = "com.kenny.watchface"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot
if (-not (Test-Path ".\gradlew.bat")) { throw "Not found: .\gradlew.bat" }

function Resolve-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return $env:JAVA_HOME }
    foreach ($exact in @(
        "C:\Program Files\Android\Android Studio\jbr",
        "C:\Program Files (x86)\Android\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android\Android Studio\jbr")) {
        if (Test-Path (Join-Path $exact "bin\java.exe")) { return $exact }
    }
    $direct = Get-Command java -ErrorAction SilentlyContinue
    if ($direct) { $g = Split-Path -Parent (Split-Path -Parent $direct.Source); if (Test-Path (Join-Path $g "bin\java.exe")) { return $g } }
    return $null
}
function Resolve-AdbPath {
    $f = Get-Command adb -ErrorAction SilentlyContinue
    if ($f) { return $f.Source }
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
        (Join-Path $env:ANDROID_HOME  "platform-tools\adb.exe"),
        "C:\Android\Sdk\platform-tools\adb.exe")) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}

if (-not $NoBuild) {
    $javaHome = Resolve-JavaHome
    if (-not $javaHome) { throw "JAVA_HOME not found. Install JDK or set JAVA_HOME." }
    $env:JAVA_HOME = $javaHome
    if ($env:PATH -notmatch [regex]::Escape("$javaHome\bin")) { $env:PATH = "$javaHome\bin;" + $env:PATH }
    Write-Host "Build: ./gradlew :watchface:assembleDebug"
    & .\gradlew.bat :watchface:assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed, exit code: $LASTEXITCODE" }
}
$apkPath = Join-Path $projectRoot "watchface\build\outputs\apk\debug\watchface-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }
$adb = Resolve-AdbPath
if (-not $adb) { throw "adb not found. Install Android platform-tools." }

$ready = @()
foreach ($line in (& $adb devices)) { $t="$line".Trim(); if ($t -match '^(.+?)\s+device$'){ $ready += $Matches[1] } }
if ($ready.Count -eq 0) { Write-Host "No adb devices; skipping."; exit 0 }
$watch = $null
foreach ($s in $ready) { $ch=(& $adb -s $s shell getprop ro.build.characteristics) 2>$null; if ("$ch" -match 'watch'){ $watch=$s; break } }
if (-not $watch) { if ($ready.Count -eq 1){ $watch=$ready[0] } else { Write-Host "Cannot pick watch among: $($ready -join ', ')"; exit 1 } }

$ErrorActionPreference = "Continue"
if ($Clean) {
    Write-Host "CLEAN: uninstalling $pkg from $watch (resets complication slots)..."
    (& $adb -s $watch uninstall $pkg 2>&1) | ForEach-Object { Write-Host $_ }
    Write-Host "Installing fresh..."
    (& $adb -s $watch install "$apkPath" 2>&1) | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Installing (keep data) to $watch..."
    (& $adb -s $watch install -r "$apkPath" 2>&1) | ForEach-Object { Write-Host $_ }
}
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: watchface install failed (rc=$LASTEXITCODE)."; exit 1 }
Write-Host "Watchface install complete on: $watch"
if ($Clean) { Write-Host "NOTE: watch reverted to default face. Re-select the Kenny face to rebind complications." }
