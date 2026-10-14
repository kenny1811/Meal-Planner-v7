@echo off
setlocal
set "MEAL_SERVER_SCRIPT=%~dp0start_server_hidden.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('\"' + $env:MEAL_SERVER_SCRIPT + '\"'),'-Restart')"
if errorlevel 1 exit /b 1
echo Meal Planner restart requested. Automatic recovery stays active.
endlocal
