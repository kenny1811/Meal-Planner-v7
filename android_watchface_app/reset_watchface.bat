@echo off
setlocal
cd /d "%~dp0"
echo CLEAN reinstall of the Kenny watch face (resets complication slots).
echo After it finishes: re-select the Kenny watch face on the watch.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_watchface.ps1" -Clean
echo.
pause
