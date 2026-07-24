"""時間解析 + 30 小時制換算——全 project 得呢一份，唔好喺其他模組自己寫 parser。

30 小時制：凌晨 00:00–05:59 當前一日嘅 24:00–29:59（規則見 CLAUDE.md）。
呢個約定嘅換算全部集中喺 business_date / slot_datetime / minutes_30h，
唔好喺 caller 自己 +/- 6 小時。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
_COMPACT_TIME_RE = re.compile(r"^\s*(\d{1,2})(\d{2})\s*$")


def parse_time(value: Any) -> time | None:
    """時間值 → time；接受 time/datetime/"HH:MM"/"HH:MM:SS"/"HHMM"，無效回 None。"""
    if isinstance(value, time):
        return time(value.hour, value.minute)
    if isinstance(value, datetime):
        return time(value.hour, value.minute)
    raw = str(value or "")
    match = _TIME_RE.match(raw) or _COMPACT_TIME_RE.match(raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def cell_text(value: Any) -> str | None:
    """儲存格值 → 顯示文字；time/datetime 一律 HH:MM，空白回 None。"""
    if value is None:
        return None
    if isinstance(value, (time, datetime)):
        return value.strftime("%H:%M")
    text = str(value).strip()
    return text or None


def to_minutes(value: Any) -> int:
    """時間值 → 由 00:00 起計嘅分鐘；無效回 -1。"""
    t = parse_time(value)
    return -1 if t is None else t.hour * 60 + t.minute


def minutes_30h(value: Any) -> int:
    """時間值 → 30 小時制分鐘（00:00–05:59 當 24:00–29:59）。無效即 raise。"""
    t = parse_time(value)
    if t is None:
        raise ValueError(f"invalid time: {value!r}")
    m = t.hour * 60 + t.minute
    return m + 1440 if t.hour < 6 else m


def normalize_hhmm(text: str) -> str:
    """時間輸入寬鬆化：'9:16'/'09:16'/'916'/'0916' 都收；
    30 小時制 24:00–29:59（或 2416 咁）轉成 00:00–05:59（即聽日凌晨）。無效回 ''。"""
    token = str(text or "").strip()
    match = _TIME_RE.match(token) or _COMPACT_TIME_RE.match(token)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if 24 <= hour <= 29:
        hour -= 24
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def business_date(now: datetime) -> date:
    """00:00–05:59 當前一日（30 小時制）。"""
    return (now - timedelta(hours=6)).date()


def slot_datetime(biz_date: date, hhmm: str, tz: ZoneInfo) -> datetime:
    """slot 實際時刻：06:00 前嘅時間屬 30 小時制「翌日凌晨」。"""
    minutes = to_minutes(hhmm)
    if minutes < 0:
        minutes = 0
    d = biz_date if minutes >= 6 * 60 else biz_date + timedelta(days=1)
    return datetime.combine(d, time(minutes // 60, minutes % 60), tzinfo=tz)
