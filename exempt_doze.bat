@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Exempt self-built apps from Doze
echo   (watch + phone, all packages)
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0exempt_doze.ps1"
echo.
pause
