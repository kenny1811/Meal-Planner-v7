param(
    [string]$Variant = "wear:assembleDebug",
    [string]$DeviceSerial = "",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot

if (-not (Test-Path ".\gradlew.bat")) {
    throw "Not found: .\gradlew.bat"
}

function Resolve-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
        return $env:JAVA_HOME
    }
    $paths = @()
    if ($env:ProgramFiles) {
        $paths += Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
        $paths += Join-Path $env:ProgramFiles "Eclipse Adoptium\jdk-*"
        $paths += Join-Path $env:ProgramFiles "OpenJDK\*"
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
    )) {
        if (Test-Path (Join-Path $exact "bin\java.exe")) { return $exact }
    }
    foreach ($pattern in $paths) {
        $cands = Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue
        foreach ($c in $cands) {
            if (Test-Path (Join-Path $c.FullName "bin\java.exe")) { return $c.FullName }
        }
    }
    $direct = Get-Command java -ErrorAction SilentlyContinue
    if ($direct) {
        $g = Split-Path -Parent (Split-Path -Parent $direct.Source)
        if (Test-Path (Join-Path $g "bin\java.exe")) { return $g }
    }
    return $null
}

if (-not $NoBuild) {
    $javaHome = Resolve-JavaHome
    if (-not $javaHome) { throw "JAVA_HOME not found. Install JDK or set JAVA_HOME." }
    $env:JAVA_HOME = $javaHome
    if ($env:PATH -notmatch [regex]::Escape("$javaHome\bin")) {
        $env:PATH = "$javaHome\bin;" + $env:PATH
    }
    Write-Host "Build: ./gradlew $Variant"
    & .\gradlew.bat $Variant
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed, exit code: $LASTEXITCODE" }
}

$apkPath = Join-Path $projectRoot "wear\build\outputs\apk\debug\wear-debug.apk"
if (-not (Test-Path $apkPath)) { throw "APK not found: $apkPath" }

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

$adbPath = Resolve-AdbPath
if (-not $adbPath) { throw "adb not found. Install Android platform-tools and add adb to PATH." }

Write-Host "Checking adb devices..."
$devicesOutput = & $adbPath devices
$ready = @()
foreach ($line in ($devicesOutput -split "`r?`n")) {
    $t = $line.Trim()
    if ($t -match '^(.+?)\s+device$') { $ready += $Matches[1] }
}
if ($ready.Count -eq 0) { throw "No adb devices in 'device' state. Connect/authorize the watch." }

$target = $DeviceSerial.Trim()
if (-not $target) {
    # Auto-detect the Wear device via ro.build.characteristics = "...watch..."
    foreach ($s in $ready) {
        $ch = (& $adbPath -s $s shell getprop ro.build.characteristics) 2>$null
        if ("$ch" -match 'watch') { $target = $s; Write-Host "Detected watch: $s"; break }
    }
}
if (-not $target) {
    if ($ready.Count -eq 1) {
        $target = $ready[0]
        Write-Host "Only one device; using: $target"
    } else {
        Write-Host "Could not auto-detect the watch. Connected devices:"
        for ($i = 0; $i -lt $ready.Count; $i++) { Write-Host "  [$i] $($ready[$i])" }
        $sel = Read-Host "Enter the WATCH serial exactly as shown above"
        $target = $sel.Trim()
    }
}
if (-not $target) { throw "No target device selected." }

Write-Host "Target device: $target"
Write-Host "Installing wear APK..."
& $adbPath -s $target install -r "$apkPath"
if ($LASTEXITCODE -ne 0) { throw "APK install failed, exit code: $LASTEXITCODE" }

Write-Host "Install complete: $apkPath"
Write-Host "Installed on: $target"
