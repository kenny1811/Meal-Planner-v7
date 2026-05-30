@echo off
setlocal

reg delete "HKCU\Software\Classes\mealplanner" /f >nul 2>nul

echo Unregistered mealplanner:// protocol.
echo.
pause
