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

rem hidden 啟動（唔再彈 cmd 視窗）；env 由本 bat 繼承落 python。log 要睇就用 start_website.bat 或手動行。
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-m','meal_planner.app') -WorkingDirectory '%ROOT%'"

echo Restarted Meal Planner Server v7 on http://%MENU_API_HOST%:%MENU_API_PORT%/
echo Browser tab was not opened.

endlocal
