@echo off
setlocal

set "ROOT=%~dp0"
rem 0.0.0.0 = 同時聽 LAN 同 Tailscale；瀏覽器仍用 http://192.168.15.125:8765/
set "MENU_API_HOST=0.0.0.0"
set "MENU_PROJECT_ROOT=%ROOT%"
if "%MENU_API_PORT%"=="" set "MENU_API_PORT=8765"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '%ROOT%').Path.TrimEnd('\');" ^
  "$port = [int]'%MENU_API_PORT%';" ^
  "$needle = '-m meal_planner.app';" ^
  "$targetPids = @();" ^
  "$targetPids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $needle + '*') } | ForEach-Object { $_.ProcessId };" ^
  "$targetPids += Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess };" ^
  "$targetPids | Sort-Object -Unique | Where-Object { $_ -and $_ -ne $PID } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

timeout /t 1 /nobreak >nul

start "Meal Planner Server v7" cmd /k "cd /d ""%ROOT%"" && set ""MENU_PROJECT_ROOT=%ROOT%"" && set ""MENU_API_HOST=%MENU_API_HOST%"" && set ""MENU_API_PORT=%MENU_API_PORT%"" && python -m meal_planner.app"

echo Restarted Meal Planner Server v7 on http://%MENU_API_HOST%:%MENU_API_PORT%/
echo Browser tab was not opened.

endlocal
