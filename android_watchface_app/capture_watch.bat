@echo off
setlocal
cd /d "%~dp0"
echo Capturing the watch screen...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0capture_watch.ps1"
echo.
pause
