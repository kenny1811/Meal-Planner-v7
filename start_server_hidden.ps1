$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:MENU_API_HOST = "192.168.15.125"
$env:MENU_PROJECT_ROOT = $Root
if (-not $env:MENU_API_PORT) {
    $env:MENU_API_PORT = "8765"
}

$HostIp = $env:MENU_API_HOST
$Port = [int]$env:MENU_API_PORT
$HealthUrl = "http://${HostIp}:$Port/api/health"
$PythonExe = "C:\Users\Kenny\AppData\Local\Programs\Python\Python313\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python.exe"
}

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogPath = Join-Path $LogDir "server_autostart.log"

function Write-StartupLog($Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$stamp] $Message"
}

function Test-MealPlannerHealth {
    try {
        $webClient = New-Object System.Net.WebClient
        $webClient.Encoding = [System.Text.Encoding]::UTF8
        $response = $webClient.DownloadString($HealthUrl) | ConvertFrom-Json
        $expectedRoot = (Resolve-Path -LiteralPath $Root).Path.TrimEnd("\")
        $actualRoot = ([string]$response.project_root).TrimEnd("\")
        return ($response.status -eq "ok" -and $actualRoot -ieq $expectedRoot)
    } catch {
        return $false
    }
}

function Test-ExpectedListener {
    $listeners = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq $HostIp }
    )
    return $listeners.Count -gt 0
}

function Test-Ready {
    return ((Test-ExpectedListener) -and (Test-MealPlannerHealth))
}

function Test-HostIpAvailable {
    $address = Get-NetIPAddress -IPAddress $HostIp -ErrorAction SilentlyContinue
    return ($null -ne $address)
}

function Stop-MealPlannerServer {
    $targetPids = @()
    $targetPids += Get-CimInstance Win32_Process |
        Where-Object { ($_.Name -like "python*.exe") -and ($_.CommandLine -like "*-m meal_planner.app*") } |
        ForEach-Object { $_.ProcessId }
    $targetPids += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { $_.OwningProcess }

    $targetPids |
        Sort-Object -Unique |
        Where-Object { $_ -and $_ -ne $PID } |
        ForEach-Object {
            Write-StartupLog "Stopping existing process PID $_ on port $Port."
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}

Write-StartupLog "Startup check begin for $HealthUrl."

for ($i = 0; $i -lt 90; $i++) {
    if (Test-HostIpAvailable) {
        break
    }
    if (($i + 1) % 15 -eq 0) {
        Write-StartupLog "Still waiting for local IP $HostIp."
    }
    Start-Sleep -Seconds 2
}

if (-not (Test-HostIpAvailable)) {
    Write-StartupLog "Local IP $HostIp was not available; server was not started."
    exit 1
}

if (-not (Test-Ready)) {
    Stop-MealPlannerServer
    Start-Sleep -Seconds 2
    Write-StartupLog "Starting Meal Planner server with $PythonExe."
    Start-Process -WindowStyle Hidden -FilePath $PythonExe -ArgumentList @("-m", "meal_planner.app") -WorkingDirectory $Root | Out-Null
}

for ($i = 0; $i -lt 180; $i++) {
    if (Test-Ready) {
        Write-StartupLog "Meal Planner server is ready."
        exit 0
    }
    if (($i + 1) % 15 -eq 0) {
        Write-StartupLog "Still waiting for Meal Planner server readiness."
    }
    Start-Sleep -Seconds 1
}

Write-StartupLog "Meal Planner server did not become ready within 180 seconds."
exit 1
