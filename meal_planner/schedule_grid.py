"""行位表：報開工／報收工／飯／小食鐘點；與飯時規則合併成實際用餐時間字串。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any


from meal_planner.settings import AppSettings
from meal_planner.timeparse import cell_text, parse_time as _to_time

MEAL_KEYS = ("早餐", "午餐", "小食", "晚餐")

# 行位表嘅「停用」欄：logical field，maint 畫面唔會當佢係一般欄render，
# 改為每行一粒 toggle + 成行 dim。空／0／false ＝ 用緊。
DISABLED_HEADER = "停用"
_DISABLED_TRUE = {"1", "true", "yes", "y", "x", "停用", "disabled"}


def is_disabled_cell(value: Any) -> bool:
    return str(value or "").strip().casefold() in _DISABLED_TRUE

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
    disabled: bool = False

    @property
    def is_marker(self) -> bool:
        """`-` 開頭嗰啲行（報人數、取牌簽簿…）：照響，但唔佔時長，
        前一格嘅時長跨過佢哋。"""
        return self.content.strip().startswith("-")


def rows_for_roster(
    rows: list[ScheduleRow],
    roster_code: str,
    day: date | None = None,
    *,
    include_disabled: bool = False,
) -> list[ScheduleRow]:
    """該更碼當日生效嗰個版本嘅行。停用咗嘅行預設唔會出——停用＝當日呢一格唔存在
    （唔響鬧鐘、唔出報平安更、唔計時長）；淨係編輯畫面先要 include_disabled=True。"""
    matched = [
        x for x in rows
        if grid_row_matches_roster(x.code, roster_code) and (include_disabled or not x.disabled)
    ]
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
    c_off = headers.get(DISABLED_HEADER)
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
                disabled=is_disabled_cell(row[c_off]) if c_off is not None and c_off < len(row) else False,
            )
        )
    return out


_RE_SUN_THU = re.compile(r"[（(]\s*日-四\s*[)）]")
_RE_FRI_SAT = re.compile(r"[（(]\s*五六\s*[)）]")


def weekday_allows(content: str, biz_date: date) -> bool:
    """(日-四)/(五六) 標記：唔匹配當日星期就唔算該行；冇標記一律算。"""
    wd = biz_date.weekday()  # Mon=0 .. Sun=6
    if _RE_SUN_THU.search(content):
        return wd in (6, 0, 1, 2, 3)
    if _RE_FRI_SAT.search(content):
        return wd in (4, 5)
    return True


def report_start_end(
    rows: list[ScheduleRow], day: date | None = None
) -> tuple[time | None, time | None]:
    """該版本行位表嘅「報開工／報收工」時間。

    有啲更碼唔同星期收唔同時間，用 (日-四)/(五六) 標記分做兩行
    （例如 FBPB：日至四 21:30、五六 22:00）——傳咗 day 就按當日星期揀啱嗰行；
    唔傳就唔理標記（攞最後嗰行）。
    """

    def usable(row: ScheduleRow) -> bool:
        return row.t is not None and (day is None or weekday_allows(row.content, day))

    start = next((x.t for x in rows if "報開工" in x.content and usable(x)), None)
    end = next((x.t for x in reversed(rows) if "報收工" in x.content and usable(x)), None)
    return start, end


def recompute_durations(rows: list[ScheduleRow]) -> list[ScheduleRow]:
    """重算時長：一格嘅時長 ＝ 去下一個「佔時間」行嘅距離。

    `-` 開頭嘅 marker 行同停用咗嘅行都唔佔時間，會俾前一格跨過。插入／刪除／停用
    之後叫一次，成張表啲時長就跟住啱返。最後一格冇下一格，時長留空。
    """
    live = sorted(
        (x for x in rows if x.t is not None and not x.disabled and not x.is_marker),
        key=lambda x: (x.t.hour * 60 + x.t.minute),
    )
    for i, row in enumerate(live):
        if i + 1 >= len(live):
            row.duration_min = None
            continue
        nxt = live[i + 1]
        row.duration_min = (nxt.t.hour * 60 + nxt.t.minute) - (row.t.hour * 60 + row.t.minute)
    for row in rows:
        if row.is_marker or row.disabled:
            row.duration_min = None
    return rows


def first_food_time(
    rows: list[ScheduleRow], *, keyword: str, not_before: time | None = None
) -> tuple[time | None, int | None]:
    """keyword 為「飯」或「小食」（內容包含即計）。

    not_before：實際開工時間。開工前嘅食位（例如打風遲開工，行位表 13:15 飯位
    你 13:40 先返到）根本食唔到，跳過佢，攞開工後第一個。
    """
    for x in rows:
        if keyword not in x.content or x.t is None:
            continue
        if not_before is not None and x.t < not_before:
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

    另加一個 `_skipped` key：{餐次: 原因}——「跟行位表」嗰啲餐次，如果行位表個
    食位喺實際開工之前（打風遲開工咁），佢就食唔到，餐次唔會出，但要講明點解，
    唔可以靜靜哋消失。
    """
    out: dict[str, Any] = {k: None for k in MEAL_KEYS}
    skipped: dict[str, str] = {}
    if not primary_rule or not roster_code:
        return out

    all_rows = schedule_rows or []
    my_rows = rows_for_roster(all_rows, roster_code, day)
    g_start, g_end = report_start_end(my_rows, day)

    ot_start, ot_end = (overtime_overrides or {}).get(day, (None, None))

    start = ot_start if ot_start is not None else g_start
    end = ot_end if ot_end is not None else g_end

    def resolve_one(meal: str, raw: Any) -> str | None:
        s = cell_text(raw)
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
            keyword = {"午餐": "飯", "小食": "小食"}.get(meal)
            if keyword is None:
                return None
            t, _ = first_food_time(my_rows, keyword=keyword, not_before=start)
            if t is not None:
                return _fmt_clock(t)
            missed, _ = first_food_time(my_rows, keyword=keyword)
            if missed is not None and start is not None:
                skipped[meal] = (
                    f"行位表{_fmt_clock(missed)}個{keyword}位喺開工 {_fmt_clock(start)} 之前，食唔到"
                )
            return None

        return None

    for meal in MEAL_KEYS:
        raw = primary_rule.get(meal)
        out[meal] = resolve_one(meal, raw)

    out["_skipped"] = skipped
    return out
