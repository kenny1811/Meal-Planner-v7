@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Update One Shot Alarm - Phone App
echo ============================================
echo.
echo Building and installing to the connected phone...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_and_install_phone.ps1"
set RC=%ERRORLEVEL%
echo.
echo ============================================
if "%RC%"=="0" (
  echo   DONE - phone app updated successfully.
) else (
  echo   FAILED - see messages above. Exit code: %RC%
)
echo ============================================
echo.
pause
