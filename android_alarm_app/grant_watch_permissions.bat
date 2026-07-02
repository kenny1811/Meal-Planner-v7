@echo off
setlocal
cd /d "%~dp0"
echo Restoring watch alarm permissions (overlay + notifications)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0grant_watch_permissions.ps1"
echo.
pause
