# 已合併入 repo root 嘅 exempt_doze.ps1（同時處理手錶同電話、所有自製 app）。
# 保留呢個檔淨係為咗 exempt_watch_doze.bat 照用得；唔好喺呢度再複製一份名單。
& (Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)) "exempt_doze.ps1")
