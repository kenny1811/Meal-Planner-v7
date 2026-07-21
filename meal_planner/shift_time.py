"""更時表（payroll_times）共用解讀邏輯 — Google Calendar sync 同報開工 form 都用呢一份。

解析規則（**唔用**優先序欄；「星期」同「每日」喺正常資料唔會並存，所以 2/3 次序無影響）：
  1. 嗰日係公眾假期 → 用「適用日=公眾假期」嗰行
  2. 再搵 match 到今日星期字（一二三四五六日）嘅行
  3. 再搵「每日」（或適用日留空）嘅行
  搵唔到 → (None, None)。邊啲更碼會有日子搵唔到（例如公司將 IFCS1/IFCS2
  分開兩個更碼），由儲存更時表時嘅 coverage 檢查負責出 warning
  （見 payroll_coverage_issues），唔喺呢度靜靜哋亂揀。

更時表欄位：更碼 | 開始時間 | 結束時間 | 適用日 |（優先序 — 已廢棄，忽略）
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from meal_planner.schedule_grid import _to_date, grid_row_matches_roster

# Mon=0 .. Sun=6 → 更時表「適用日」用嘅星期字。
WEEKDAY_CHAR = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
_ALL_WEEKDAY_CHARS = "日一二三四五六"

_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
_COMPACT_TIME_RE = re.compile(r"^\s*(\d{1,2})(\d{2})\s*$")


def parse_time(value: Any) -> time | None:
    """時間格仔 → time；接受 time/datetime/"HH:MM"/"HH:MM:SS"/"HHMM"。"""
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


def holiday_dates_from_rows(rows: list[Any] | None) -> set[date]:
    """公眾假期表 rows → 日期 set（第一欄係日期，首行係 header）。"""
    out: set[date] = set()
    for row in (rows or [])[1:]:
        if not isinstance(row, list) or not row:
            continue
        d = _to_date(row[0])
        if d is not None:
            out.add(d)
    return out


def _payroll_cands(
    payroll_rows: list[list[Any]] | None, roster_code: str
) -> list[tuple[time, time, str]]:
    """該更碼喺更時表所有有效行（開始/結束時間齊）→ [(start, end, 適用日)]。"""
    cands: list[tuple[time, time, str]] = []
    for row in (payroll_rows or [])[1:]:
        if not isinstance(row, list) or not row:
            continue
        code = str(row[0] or "").strip()
        if not grid_row_matches_roster(code, roster_code):
            continue
        start = parse_time(row[1] if len(row) > 1 else None)
        end = parse_time(row[2] if len(row) > 2 else None)
        if start is None or end is None:
            continue
        applies = str(row[3] or "").strip() if len(row) > 3 else ""
        cands.append((start, end, applies))
    return cands


def resolve_shift_time(
    payroll_rows: list[list[Any]] | None,
    roster_code: str,
    biz_date: date,
    holidays: set[date],
    overtime_by_date: dict[date, tuple[time | None, time | None]] | None = None,
) -> tuple[time | None, time | None]:
    """更時表按適用日揀開工/收工，再套加班表 override。攞唔到回 (None, None)。"""
    cands = _payroll_cands(payroll_rows, roster_code)
    weekday_char = WEEKDAY_CHAR[biz_date.weekday()]
    picked: tuple[time, time, str] | None = None
    if biz_date in holidays:
        picked = next((c for c in cands if c[2] == "公眾假期"), None)
    if picked is None:
        picked = next(
            (c for c in cands if c[2] not in ("", "每日", "公眾假期") and weekday_char in c[2]),
            None,
        )
    if picked is None:
        picked = next((c for c in cands if c[2] in ("", "每日")), None)
    if picked is None:
        return None, None
    start, end, _ = picked
    ot_start, ot_end = (overtime_by_date or {}).get(biz_date, (None, None))
    return (ot_start or start, ot_end or end)


def payroll_coverage_issues(payroll_rows: list[list[Any]] | None) -> list[dict[str, str]]:
    """儲存更時表時嘅 coverage 檢查：每個更碼邊啲星期字 resolve 唔到。

    「每日」/留空冚晒七日；「公眾假期」唔當冚任何星期（假期日會 fallback
    去星期/每日行，所以冇公眾假期行唔使 warn）。時間無效嘅行唔計入 coverage
    （同 resolve_shift_time 一致）。
    """
    order: list[str] = []
    applies_by_code: dict[str, list[str]] = {}
    for row in (payroll_rows or [])[1:]:
        if not isinstance(row, list) or not row:
            continue
        code = str(row[0] or "").strip()
        if not code:
            continue
        if code not in applies_by_code:
            order.append(code)
            applies_by_code[code] = []
        start = parse_time(row[1] if len(row) > 1 else None)
        end = parse_time(row[2] if len(row) > 2 else None)
        if start is None or end is None:
            continue
        applies_by_code[code].append(str(row[3] or "").strip() if len(row) > 3 else "")

    issues: list[dict[str, str]] = []
    for code in order:
        covered: set[str] = set()
        for applies in applies_by_code[code]:
            if applies in ("", "每日"):
                covered.update(_ALL_WEEKDAY_CHARS)
            elif applies != "公眾假期":
                covered.update(ch for ch in applies if ch in _ALL_WEEKDAY_CHARS)
        uncovered = "".join(ch for ch in _ALL_WEEKDAY_CHARS if ch not in covered)
        if uncovered:
            issues.append({"code": code, "uncovered_days": uncovered})
    return issues
