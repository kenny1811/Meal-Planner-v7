@echo off
setlocal

set "ROOT=%~dp0"
set "MENU_API_HOST=127.0.0.1"
set "MENU_PROJECT_ROOT=%ROOT%"
if "%MENU_API_PORT%"=="" set "MENU_API_PORT=8765"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '%ROOT%').Path.TrimEnd('\');" ^
  "$needle = '-m meal_planner.app';" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $needle + '*') -and $_.CommandLine -like ('*' + $root + '*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

timeout /t 1 /nobreak >nul

start "Meal Planner Server v6" cmd /k "cd /d ""%ROOT%"" && set ""MENU_PROJECT_ROOT=%ROOT%"" && set ""MENU_API_HOST=%MENU_API_HOST%"" && set ""MENU_API_PORT=%MENU_API_PORT%"" && python -m meal_planner.app"

echo Restarted Meal Planner Server v6 on http://%MENU_API_HOST%:%MENU_API_PORT%/
echo Browser tab was not opened.

endlocal
