@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pull_phone_schedule_to_v7.ps1"
exit /b %errorlevel%
