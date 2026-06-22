@echo off
setlocal

set "ROOT=%~dp0"
set "APP=start_website.bat"
set "KEY=HKCU\Software\Classes\mealplanner"

reg add "%KEY%" /ve /d "URL:Meal Planner v7" /f >nul
reg add "%KEY%" /v "URL Protocol" /d "" /f >nul
reg add "%KEY%\DefaultIcon" /ve /d "%ROOT%%APP%,0" /f >nul
reg add "%KEY%\shell\open\command" /ve /d "\"%ROOT%%APP%\" \"%%1\"" /f >nul

echo Registered mealplanner:// protocol for Meal Planner v7.
echo.
echo Add this URL as a Chrome bookmark:
echo mealplanner://open
echo.
pause
