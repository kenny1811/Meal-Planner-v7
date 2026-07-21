"""行位表：報開工／報收工／飯／小食鐘點；與飯時規則合併成實際用餐時間字串。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any


from meal_planner.settings import AppSettings
from meal_planner.timeparse import parse_time as _to_time

MEAL_KEYS = ("早餐", "午餐", "小食", "晚餐")

_RE_BEFORE = re.compile(r"開工前\s*(\d+(?:\.\d+)?)\s*小時")
_RE_AFTER = re.compile(r"收工後\s*(\d+(?:\.\d+)?)\s*小時")


def _to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^(\d{1,2}/\d{1,2}/\d{2,4})(?:\s+\w+)?$", s)
        if m:
            s = m.group(1)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%d%m%Y", "%d%m%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)
        if m:
            try:
                today = date.today()
                return date(today.year, int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
    return None


def _ddt(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def _fmt_clock(t: time) -> str:
    return t.strftime("%H:%M")


def grid_row_matches_roster(cell_code: str | None, roster_code: str) -> bool:
    """
    行位更碼：必須與更表更碼完全一致（只忽略大小寫同前後空格）。

    括號**唔係**版本後綴：`PenB(頂位)`、`FBPA(單人)`、`FBPA(雙人)` 各自係獨立更碼，
    唔可以當成 `PenB` / `FBPA` 嘅變體（同 `PenC頂位` 唔當 `PenC` 一樣道理）。
    同一個更碼嘅新舊版本，一律靠「生效日期」欄分辨。
    """
    if not cell_code or not roster_code:
        return False
    return str(cell_code).strip().casefold() == str(roster_code).strip().casefold()


@dataclass
class ScheduleRow:
    code: str
    t: time | None
    content: str
    duration_min: int | None
    effective_from: date | None = None


def rows_for_roster(rows: list[ScheduleRow], roster_code: str, day: date | None = None) -> list[ScheduleRow]:
    matched = [x for x in rows if grid_row_matches_roster(x.code, roster_code)]
    if day is None:
        return matched
    dated = [x for x in matched if x.effective_from is not None and x.effective_from <= day]
    if not dated:
        return [x for x in matched if x.effective_from is None]
    latest = max(x.effective_from for x in dated if x.effective_from is not None)
    return [x for x in dated if x.effective_from == latest]


def load_schedule_rows_from_rows(rows: list[list[Any]]) -> list[ScheduleRow]:
    if not rows:
        return []
    headers = {str(v).strip(): idx for idx, v in enumerate(rows[0]) if v is not None and str(v).strip()}
    c_code = headers.get("更碼")
    c_time = headers.get("時間")
    c_content = headers.get("內容")
    c_dur = headers.get("時長")
    c_eff = headers.get("生效日期")
    if c_eff is None:
        c_eff = headers.get("生效")
    if c_eff is None:
        c_eff = headers.get("Effective From")
    if c_code is None or c_time is None or c_content is None:
        return []
    out: list[ScheduleRow] = []
    for row in rows[1:]:
        if not isinstance(row, list) or c_code >= len(row):
            continue
        code = str(row[c_code] or "").strip()
        if not code:
            continue
        dur_raw = row[c_dur] if c_dur is not None and c_dur < len(row) else None
        dur: int | None = None
        if dur_raw is not None:
            try:
                dur = int(float(dur_raw))
            except (TypeError, ValueError):
                dur = None
        out.append(
            ScheduleRow(
                code=code,
                t=_to_time(row[c_time]) if c_time < len(row) else None,
                content=str(row[c_content] if c_content < len(row) and row[c_content] is not None else ""),
                duration_min=dur,
                effective_from=_to_date(row[c_eff]) if c_eff is not None and c_eff < len(row) else None,
            )
        )
    return out


def report_start_end(rows: list[ScheduleRow]) -> tuple[time | None, time | None]:
    start: time | None = None
    end: time | None = None
    for x in rows:
        if "報開工" in x.content and x.t is not None:
            start = x.t
            break
    for x in reversed(rows):
        if "報收工" in x.content and x.t is not None:
            end = x.t
            break
    return start, end


def first_food_time(rows: list[ScheduleRow], *, keyword: str) -> tuple[time | None, int | None]:
    """keyword 為「飯」或「小食」（內容包含即計）。"""
    for x in rows:
        if keyword not in x.content:
            continue
        if x.t is None:
            continue
        return x.t, x.duration_min
    return None, None


def load_overtime_overrides_from_rows(rows: list[list[Any]]) -> dict[date, tuple[time | None, time | None]]:
    if not rows:
        return {}
    headers = {str(v).strip(): idx for idx, v in enumerate(rows[0]) if v is not None and str(v).strip()}
    c_date = headers.get("日期")
    c_start = headers.get("開工")
    c_end = headers.get("收工")
    if c_date is None:
        return {}
    out: dict[date, tuple[time | None, time | None]] = {}
    for row in rows[1:]:
        if not isinstance(row, list) or c_date >= len(row):
            continue
        dd = _to_date(row[c_date])
        if dd is None:
            continue
        out[dd] = (
            _to_time(row[c_start]) if c_start is not None and c_start < len(row) else None,
            _to_time(row[c_end]) if c_end is not None and c_end < len(row) else None,
        )
    return out


def load_wake_alarm_overrides_from_rows(rows: list[list[Any]]) -> dict[date, time]:
    if not rows:
        return {}
    headers = {str(v).strip(): idx for idx, v in enumerate(rows[0]) if v is not None and str(v).strip()}
    c_date = headers.get("日期")
    c_wake = headers.get("起身時間")
    if c_wake is None:
        c_wake = headers.get("起身")
    if c_date is None or c_wake is None:
        return {}
    out: dict[date, time] = {}
    for row in rows[1:]:
        if not isinstance(row, list) or c_date >= len(row) or c_wake >= len(row):
            continue
        dd = _to_date(row[c_date])
        wake = _to_time(row[c_wake])
        if dd is None or wake is None:
            continue
        out[dd] = wake
    return out


def parse_relative_hours(text: str | None, *, kind: str) -> float | None:
    if not text:
        return None
    s = str(text).strip()
    if kind == "before":
        m = _RE_BEFORE.search(s)
        return float(m.group(1)) if m else None
    if kind == "after":
        m = _RE_AFTER.search(s)
        return float(m.group(1)) if m else None
    return None


def _cell_rule_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, datetime):
        return v.strftime("%H:%M")
    s = str(v).strip()
    return s if s else None


def resolve_meal_times_display(
    settings: AppSettings,
    *,
    day: date,
    roster_code: str,
    primary_rule: dict[str, Any] | None,
    is_work_day: bool | None,
    restaurant: dict[str, Any] | None,
    schedule_rows: list[ScheduleRow] | None = None,
    overtime_overrides: dict[date, tuple[time | None, time | None]] | None = None,
) -> dict[str, str | None]:
    """
    回傳 早餐／午餐／小食／晚餐 → 顯示字串（實際鐘点或時段）。
    無法推算則 None（前端可回落顯示飯時原文）。
    """
    out: dict[str, str | None] = {k: None for k in MEAL_KEYS}
    if not primary_rule or not roster_code:
        return out

    all_rows = schedule_rows or []
    my_rows = rows_for_roster(all_rows, roster_code, day)
    g_start, g_end = report_start_end(my_rows)

    ot_start, ot_end = (overtime_overrides or {}).get(day, (None, None))

    start = ot_start if ot_start is not None else g_start
    end = ot_end if ot_end is not None else g_end

    def resolve_one(meal: str, raw: Any) -> str | None:
        s = _cell_rule_str(raw)
        if not s or s == "—":
            return None
        if re.fullmatch(r"\d{1,2}:\d{2}", s):
            return s

        if "開工前" in s and start is not None:
            h = parse_relative_hours(s, kind="before") or 2.0
            a = _ddt(day, start) - timedelta(hours=h)
            return _fmt_clock(a.time())

        if "收工後" in s and end is not None:
            h = parse_relative_hours(s, kind="after") or 1.5
            b = _ddt(day, end) + timedelta(hours=h)
            return _fmt_clock(b.time())

        if "跟行位表" in s:
            if meal == "午餐":
                t, _ = first_food_time(my_rows, keyword="飯")
                if t is None:
                    return None
                return _fmt_clock(t)
            if meal == "小食":
                t, _ = first_food_time(my_rows, keyword="小食")
                if t is None:
                    return None
                return _fmt_clock(t)
            return None

        return None

    for meal in MEAL_KEYS:
        raw = primary_rule.get(meal)
        out[meal] = resolve_one(meal, raw)

    return out
