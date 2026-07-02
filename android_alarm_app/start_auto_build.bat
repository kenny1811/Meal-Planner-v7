@echo off
setlocal
cd /d "%~dp0"
echo Starting auto build+install watcher...
echo Leave this window OPEN. Keep phone + watch connected via adb.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto_build_watcher.ps1"
echo.
echo Watcher stopped.
pause
