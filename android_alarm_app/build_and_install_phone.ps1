param([string]$Variant = "app:assembleDebug", [string]$DeviceSerial = "", [switch]$NoBuild)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot
if (-not (Test-Path ".\gradlew.bat")) { throw "Not found: .\gradlew.bat" }

function Resolve-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return $env:JAVA_HOME }
    $paths = @()
    if ($env:ProgramFiles) {
        $paths += Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
        $paths += Join-Path $env:ProgramFiles "Eclipse Adoptium\jdk-*"
    }
    if ($env:LOCALAPPDATA) {
        $paths += Join-Path $env:LOCALAPPDATA "Programs\Android Studio\jbr"
        $paths += Join-Path $env:LOCALAPPDATA "Programs\Android\Android Studio\jbr"
    }
    foreach ($exact in @(
        "C:\Program Files\Android\Android Studio\jbr",
        "C:\Program Files (x86)\Android\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android\Android Studio\jbr"
    )) { if (Test-Path (Join-Path $exact "bin\java.exe")) { return $exact } }
    foreach ($pattern in $paths) {
        foreach ($c in (Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue)) {
            if (Test-Path (Join-Path $c.FullName "bin\java.exe")) { return $c.FullName }
        }
    }
    $direct = Get-Command java -ErrorAction SilentlyContinue
    if ($direct) { $g = Split-Path -Parent (Split-Path -Parent $direct.Source); if (Test-Path (Join-Path $g "bin\java.exe")) { return $g } }
    return $null
}

function Resolve-AdbPath {
    $fromCmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($fromCmd) { return $fromCmd.Source }
    $candidates = @()
    if ($env:ANDROID_HOME) { $candidates += Join-Path $env:ANDROID_HOME "platform-tools\adb.exe" }
    if ($env:ANDROID_SDK_ROOT) { $candidates += Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe" }
    if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe" }
    $candidates += "C:\Android\Sdk\platform-tools\adb.exe"
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    return $null
}

function Get-ReadyDevices($adb) {
    $out = & $adb devices
    $ready = @()
    foreach ($line in ($out -split "`r?`n")) {
        $t = $line.Trim()
        if ($t -match '^(.+?)\s+device$') { $ready += $Matches[1] }
    }
    return ,$ready
}

function Test-IsWatch($adb, $serial) {
    $ch = (& $adb -s $serial shell getprop ro.build.characteristics) 2>$null
    return ("$ch" -match 'watch')
}

if (-not $NoBuild) {
    $javaHome = Resolve-JavaHome
    if (-not $javaHome) { throw "JAVA_HOME not found. Install JDK or set JAVA_HOME." }
    $env:JAVA_HOME = $javaHome
    if ($env:PATH -notmatch [regex]::Escape("$javaHome\bin")) { $env:PATH = "$javaHome\bin;" + $env:PATH }
    Write-Host "Build: ./gradlew $Variant"
    & .\gradlew.bat $Variant
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed, exit code: $LASTEXITCODE" }
}
$apkPath = Join-Path $projectRoot "app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }
$adbPath = Resolve-AdbPath
if (-not $adbPath) { throw "adb not found. Install Android platform-tools." }

Write-Host "Checking adb devices..."
$ready = Get-ReadyDevices $adbPath
if ($ready.Count -eq 0) { Write-Host "No adb devices connected; skipping PHONE install."; exit 0 }

$target = $DeviceSerial.Trim()
if (-not $target) {
    $phones = @()
    foreach ($s in $ready) { if (-not (Test-IsWatch $adbPath $s)) { $phones += $s } }
    if ($phones.Count -eq 1) { $target = $phones[0] }
    elseif ($phones.Count -gt 1) {
        Write-Host "Multiple non-watch devices:"; for ($i=0;$i -lt $phones.Count;$i++){ Write-Host "  [$i] $($phones[$i])" }
        $target = (Read-Host "Enter the PHONE serial").Trim()
    } else {
        Write-Host "No PHONE (non-watch) device connected; skipping phone install."; exit 0
    }
}
Write-Host "Target phone: $target"
Write-Host "Installing phone APK..."
& $adbPath -s $target install -r "$apkPath"
if ($LASTEXITCODE -ne 0) { throw "Phone APK install failed, exit code: $LASTEXITCODE" }
Write-Host "Install complete on: $target"
