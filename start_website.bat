@echo off
setlocal

set "ROOT=%~dp0"
set "MENU_API_HOST=192.168.15.125"
set "MENU_PROJECT_ROOT=%ROOT%"
if "%MENU_API_PORT%"=="" set "MENU_API_PORT=8765"
set "MENU_URL=http://%MENU_API_HOST%:%MENU_API_PORT%"
set "PYTHON_EXE=C:\Users\Kenny\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$want = (Resolve-Path '%ROOT%').Path.TrimEnd('\'); $hostIp = '%MENU_API_HOST%'; $port = [int]'%MENU_API_PORT%'; $lanUrl = 'http://%MENU_API_HOST%:%MENU_API_PORT%/api/health'; function Get-Utf8Json($url) { $wc = New-Object System.Net.WebClient; $bytes = $wc.DownloadData($url); [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json }; function Test-Health($url) { try { $r = Get-Utf8Json $url; $got = ([string]$r.project_root).TrimEnd('\'); if ($r.status -eq 'ok' -and $got -ieq $want) { return $true } } catch { return $false }; return $false }; function Test-ExpectedListener { $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -eq $hostIp }); return $listeners.Count -gt 0 }; function Test-Ready { return ((Test-ExpectedListener) -and (Test-Health $lanUrl)) }; function Stop-MealPlannerServer { $targetPids = @(); $targetPids += Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*.exe') -and ($_.CommandLine -like '*-m meal_planner.app*') } | ForEach-Object { $_.ProcessId }; $targetPids += Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }; $targetPids | Sort-Object -Unique | Where-Object { $_ -and $_ -ne $PID } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }; if (-not (Test-Ready)) { Stop-MealPlannerServer; Start-Sleep -Milliseconds 350; Start-Process -WindowStyle Hidden -FilePath '%PYTHON_EXE%' -ArgumentList @('-m','meal_planner.app') -WorkingDirectory '%ROOT%' >$null 2>$null }; for ($i=0; $i -lt 40; $i++) { if (Test-Ready) { exit 0 }; Start-Sleep -Milliseconds 250 }; exit 1" >nul 2>nul
if errorlevel 1 exit /b 1

:open_site
start "" "%MENU_URL%/?v=v7-%RANDOM%-%RANDOM%"
exit /b 0

endlocal
