"""行位表電話同步：parse / merge / export ——純 domain 邏輯，唔識 HTTP。

電腦同電話之間行 JSON（電腦讀 sqlite 出 alarms、電話推返上嚟亦係 alarms），
以前嗰套 XML 中轉已經拆走。呢度只 raise ScheduleGridDataError／
ScheduleGridNotFound，由 app.py 譯做 HTTP status。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo

from meal_planner.maintenance_db import MaintenanceDatabaseError, load_sheet_rows, roster_code_defs
from meal_planner.roster import code_for_date, roster_map_from_sheet_rows
from meal_planner.roster_codes import is_work_day
from meal_planner.schedule_grid import (
    grid_row_matches_roster,
    load_schedule_rows_from_rows,
    report_start_end,
    rows_for_roster,
)
from meal_planner.settings import get_settings
from meal_planner.timeparse import hhmm30


class ScheduleGridDataError(ValueError):
    """行位表資料本身有問題（400）。"""


class ScheduleGridNotFound(LookupError):
    """搵唔到對應嘅行位表版本（404）。"""


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_TRAILING_DURATION_RE = re.compile(r"\s+\d{1,3}$")
_SCHEDULE_GRID_DATE_ONLY_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}|(\d{1,2})/(\d{1,2})/(\d{4}))\s*$")
SCHEDULE_GRID_HEADER = ["更碼", "時間", "內容", "時長", "生效日期", "停用"]
_BLANK_EFFECTIVE_DATE_SENTINEL = "0001-01-01"


def _parse_date_iso(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if _SCHEDULE_GRID_DATE_ONLY_RE.fullmatch(text):
        m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$", text)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", text)
        if m:
            return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def normalize_schedule_grid_effective_date(raw: Any) -> str:
    normalized = _parse_date_iso(str(raw).strip())
    if normalized == _BLANK_EFFECTIVE_DATE_SENTINEL:
        return ""
    return normalized


def check_roster_codes_against_schedule_grid(roster_rows: list[Any]) -> dict[str, Any]:
    """
    更表檢查：今日及之後每個返工日，行位表有冇當日可用嘅版本。

    三類問題：
      unknown_code        — 行位表根本冇呢個更碼（例如打錯字）
      no_effective_version — 更碼存在，但當日冇任何已生效版本（生效日期全部遲過嗰日）
      missing_report_rows  — 當日版本喺度，但入面冇齊「報開工／報收工」兩行。
                             呢兩行係全系統嘅實務時間軸（報開工/收工 form、報平安更、
                             日曆返工 event、起身鬧鐘），冇就成日冇時間可用。

    過去嘅日子唔檢查（改唔到亦冇影響）。喺前端離開更表行嗰陣逐行叫，
    俾用戶即刻更正；儲存時唔再重覆檢查。
    """
    settings = get_settings()
    try:
        grid_sheet = load_sheet_rows("schedule_grid", settings)
    except (MaintenanceDatabaseError, OSError):
        return {"status": "skipped", "issues": []}

    grid_rows = grid_sheet.get("rows", []) if isinstance(grid_sheet, dict) else []
    parsed_rows = load_schedule_rows_from_rows(grid_rows if isinstance(grid_rows, list) else [])
    if not parsed_rows:
        return {"status": "skipped", "issues": []}

    known_codes = {str(getattr(row, "code", "") or "").strip() for row in parsed_rows}
    known_codes.discard("")

    code_defs = roster_code_defs(settings)
    today = datetime.now(ZoneInfo(settings.dates.timezone)).date()
    grouped: dict[tuple[str, str], list[str]] = {}
    for (year, month), month_map in sorted(roster_map_from_sheet_rows(roster_rows).items()):
        for day, raw_code in sorted(month_map.day_to_code.items()):
            code = str(raw_code or "").strip()
            if not code or not is_work_day(code_defs, code):
                continue
            try:
                day_date = date(year, month, day)
            except ValueError:
                continue
            if day_date < today:
                continue
            day_rows = rows_for_roster(parsed_rows, code, day_date)
            if day_rows:
                start, end = report_start_end(day_rows, day_date)
                if start is not None and end is not None:
                    continue
                reason = "missing_report_rows"
            elif any(grid_row_matches_roster(known, code) for known in known_codes):
                reason = "no_effective_version"
            else:
                reason = "unknown_code"
            grouped.setdefault((code, reason), []).append(day_date.isoformat())

    issues = [
        {
            "roster_code": code,
            "reason": reason,
            "day_count": len(days),
            "dates": sorted(days),
        }
        for (code, reason), days in sorted(grouped.items())
    ]
    return {
        "status": "warning" if issues else "ok",
        "checked_from": today.isoformat(),
        "issues": issues,
    }


def _next_workday_from(
    start: date,
    roster_map: dict[tuple[int, int], Any],
    *,
    max_days: int = 365,
) -> tuple[date, str] | tuple[None, None]:
    current = start
    for _ in range(max_days + 1):
        month_map = roster_map.get((current.year, current.month))
        code = code_for_date(month_map, current) if month_map else None
        if code and is_work_day(roster_code_defs(), code):
            return current, code
        current += timedelta(days=1)
    return None, None


def _schedule_day_minutes(rows: list[Any]) -> tuple[int, int]:
    mins: list[int] = []
    for row in rows:
        t = getattr(row, "t", None)
        if t is None:
            continue
        mins.append(int(t.hour) * 60 + int(t.minute))
    if not mins:
        return -1, -1
    return min(mins), max(mins)


def _latest_workday_schedule_before(
    start: date,
    roster_map: dict[tuple[int, int], Any],
    parsed_rows: list[Any],
    *,
    max_days: int = 365,
) -> tuple[date, str, list[Any]] | tuple[None, None, list[Any]]:
    current = start
    for _ in range(max_days + 1):
        month_map = roster_map.get((current.year, current.month))
        code = code_for_date(month_map, current) if month_map else None
        if code and is_work_day(roster_code_defs(), code):
            candidate_rows = rows_for_roster(parsed_rows, code, current)
            if candidate_rows:
                return current, code, candidate_rows
        current -= timedelta(days=1)
    return None, None, []


def _schedule_grid_effective_iso(rows: list[Any]) -> str:
    if not rows:
        return ""
    effective = getattr(rows[0], "effective_from", None)
    return "" if effective is None else effective.isoformat()


def _schedule_rows_to_grid_rows(rows: list[Any]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for row in rows:
        t = getattr(row, "t", None)
        if t is None:
            continue
        effective = getattr(row, "effective_from", None)
        out.append(
            [
                getattr(row, "code", "") or "",
                hhmm30(t),
                getattr(row, "content", "") or "",
                "" if getattr(row, "duration_min", None) is None else str(getattr(row, "duration_min")),
                "" if effective is None else effective.isoformat(),
                "1" if getattr(row, "disabled", False) else "",
            ]
        )
    return out


def _choose_schedule_grid_export_target(
    rows: list[list[Any]],
    timezone: str,
    roster_rows: list[Any],
) -> tuple[str, str, str, list[Any]] | None:
    now = datetime.now(ZoneInfo(timezone))
    now_minutes = now.hour * 60 + now.minute
    parsed_rows = load_schedule_rows_from_rows(rows)
    if not parsed_rows:
        return None

    roster_map = roster_map_from_sheet_rows(roster_rows)
    if not roster_map:
        return None

    # 唔可以跳過「有更但行位表冇對應更碼」嗰日：寧願俾上層報「搵唔到 X 行位表」，
    # 都好過靜靜雞攞咗第二日嘅行位表落手機。所以呢度淨係按更表揀日子，
    # 行位表配唔到就照返個空 rows 上去。
    candidate_date, code = _next_workday_from(now.date(), roster_map)
    if candidate_date is None or not code:
        candidate_date, code, candidate_rows = _latest_workday_schedule_before(
            now.date() - timedelta(days=1),
            roster_map,
            parsed_rows,
        )
        if candidate_date is None or not code or not candidate_rows:
            return None
        return candidate_date.isoformat(), str(code), _schedule_grid_effective_iso(candidate_rows), candidate_rows

    candidate_rows = rows_for_roster(parsed_rows, code, candidate_date)
    if candidate_date == now.date() and candidate_rows:
        _, max_time = _schedule_day_minutes(candidate_rows)
        if max_time >= 0 and now_minutes > max_time:
            next_date, next_code = _next_workday_from(candidate_date + timedelta(days=1), roster_map)
            if next_date is None or not next_code:
                return None
            candidate_date = next_date
            code = next_code
            candidate_rows = rows_for_roster(parsed_rows, code, candidate_date)

    return candidate_date.isoformat(), str(code), _schedule_grid_effective_iso(candidate_rows), candidate_rows


def rows_for_dates(
    rows: list[list[Any]],
    dates: set[str],
    imported_codes: set[str],
) -> list[list[Any]]:
    if not dates or not imported_codes:
        return []
    return [
        row for row in rows[1:]
        if isinstance(row, (list, tuple))
        and (
            (normalize_schedule_grid_effective_date(row[4]) if len(row) >= 5 else "")
            in dates
        )
        and (
            ("" if row[0] is None else str(row[0]).strip()) in imported_codes
        )
    ]


def extract_schedule_grid_effective_dates(imported_rows: list[list[Any]]) -> set[str]:
    if not isinstance(imported_rows, list):
        return set()

    versions: set[str] = set()
    for row in imported_rows[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        effective = normalize_schedule_grid_effective_date(row[4])
        if effective:
            versions.add(effective)

    return versions


def collect_schedule_grid_import_codes(rows: list[list[Any]]) -> set[str]:
    codes: set[str] = set()
    if not isinstance(rows, list):
        return codes
    for row in rows[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            continue
        code = ("" if row[0] is None else str(row[0]).strip())
        if code:
            codes.add(code)
    return codes


def split_content_duration(label: Any) -> tuple[str, str]:
    """電話送返嚟嘅 label 係「內容 + 時長」；拆返做兩欄存入行位表。"""
    text = ("" if label is None else str(label)).strip()
    match = _TRAILING_DURATION_RE.search(text)
    if not match:
        return text, ""
    content = text[: match.start()].rstrip()
    if not content:
        return text, ""
    return content, match.group(0).strip()


def parse_schedule_grid_push_payload(payload: Any) -> tuple[list[list[Any]], set[str]]:
    """電話推上嚟嘅 JSON → 行位表 rows。

    payload：{"effective_date": "2026-07-26", "roster_code": "PenBM",
              "alarms": [{"time": "10:20", "label": "報開工 10", "disabled": false}, ...]}
    """
    if not isinstance(payload, dict):
        raise ScheduleGridDataError("Phone push payload must be a JSON object.")
    roster_code = str(payload.get("roster_code", "") or "").strip()
    effective = normalize_schedule_grid_effective_date(payload.get("effective_date", ""))
    alarms = payload.get("alarms")
    if not isinstance(alarms, list):
        raise ScheduleGridDataError("Phone push payload has no alarms list.")

    rows_out: list[list[Any]] = [SCHEDULE_GRID_HEADER[:]]
    for item in alarms:
        if not isinstance(item, dict):
            continue
        time_value = str(item.get("time", "") or "").strip()
        if not _TIME_RE.fullmatch(time_value):
            continue
        content, duration = split_content_duration(item.get("label", ""))
        if not content:
            continue
        disabled = "1" if item.get("disabled") else ""
        rows_out.append([roster_code, time_value, content, duration, effective, disabled])

    if len(rows_out) <= 1:
        raise ScheduleGridDataError("No alarm rows found in the phone push payload.")
    imported_dates = {effective} if effective else set()
    return rows_out, imported_dates


def merge_schedule_grid_rows_for_import(
    existing_rows: list[Any],
    imported_rows: list[list[Any]],
    imported_dates: set[str],
    imported_codes: set[str],
) -> list[list[Any]]:
    existing = existing_rows if isinstance(existing_rows, list) else []
    if not imported_dates:
        return imported_rows

    kept_rows: list[list[Any]] = []
    for row in existing[1:] if isinstance(existing, list) and len(existing) > 1 else []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            effective = ""
        else:
            effective = normalize_schedule_grid_effective_date(row[4])
        code = ("" if len(row) <= 0 or row[0] is None else str(row[0]).strip())
        if imported_codes and effective in imported_dates and code in imported_codes:
            continue
        kept_rows.append(list(row))
    merged = [SCHEDULE_GRID_HEADER[:]]
    merged.extend(kept_rows)
    merged.extend(imported_rows[1:])
    return merged


def _label_with_duration(content: str, duration: str) -> str:
    """行位表 label 一律「內容 + 時長」：先剝走內容尾巴嘅舊數字，再貼返時長欄嘅值。"""
    base = _TRAILING_DURATION_RE.sub("", content).rstrip()
    if not base:
        base = content.strip()
    if not duration or base == duration:
        return base
    return f"{base} {duration}".strip()


def _exact_schedule_rows_for_code_on_day(
    parsed_rows: list[Any],
    roster_code: str,
    target_day: date,
) -> list[Any]:
    code = str(roster_code or "").strip()
    if not code:
        return []
    matched = [row for row in parsed_rows if grid_row_matches_roster(getattr(row, "code", ""), code)]
    dated = [
        row for row in matched
        if getattr(row, "effective_from", None) is not None
        and getattr(row, "effective_from") <= target_day
    ]
    if dated:
        latest = max(getattr(row, "effective_from") for row in dated)
        return [row for row in dated if getattr(row, "effective_from") == latest]
    return [row for row in matched if getattr(row, "effective_from", None) is None]


def build_schedule_grid_all_variants_export() -> dict[str, Any]:
    settings = get_settings()
    try:
        sheet = load_sheet_rows("schedule_grid", settings)
    except MaintenanceDatabaseError as e:
        raise ScheduleGridDataError(str(e)) from e
    try:
        roster_sheet = load_sheet_rows("roster", settings)
    except MaintenanceDatabaseError:
        roster_sheet = {}
    except OSError:
        roster_sheet = {}

    rows = sheet.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    export_target = _choose_schedule_grid_export_target(
        rows,
        settings.dates.timezone,
        roster_sheet.get("rows", []) if isinstance(roster_sheet.get("rows", []), list) else [],
    )
    if export_target is None:
        raise ScheduleGridNotFound("更表之後冇返工日記錄")
    target_date, roster_code, export_version, _ = export_target
    try:
        target_day = datetime.fromisoformat(target_date).date()
    except ValueError as e:
        raise ScheduleGridDataError(f"Invalid schedule target date: {target_date}") from e

    parsed_rows = load_schedule_rows_from_rows(rows)
    code_order: list[str] = []
    for row in parsed_rows:
        code = str(getattr(row, "code", "") or "").strip()
        if code and code not in code_order:
            code_order.append(code)

    # 打風日：當日更碼嗰個 variant 換成模擬出嚟嗰份（返唔到嘅位 disabled、加開報更）。
    # 行位表 sheet 冇改過——呢度淨係出 payload 嗰刻按加班表 + 4 小時規則砌返出嚟。
    from meal_planner.typhoon import typhoon_grid_rows

    typhoon_rows = typhoon_grid_rows(settings, target_day, roster_code) if roster_code else None

    variants: list[dict[str, Any]] = []
    for code in code_order:
        # 停用行都要送落電話——電話要見到佢先撳得返啟用；停用資訊喺 alarm 個 disabled 欄。
        variant_rows = _exact_schedule_rows_for_code_on_day(parsed_rows, code, target_day)
        exported_rows = _schedule_rows_to_grid_rows(variant_rows)
        if not exported_rows:
            continue
        variant_version = _schedule_grid_effective_iso(variant_rows) or export_version
        is_current = grid_row_matches_roster(code, roster_code)
        if is_current and typhoon_rows is not None:
            alarms = [
                {
                    "time": item["time"],
                    "label": _label_with_duration(
                        item["content"], "" if item["duration_min"] is None else str(item["duration_min"])
                    ),
                    "disabled": bool(item["disabled"]),
                }
                for item in typhoon_rows
                if _TIME_RE.fullmatch(str(item["time"] or ""))
            ]
        else:
            alarms = [
                {
                    "time": row[1],
                    "label": _label_with_duration(str(row[2] or ""), str(row[3] or "")),
                    "disabled": bool(len(row) > 5 and str(row[5] or "").strip()),
                }
                for row in exported_rows
                if _TIME_RE.fullmatch(str(row[1] or ""))
            ]
        if not alarms:
            continue
        variants.append(
            {
                "roster_code": code,
                "target_date": target_date,
                "effective_date": variant_version,
                "alarm_count": len(alarms),
                "is_current": is_current,
                "alarms": alarms,
            }
        )
    if not variants:
        raise ScheduleGridNotFound(f"搵唔到 {target_date} 可用嘅行位表版本。")
    if roster_code and not any(item["is_current"] for item in variants):
        raise ScheduleGridNotFound(f"搵唔到 {roster_code} 行位表")
    return {
        "ok": True,
        "target_date": target_date,
        "current_roster_code": roster_code,
        "effective_date": export_version,
        "variant_count": len(variants),
        "variants": variants,
    }
