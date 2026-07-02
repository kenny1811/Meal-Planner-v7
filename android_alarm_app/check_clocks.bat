@echo off
setlocal
cd /d "%~dp0"
echo Comparing phone vs watch clocks...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_clocks.ps1"
echo.
pause
