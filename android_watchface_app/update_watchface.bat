@echo off
setlocal
cd /d "%~dp0"
echo Building + installing (keep data) the Kenny watch face...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_watchface.ps1"
echo.
pause
