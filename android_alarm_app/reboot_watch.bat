@echo off
setlocal
cd /d "%~dp0"
echo Rebooting the watch (auto-detected)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reboot_watch.ps1"
echo.
pause
