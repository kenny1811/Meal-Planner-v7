"""釋放本機 TCP 埠：終止正在 Listen 嘅程序（主要支援 Windows）。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Iterable


def _parse_int_lines(text: str) -> set[int]:
    out: set[int] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.add(int(line))
        except ValueError:
            continue
    return out


def pids_listening_on_port_windows(port: int) -> set[int]:
    """搵 Listen 緊指定埠嘅 OwningProcess。

    `Get-NetTCPConnection` 在部份 Windows 環境會間歇性卡住，所以啟動流程優先用
    `netstat -ano`，避免因為查 port 超時而令網站起唔到。
    """
    port_i = int(port)
    pids = _pids_listening_on_port_windows_netstat(port_i)
    if pids:
        return pids
    if os.environ.get("MENU_API_USE_POWERSHELL_PORT_CHECK", "").strip().lower() not in ("1", "true", "yes"):
        return set()
    ps = (
        f"$c = Get-NetTCPConnection -LocalPort {port_i} -State Listen -ErrorAction SilentlyContinue; "
        r"$c | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return set()
    if r.returncode == 0:
        return _parse_int_lines(r.stdout)
    return set()


def _pids_listening_on_port_windows_netstat(port: int) -> set[int]:
    out: set[int] = set()
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return out
    if r.returncode != 0:
        return out
    needle = f":{int(port)}"
    for raw in r.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        # 典型格式：Proto LocalAddress ForeignAddress State PID
        local_addr = parts[1]
        state = parts[3].upper()
        pid_s = parts[4]
        if state != "LISTENING":
            continue
        if not local_addr.endswith(needle):
            continue
        try:
            out.add(int(pid_s))
        except ValueError:
            continue
    return out


def kill_pids(pids: Iterable[int], *, force: bool = True) -> list[tuple[int, bool, str]]:
    """Windows：`taskkill`。回傳 [(pid, ok, message), ...]。"""
    out: list[tuple[int, bool, str]] = []
    for pid in pids:
        if pid <= 0:
            continue
        args = ["taskkill", "/PID", str(pid), "/F"] if force else ["taskkill", "/PID", str(pid)]
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        msg = (r.stdout or "") + (r.stderr or "")
        msg = msg.strip() or f"exit {r.returncode}"
        out.append((pid, r.returncode == 0, msg))
    return out


def free_tcp_port(port: int) -> list[int]:
    """
    終止所有喺 `port` 上 TCP Listen 嘅程序（唔會殺自己個 PID）。
    回傳已嘗試終止嘅 PID 清單（成功與否由 log 另睇）。
    """
    if os.environ.get("MENU_API_NO_KILL", "").strip() in ("1", "true", "yes"):
        return []

    my = os.getpid()
    if sys.platform != "win32":
        return []

    killed: list[int] = []
    # 做幾輪，減少 race condition（程序剛釋放/剛建立 listen）造成的漏殺。
    for _ in range(3):
        try:
            pids = pids_listening_on_port_windows(port) - {my}
        except Exception as ex:
            print(f"[meal_planner] 查詢埠 {port} 佔用程序失敗，略過自動釋放：{ex}", file=sys.stderr)
            break
        if not pids:
            break
        for pid, ok, msg in kill_pids(sorted(pids)):
            killed.append(pid)
            if ok:
                print(f"[meal_planner] 已終止佔用埠 {port} 的程序 PID={pid}。", file=sys.stderr)
            else:
                print(f"[meal_planner] 無法終止 PID={pid}：{msg}", file=sys.stderr)
        time.sleep(0.35)
    return killed
