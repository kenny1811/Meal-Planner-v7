param(
    [string]$ProjectRoot = $PSScriptRoot,
    [int]$Port = 0,
    [string]$ServerModule = 'meal_planner.app',
    [int]$PollSeconds = 5,
    [int]$StartupTimeoutSeconds = 180,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
if (-not $Port) { $Port = if ($env:MENU_API_PORT) { [int]$env:MENU_API_PORT } else { 8765 } }
$env:MENU_API_HOST = '0.0.0.0'
$env:MENU_API_PORT = [string]$Port
$env:MENU_PROJECT_ROOT = $Root
# If a different launcher wins the bind race, never evict its running server.
$env:MENU_API_NO_KILL = '1'
# Loopback supervision is independent of LAN / VPN interface availability.
$HealthUrl = "http://127.0.0.1:$Port/api/health"
$PythonExe = 'C:\Users\Kenny\AppData\Local\Programs\Python\Python313\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = 'python.exe' }
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogPath = Join-Path $LogDir 'server_autostart.log'
$RestartPath = Join-Path $LogDir "server-$Port.restart"
$sha = [Security.Cryptography.SHA256]::Create()
$key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes("$($Root.ToLowerInvariant()):$Port"))).Replace('-', '')
$sha.Dispose()
$mutex = New-Object Threading.Mutex($false, "Global\MealPlannerServer-$key")
if ($Restart) { [IO.File]::WriteAllText($RestartPath, [DateTime]::UtcNow.ToString('o')) }
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); exit 0 }

function Write-StartupLog([string]$Message) {
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}
function Test-MealPlannerHealth {
    try {
        $request = [Net.HttpWebRequest]::Create($HealthUrl)
        $request.Proxy = $null; $request.Timeout = 3000; $request.ReadWriteTimeout = 3000
        $response = $request.GetResponse()
        try {
            $reader = New-Object IO.StreamReader($response.GetResponseStream(), [Text.Encoding]::UTF8)
            try { $data = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            return ($data.status -eq 'ok' -and ([string]$data.project_root).TrimEnd('\') -ieq $Root)
        } finally { $response.Dispose() }
    } catch { return $false }
}
function Get-ListenerPid {
    foreach ($line in (& netstat.exe -ano -p tcp)) {
        $parts = $line.Trim() -split '\s+'
        if ($parts.Count -ge 5 -and $parts[0] -eq 'TCP' -and $parts[1] -match ":$Port`$" -and $parts[3] -eq 'LISTENING') { return [int]$parts[4] }
    }
    return 0
}
$server = $null; $owned = $false; $startedAt = $null; $wasReady = $false
$warning = ''; $failures = 0; $nextStart = [DateTime]::MinValue
try {
    Write-StartupLog "Supervisor PID $PID started for $HealthUrl; root=$Root."
    while ($true) {
        try {
            $healthy = Test-MealPlannerHealth
            if ($server) {
                $server.Refresh()
                if ($server.HasExited) {
                    $exitCode = 'unknown (attached process)'
                    if ($owned) { $exitCode = [string]$server.ExitCode }
                    Write-StartupLog "Server PID $($server.Id) exited; exit code=$exitCode. Automatic recovery pending."
                    $server.Dispose(); $server = $null; $owned = $false; $wasReady = $false
                    $failures++
                    $nextStart = [DateTime]::UtcNow.AddSeconds([Math]::Min(60, [Math]::Pow(2, [Math]::Min($failures, 6))))
                }
            }
            if ($healthy -and -not $server) {
                $listenerPid = Get-ListenerPid
                if ($listenerPid) {
                    $server = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
                    if ($server) {
                        # Retain a handle so PID reuse cannot become our restart target.
                        $null = $server.Handle
                        Write-StartupLog "Attached to healthy server PID $listenerPid without restarting it."
                    }
                }
            }
            if (Test-Path -LiteralPath $RestartPath) {
                Remove-Item -LiteralPath $RestartPath
                if ($server -and ($owned -or $healthy)) {
                    Write-StartupLog "Manual restart requested for server PID $($server.Id)."
                    $server.Kill(); $server.WaitForExit(10000) | Out-Null
                    $server.Dispose(); $server = $null; $owned = $false; $wasReady = $false
                    $healthy = $false; $nextStart = [DateTime]::MinValue
                } else { Write-StartupLog 'Manual restart requested; no verified server to stop.' }
            }
            if ($healthy) {
                if (-not $wasReady) { Write-StartupLog 'Meal Planner server is ready; continuous supervision active.' }
                $wasReady = $true; $warning = ''; $failures = 0
            } elseif ($server) {
                # A slow health request during reporting must not cause a restart.
                if ($owned -and -not $wasReady -and ([DateTime]::UtcNow - $startedAt).TotalSeconds -gt $StartupTimeoutSeconds) {
                    Write-StartupLog "Server PID $($server.Id) failed initial readiness after $StartupTimeoutSeconds seconds; stopping newly launched child."
                    $server.Kill()
                } elseif ($warning -ne 'unhealthy') {
                    Write-StartupLog "Health check unavailable; server PID $($server.Id) still running. Leaving it running and checking again."
                    $warning = 'unhealthy'
                }
            } elseif ([DateTime]::UtcNow -ge $nextStart) {
                $listenerPid = Get-ListenerPid
                if ($listenerPid) {
                    if ($warning -ne 'occupied') { Write-StartupLog "Port $Port occupied by PID $listenerPid but project health not verified; leaving it untouched."; $warning = 'occupied' }
                } else {
                    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
                    $stdout = Join-Path $LogDir "server-$Port-$stamp.stdout.log"
                    $stderr = Join-Path $LogDir "server-$Port-$stamp.stderr.log"
                    $server = Start-Process -WindowStyle Hidden -FilePath $PythonExe -ArgumentList @('-u', '-m', $ServerModule) -WorkingDirectory $Root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
                    $null = $server.Handle
                    $owned = $true; $startedAt = [DateTime]::UtcNow; $wasReady = $false; $warning = ''
                    Write-StartupLog "Started server PID $($server.Id); stdout=$stdout; stderr=$stderr."
                }
            }
        } catch {
            Write-StartupLog "Supervisor check failed: $($_.Exception.Message). Retrying; existing server left running."
            $nextStart = [DateTime]::UtcNow.AddSeconds(10)
        }
        Start-Sleep -Seconds $PollSeconds
    }
} finally {
    if ($server) { $server.Dispose() }
    $mutex.ReleaseMutex(); $mutex.Dispose()
}
