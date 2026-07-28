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
    """時間值 → time；接受 time/datetime/"HH:MM"/"HH:MM:SS"/"HHMM"，無效回 None。

    30 小時制寫法（24:00–29:59）照收，換返做真正嘅鐘點（27:56 → 03:56）——
    「屬前一日」呢個意思由 business_date / minutes_30h 嗰邊表達，唔靠 time 本身。
    """
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
    if 24 <= hour <= 29:
        hour -= 24
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
    """時間輸入寬鬆化：'9:16'/'09:16'/'916'/'0916' 都收；無效回 ''。

    出返嚟一律 30 小時制：00:00–05:59 寫成 24:00–29:59（全 project 都係咁存同咁顯示，
    唔會有兩個寫法指同一個鐘點）。
    """
    token = str(text or "").strip()
    match = _TIME_RE.match(token) or _COMPACT_TIME_RE.match(token)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if minute > 59 or hour > 29:
        return ""
    if hour < 6:
        hour += 24
    return f"{hour:02d}:{minute:02d}"


def hhmm30(value: Any) -> str:
    """時間值 → 30 小時制顯示文字（03:56 → 27:56）；無效回 ''。"""
    t = parse_time(value)
    if t is None:
        return ""
    return f"{t.hour + 24 if t.hour < 6 else t.hour:02d}:{t.minute:02d}"


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
