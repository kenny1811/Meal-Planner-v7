@echo off
setlocal

reg delete "HKCU\Software\Classes\mealplanner" /f >nul 2>nul

echo Unregistered mealplanner:// protocol for Meal Planner v7.
echo.
pause
