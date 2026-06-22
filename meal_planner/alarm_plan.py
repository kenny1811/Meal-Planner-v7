"""Daily phone alarm payloads derived from roster and schedule-grid rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from meal_planner.maintenance_db import load_sheet_rows
from meal_planner.roster import code_for_date, is_work_day, roster_for_month
from meal_planner.schedule_grid import (
    ScheduleRow,
    load_overtime_overrides_from_rows,
    load_schedule_rows_from_rows,
    report_start_end,
    rows_for_roster,
)
from meal_planner.settings import AppSettings, get_settings


@dataclass(frozen=True)
class DailyAlarm:
    id: str
    label: str
    trigger_at: datetime


def _today(settings: AppSettings) -> date:
    return datetime.now(ZoneInfo(settings.dates.timezone)).date()


def _roster_cell_texts(rows: list[list[Any]]) -> list[str | None]:
    out: list[str | None] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        for cell in row:
            if cell is None:
                continue
            out.append(str(cell))
    return out


def _combine_shift_datetime(
    day: date,
    t: time,
    *,
    start: time | None,
    end: time | None,
    tz: ZoneInfo,
) -> datetime:
    out = datetime.combine(day, t, tzinfo=tz)
    if start is not None and end is not None and end <= start and t < start:
        out += timedelta(days=1)
    return out


def _row_time(row: ScheduleRow, *, start: time | None, end: time | None) -> time | None:
    content = row.content or ""
    if "報開工" in content and start is not None:
        return start
    if "報收工" in content and end is not None:
        return end
    return row.t


def build_daily_alarm_plan(
    target_date: date | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    target_date = target_date or _today(settings)
    tz = ZoneInfo(settings.dates.timezone)

    roster_payload = load_sheet_rows("roster", settings)
    roster_map = roster_for_month(_roster_cell_texts(roster_payload.get("rows", [])))
    roster_month = roster_map.get((target_date.year, target_date.month))
    roster_code = code_for_date(roster_month, target_date) if roster_month else None
    work_day = is_work_day(roster_code) if roster_code else None

    base: dict[str, Any] = {
        "date": target_date.isoformat(),
        "timezone": settings.dates.timezone,
        "roster_code": roster_code,
        "is_work_day": work_day,
        "alarms": [],
        "cleanup_at": None,
        "notes": [],
    }
    if not roster_code:
        base["notes"].append("今日更表無更碼，未能產生電話鬧鐘。")
        return base
    if work_day is False:
        base["notes"].append("今日係非返工日，無需設定行位鬧鐘。")
        return base

    schedule_payload = load_sheet_rows("schedule_grid", settings)
    schedule_rows = load_schedule_rows_from_rows(schedule_payload.get("rows", []))
    day_rows = rows_for_roster(schedule_rows, roster_code, target_date)
    if not day_rows:
        base["notes"].append(f"行位表搵唔到更碼 {roster_code}。")
        return base

    grid_start, grid_end = report_start_end(day_rows)
    overtime_payload = load_sheet_rows("overtime", settings)
    overtime = load_overtime_overrides_from_rows(overtime_payload.get("rows", []))
    ot_start, ot_end = overtime.get(target_date, (None, None))
    start = ot_start or grid_start
    end = ot_end or grid_end

    alarms: list[DailyAlarm] = []
    seen: set[tuple[str, str]] = set()
    for idx, row in enumerate(day_rows, start=1):
        t = _row_time(row, start=start, end=end)
        label = str(row.content or "").strip()
        if t is None or not label:
            continue
        trigger = _combine_shift_datetime(target_date, t, start=start, end=end, tz=tz)
        key = (trigger.isoformat(), label)
        if key in seen:
            continue
        seen.add(key)
        alarms.append(
            DailyAlarm(
                id=f"{target_date.isoformat()}-{idx}",
                label=label,
                trigger_at=trigger,
            )
        )

    alarms.sort(key=lambda item: item.trigger_at)
    base["alarms"] = [
        {
            "id": alarm.id,
            "label": alarm.label,
            "trigger_at": alarm.trigger_at.isoformat(),
            "trigger_at_epoch_ms": int(alarm.trigger_at.timestamp() * 1000),
        }
        for alarm in alarms
    ]

    if end is not None:
        cleanup_at = _combine_shift_datetime(target_date, end, start=start, end=end, tz=tz) + timedelta(hours=2)
        base["cleanup_at"] = cleanup_at.isoformat()
        base["cleanup_at_epoch_ms"] = int(cleanup_at.timestamp() * 1000)
    else:
        base["notes"].append("行位表無報收工時間，未能設定收工後兩小時清理。")

    return base
