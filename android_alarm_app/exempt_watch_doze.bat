@echo off
setlocal
cd /d "%~dp0"
echo Exempting the watch alarm app from Doze / battery optimization...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0exempt_watch_doze.ps1"
echo.
pause
