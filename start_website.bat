@echo off
setlocal
set "MEAL_SERVER_SCRIPT=%~dp0start_server_hidden.ps1"
if "%MENU_API_PORT%"=="" set "MENU_API_PORT=8765"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('\"' + $env:MEAL_SERVER_SCRIPT + '\"')); $want = (Split-Path -Parent $env:MEAL_SERVER_SCRIPT).TrimEnd('\'); for ($i=0; $i -lt 60; $i++) { try { $req = [Net.HttpWebRequest]::Create('http://127.0.0.1:' + $env:MENU_API_PORT + '/api/health'); $req.Proxy = $null; $req.Timeout = 2000; $req.ReadWriteTimeout = 2000; $response = $req.GetResponse(); try { $reader = New-Object IO.StreamReader($response.GetResponseStream(), [Text.Encoding]::UTF8); try { $r = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() } } finally { $response.Dispose() }; if ($r.status -eq 'ok' -and ([string]$r.project_root).TrimEnd('\') -ieq $want) { exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 exit /b 1
start "" "http://192.168.15.125:%MENU_API_PORT%/?v=v7-%RANDOM%-%RANDOM%"
endlocal
