"""Atomic file writes.

直接 `Path.write_text()` 係先 truncate 後寫；寫到一半被 `taskkill /F` 或停電，
檔案就會剩返半截（config.yaml 殘缺 = server 起唔返）。呢度統一用
「寫去同一個資料夾嘅 .tmp → fsync → os.replace 換名」，
`os.replace` 喺 Windows 同 POSIX 都係原子操作，所以讀嗰邊永遠只會見到
「舊嘅完整版」或者「新嘅完整版」，唔會見到半截。
"""

from __future__ import annotations

import os
from pathlib import Path


def _replace_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """`Path.write_bytes()` 嘅原子版本。"""
    _replace_atomically(path, data)


def write_text_atomic(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """`Path.write_text()` 嘅原子版本；預設 UTF-8 + LF，唔會被 Windows 轉 CRLF。"""
    if newline != "\n":
        text = text.replace("\n", newline)
    _replace_atomically(path, text.encode(encoding))
