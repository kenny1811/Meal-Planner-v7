@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Update One Shot Alarm - Watch (Wear) App
echo ============================================
echo.
echo Building and installing to the watch...
echo (auto-detects the Wear device; will ask if unsure)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_and_install_watch.ps1"
set RC=%ERRORLEVEL%
echo.
echo ============================================
if "%RC%"=="0" (
  echo   DONE - watch app updated successfully.
) else (
  echo   FAILED - see messages above. Exit code: %RC%
)
echo ============================================
echo.
pause
