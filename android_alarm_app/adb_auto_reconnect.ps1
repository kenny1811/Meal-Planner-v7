# Keeps the phone's adb-over-WiFi (port 5555) alive with zero manual steps on the PC side.
# Runs from Task Scheduler every 5 minutes; the task's action is adb_auto_reconnect.vbs
# (wscript runs windowless, so no console flashes).
#
# Recovery ladder when the phone is offline:
#   1. adb connect meshnet/LAN :5555 (normal case: PC rebooted or adb server restarted)
#   2. USB: if the phone is plugged in, re-arm tcpip 5555 through the cable
#   3. mDNS: if Wireless debugging is toggled on, discover its rotating port,
#      connect through it, then re-arm tcpip 5555 (user never needs to read the port)
#
# The only thing the script cannot do is start adbd after a phone reboot -
# Android requires either a USB plug-in or the Wireless debugging toggle for that.

. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "..\adb_common.ps1")

$Adb = Resolve-AdbPath
if (-not $Adb) { exit 0 }   # 搵唔到 adb 就靜靜退出，唔好每 5 分鐘寫一次 log
$Targets = @("100.78.27.188:5555", "192.168.15.102:5555")
$PhoneLanIp = "192.168.15.102"
$LogPath = Join-Path $PSScriptRoot "adb_auto_reconnect.log"

function Write-Log($Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$stamp] $Message"
}

function Get-DeviceLines {
    (& $Adb devices) -split "`r?`n" | Select-Object -Skip 1 | Where-Object { $_ -match "\S" }
}

function Test-PhoneOnline {
    $lines = Get-DeviceLines
    foreach ($t in $Targets) {
        if ($lines | Where-Object { $_ -match ([regex]::Escape($t) + "\s+device") }) { return $true }
    }
    return $false
}

function Connect-Targets {
    foreach ($t in $Targets) { & $Adb connect $t 2>$null | Out-Null }
}

function Invoke-RecoveryLadder {
    Connect-Targets
    if (Test-PhoneOnline) { Write-Log "Reconnected via :5555."; return $true }

    # --- USB fallback: any online device without an IP-style serial is a cable ---
    $usbSerial = Get-DeviceLines |
        Where-Object { $_ -match "^\S+\s+device" -and $_ -notmatch ":" } |
        ForEach-Object { ($_ -split "\s+")[0] } |
        Select-Object -First 1
    if ($usbSerial) {
        & $Adb -s $usbSerial tcpip 5555 2>$null | Out-Null
        Start-Sleep -Seconds 3
        Connect-Targets
        if (Test-PhoneOnline) { Write-Log "Re-armed 5555 via USB ($usbSerial)."; return $true }
    }

    # --- mDNS fallback: Wireless debugging advertises _adb-tls-connect on a rotating port ---
    $services = & $Adb mdns services 2>$null
    $candidate = $services | Where-Object {
        $_ -match "_adb-tls-connect" -and $_ -match [regex]::Escape($PhoneLanIp)
    } | Select-Object -First 1
    if ($candidate -and $candidate -match "$([regex]::Escape($PhoneLanIp)):(\d+)") {
        $wirelessPort = $Matches[1]
        & $Adb connect "${PhoneLanIp}:$wirelessPort" 2>$null | Out-Null
        Start-Sleep -Seconds 2
        $viaWireless = Get-DeviceLines | Where-Object {
            $_ -match ([regex]::Escape("${PhoneLanIp}:$wirelessPort") + "\s+device")
        }
        if ($viaWireless) {
            & $Adb -s "${PhoneLanIp}:$wirelessPort" tcpip 5555 2>$null | Out-Null
            Start-Sleep -Seconds 3
            Connect-Targets
            if (Test-PhoneOnline) { Write-Log "Re-armed 5555 via wireless debugging port $wirelessPort."; return $true }
        }
    }
    return $false
}

if (Test-PhoneOnline) { exit 0 }

# Retry inside one run so the at-logon launch keeps trying while the network
# (WiFi/meshnet) is still coming up, instead of waiting for the next 5-min tick.
for ($attempt = 0; $attempt -lt 8; $attempt++) {
    if ($attempt -gt 0) { Start-Sleep -Seconds 15 }
    if (Invoke-RecoveryLadder) { exit 0 }
}

exit 0
