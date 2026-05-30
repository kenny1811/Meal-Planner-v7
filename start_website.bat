@echo off
setlocal

set "ROOT=%~dp0"
set "MENU_API_HOST=127.0.0.1"
set "MENU_PROJECT_ROOT=%ROOT%"
if "%MENU_API_PORT%"=="" set "MENU_API_PORT=8765"

start "Meal Planner Server v6" cmd /k "cd /d ""%ROOT%"" && set ""MENU_PROJECT_ROOT=%ROOT%"" && python -m meal_planner.app"

timeout /t 3 /nobreak >nul
start "" "http://%MENU_API_HOST%:%MENU_API_PORT%/?v=v6-%RANDOM%-%RANDOM%"

endlocal
