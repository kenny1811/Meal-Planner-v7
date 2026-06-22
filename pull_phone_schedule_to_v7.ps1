$ErrorActionPreference = 'Stop'

$adb = 'C:\Users\Kenny\AppData\Local\Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path $adb)) {
  Write-Host "adb not found: $adb"
  exit 1
}

$deviceLine = (& $adb devices | Select-String '^[^ \t]+\s+device$' | Select-Object -First 1)
if (-not $deviceLine) {
  Write-Host "not found any adb device online. please connect phone and allow adb."
  exit 1
}

$device = ($deviceLine.Line -split '\s+')[0]
$phoneXml = '/sdcard/Download/schedule_grid.xml'
$pcXml = Join-Path $PSScriptRoot 'schedule_grid.xml'

& $adb -s $device shell test -f $phoneXml | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "phone has no file: $phoneXml"
  exit 1
}

& $adb -s $device pull $phoneXml $pcXml
if ($LASTEXITCODE -ne 0) {
  Write-Host "pull failed"
  exit 1
}

Write-Host "pulled to: $pcXml"
