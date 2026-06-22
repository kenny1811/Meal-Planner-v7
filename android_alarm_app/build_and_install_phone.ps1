param(
    [string]$Variant = "app:assembleDebug",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot

if (-not (Test-Path ".\gradlew.bat")) {
    throw "Not found: .\\gradlew.bat"
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
        $paths += Join-Path $env:LOCALAPPDATA "Programs\Microsoft\JDK\*"
    }
    if ($env:ProgramFilesX86) {
        $paths += Join-Path $env:ProgramFilesX86 "Android\Android Studio\jbr"
        $paths += Join-Path $env:ProgramFilesX86 "Eclipse Adoptium\jdk-*"
        $paths += Join-Path $env:ProgramFilesX86 "Java\*"
    }

    foreach ($exact in @(
        "C:\\Program Files\\Android\\Android Studio\\jbr",
        "C:\\Program Files (x86)\\Android\\Android Studio\\jbr",
        "$env:LOCALAPPDATA\\Programs\\Android Studio\\jbr",
        "$env:LOCALAPPDATA\\Programs\\Android\\Android Studio\\jbr"
    )) {
        if (Test-Path $exact) {
            if (Test-Path (Join-Path $exact "bin\java.exe")) {
                return $exact
            }
        }
    }

    foreach ($pattern in $paths) {
        $cands = Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue
        foreach ($c in $cands) {
            $javaHome = $c.FullName
            if (Test-Path (Join-Path $javaHome "bin\java.exe")) {
                return $javaHome
            }
        }
    }

    $direct = Get-Command java -ErrorAction SilentlyContinue
    if ($direct) {
        $javaPath = $direct.Source
        $javaHomeGuess = Split-Path -Parent (Split-Path -Parent $javaPath)
        if (Test-Path (Join-Path $javaHomeGuess "bin\java.exe")) {
            return $javaHomeGuess
        }
    }

    return $null
}

if (-not $NoBuild) {
    $javaHome = Resolve-JavaHome
    if (-not $javaHome) {
        throw "JAVA_HOME not found and could not auto-discover Java. Please install JDK or set JAVA_HOME."
    }
    $env:JAVA_HOME = $javaHome
    if ($env:PATH -notmatch [regex]::Escape("$javaHome\bin")) {
        $env:PATH = "$javaHome\bin;" + $env:PATH
    }
}

if (-not $NoBuild) {
    Write-Host "Build: ./gradlew $Variant"
    & .\gradlew.bat $Variant
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle build failed, exit code: $LASTEXITCODE"
    }
}

$apkPath = Join-Path $projectRoot "app\\build\\outputs\\apk\\debug\\app-debug.apk"
if (-not (Test-Path $apkPath)) {
    throw "APK not found: $apkPath"
}

function Resolve-AdbPath {
    $fromCmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($fromCmd) {
        return $fromCmd.Source
    }

    $candidates = @()
    if ($env:ANDROID_HOME) {
        $candidates += Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    }
    if ($env:ANDROID_SDK_ROOT) {
        $candidates += Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe"
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    }
    $candidates += "C:\Android\Sdk\platform-tools\adb.exe"
    if ($env:APPDATA) {
        $candidates += Join-Path $env:APPDATA "Android\SDK\platform-tools\adb.exe"
    }

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    return $null
}

$adbPath = Resolve-AdbPath
if (-not $adbPath) {
    throw "adb not found. Install Android platform-tools and add adb to PATH."
}

Write-Host "Checking adb devices..."
$devicesOutput = & $adbPath devices
$lines = $devicesOutput -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch '^List of devices' }
if (-not $lines -or $lines.Count -eq 0) {
    throw "No adb devices detected. Connect your phone and authorize USB debugging."
}

$deviceSerial = $null
foreach ($line in $lines) {
    if ($line -match '^(.+)\s+device$') {
        $deviceSerial = $Matches[1]
        break
    }
}

if (-not $deviceSerial) {
    Write-Host "No ready device in adb list:"
    Write-Host $devicesOutput
    throw "No device in 'device' state (maybe unauthorized)."
}

Write-Host "Target device: $deviceSerial"
Write-Host "Installing APK..."
    & $adbPath -s $deviceSerial install -r "$apkPath"
if ($LASTEXITCODE -ne 0) {
    throw "APK install failed, exit code: $LASTEXITCODE"
}

Write-Host "Install complete: $apkPath"
Write-Host "Installed on: $deviceSerial"
