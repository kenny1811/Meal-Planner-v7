$ErrorActionPreference = "Continue"
$appDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$trigger = Join-Path $appDir ".autobuild_trigger"
$phone   = Join-Path $appDir "build_and_install_phone.ps1"
$watch   = Join-Path $appDir "build_and_install_watch.ps1"

if (-not (Test-Path $trigger)) { Set-Content -Path $trigger -Value "init" -NoNewline }
$last = Get-Content -Path $trigger -Raw -ErrorAction SilentlyContinue

Write-Host "============================================"
Write-Host "  Auto build+install watcher (phone + watch)"
Write-Host "============================================"
Write-Host "Watching trigger: $trigger"
Write-Host "Keep phone + watch connected via adb; leave this window open."
Write-Host "It auto-builds+installs whenever Claude finishes a change."
Write-Host "Ctrl+C to stop."
Write-Host ""

while ($true) {
    Start-Sleep -Seconds 5
    $cur = Get-Content -Path $trigger -Raw -ErrorAction SilentlyContinue
    if ($cur -and $cur -ne $last) {
        $last = $cur
        Write-Host ""
        Write-Host ("=== Change detected ({0}) -> build + install ===" -f (Get-Date -Format "HH:mm:ss"))
        Write-Host "--- Phone ---"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $phone
        Write-Host "--- Watch ---"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $watch
        Write-Host ("=== Done ({0}). Waiting for next change... ===" -f (Get-Date -Format "HH:mm:ss"))
    }
}
