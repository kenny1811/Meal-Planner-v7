"""行位表 XML：parse / merge / export ——純 domain 邏輯，唔識 HTTP。

以前成 640 行擺喺 app.py 入面，同 route handler 撈埋一齊。呢度只 raise
ScheduleGridDataError／ScheduleGridNotFound，由 app.py 譯做 HTTP status。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from meal_planner.maintenance_db import MaintenanceDatabaseError, load_sheet_rows
from meal_planner.roster import code_for_date, is_work_day, roster_map_from_sheet_rows
from meal_planner.schedule_grid import (
    grid_row_matches_roster,
    load_schedule_rows_from_rows,
    rows_for_roster,
)
from meal_planner.settings import get_settings


class ScheduleGridDataError(ValueError):
    """行位表資料本身有問題（400）。"""


class ScheduleGridNotFound(LookupError):
    """搵唔到對應嘅行位表版本（404）。"""


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
SCHEDULE_GRID_HEADER_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2}|(\d{1,2})/(\d{1,2})/(\d{4}))\s+(.+)\s*$"
)
_SCHEDULE_GRID_DATE_ONLY_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}|(\d{1,2})/(\d{1,2})/(\d{4}))\s*$")
_SCHEDULE_GRID_NOISE_TEXTS = {
    "",
    "時間",
    "內容",
    "操作",
    "插入",
    "刪除",
    "刪除全部",
    "append",
    "append all",
    "insert",
    "delete",
    "delete all",
    "sync",
    "synchronize",
}
SCHEDULE_GRID_HEADER = ["更碼", "時間", "內容", "時長", "生效日期"]
_BLANK_EFFECTIVE_DATE_SENTINEL = "0001-01-01"
SCHEDULE_GRID_EXPORT_FILE_NAME = "export.xml"


def extract_xml_texts(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    return [
        text.strip()
        for text in root.itertext()
        if isinstance(text, str) and text.strip()
    ]


def schedule_grid_xml_metadata(xml_bytes: bytes) -> tuple[str | None, str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None, ""
    effective = normalize_schedule_grid_effective_date(root.attrib.get("effective_date", ""))
    roster_code = str(root.attrib.get("roster_code", "") or "").strip()
    return (effective or None), roster_code


def apply_schedule_grid_xml_metadata(
    rows: list[list[Any]],
    *,
    effective_version: str | None,
    roster_code: str,
) -> list[list[Any]]:
    normalized_version = (
        normalize_schedule_grid_effective_date(str(effective_version).strip())
        if effective_version
        else ""
    )
    normalized_code = str(roster_code or "").strip()
    if not normalized_version and not normalized_code:
        return rows

    for row in rows[1:]:
        if not isinstance(row, list):
            continue
        while len(row) < 5:
            row.append("")
        if normalized_code:
            row[0] = normalized_code
        if normalized_version and not normalize_schedule_grid_effective_date(row[4]):
            row[4] = normalized_version
    return rows


def parse_header_date(raw: str) -> str:
    text = raw.strip()
    match = SCHEDULE_GRID_HEADER_RE.fullmatch(text)
    if match:
        if match.group(1).count("-") == 2:
            return match.group(1)
        day = int(match.group(2))
        month = int(match.group(3))
        year = int(match.group(4))
        return f"{year:04d}-{month:02d}-{day:02d}"
    raise ScheduleGridDataError(f"Invalid header date: {raw}")


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

    分兩類問題：
      unknown_code        — 行位表根本冇呢個更碼（例如打錯字）
      no_effective_version — 更碼存在，但當日冇任何已生效版本（生效日期全部遲過嗰日）

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

    today = datetime.now(ZoneInfo(settings.dates.timezone)).date()
    grouped: dict[tuple[str, str], list[str]] = {}
    for (year, month), month_map in sorted(roster_map_from_sheet_rows(roster_rows).items()):
        for day, raw_code in sorted(month_map.day_to_code.items()):
            code = str(raw_code or "").strip()
            if not code or not is_work_day(code):
                continue
            try:
                day_date = date(year, month, day)
            except ValueError:
                continue
            if day_date < today or rows_for_roster(parsed_rows, code, day_date):
                continue
            reason = (
                "no_effective_version"
                if any(grid_row_matches_roster(known, code) for known in known_codes)
                else "unknown_code"
            )
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
        if code and is_work_day(code):
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
        if code and is_work_day(code):
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
                t.strftime("%H:%M"),
                getattr(row, "content", "") or "",
                "" if getattr(row, "duration_min", None) is None else str(getattr(row, "duration_min")),
                "" if effective is None else effective.isoformat(),
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


def parse_schedule_grid_texts(rows: list[str]) -> tuple[list[list[Any]], set[str]]:
    rows_out: list[list[Any]] = [SCHEDULE_GRID_HEADER[:]]
    current_code = ""
    current_effective = ""
    i = 0
    n = len(rows)

    while i < n:
        token = rows[i].strip()
        if not token:
            i += 1
            continue

        if _SCHEDULE_GRID_NOISE_TEXTS and token.lower() in _SCHEDULE_GRID_NOISE_TEXTS:
            i += 1
            continue

        date_only = _SCHEDULE_GRID_DATE_ONLY_RE.fullmatch(token)
        if date_only and not _TIME_RE.match(token):
            current_effective = normalize_schedule_grid_effective_date(parse_header_date(token))
            i += 1
            continue

        header_match = SCHEDULE_GRID_HEADER_RE.fullmatch(token)
        if header_match:
            current_effective = normalize_schedule_grid_effective_date(parse_header_date(token))
            current_code = (header_match.group(5) or "").strip()
            i += 1
            continue

        if _TIME_RE.match(token):
            content = None
            j = i + 1
            while j < n:
                next_token = rows[j].strip()
                if not next_token or next_token.lower() in _SCHEDULE_GRID_NOISE_TEXTS:
                    j += 1
                    continue
                if _TIME_RE.match(next_token) or _SCHEDULE_GRID_DATE_ONLY_RE.fullmatch(next_token) or SCHEDULE_GRID_HEADER_RE.fullmatch(next_token):
                    break
                content = next_token
                j = j + 1
                break
            if content is None:
                i += 1
                continue

            minutes_duration = ""
            content_value = content
            m = re.match(r"^(.*)\s+(\d{1,3})$", content_value)
            if m and m.group(1).strip() and m.group(2):
                content_value = m.group(1).strip()
                minutes_duration = m.group(2)

            rows_out.append([current_code, token, content_value, minutes_duration, current_effective])
            i = j
            continue

        i += 1

    if len(rows_out) <= 1:
        raise ScheduleGridDataError("No alarm rows found in the uploaded XML.")

    imported_dates: set[str] = set()
    for row in rows_out[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        effective = normalize_schedule_grid_effective_date(row[4])
        if effective:
            imported_dates.add(effective)
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


def _escape_xml_text(value: Any) -> str:
    return (
        ""
        if value is None
        else (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;")
        )
    )


def build_schedule_grid_xml(
    rows: list[list[Any]],
    *,
    fallback_effective_date: str | None = None,
    section_date: str | None = None,
) -> bytes:
    root_effective_version: str | None = (
        normalize_schedule_grid_effective_date(str(fallback_effective_date).strip())
        if fallback_effective_date is not None
        else None
    )
    if root_effective_version is None:
        for row in rows[1:]:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                continue
            row_version = normalize_schedule_grid_effective_date(row[4])
            if row_version:
                root_effective_version = row_version
                break
    root_roster_code = ""
    for row in rows[1:]:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        code = ("" if row[0] is None else str(row[0])).strip()
        if code:
            root_roster_code = code
            break
    root_roster_attr = f' roster_code="{_escape_xml_text(root_roster_code)}"' if root_roster_code else ""
    lines: list[str] = [
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>",
    ]
    if fallback_effective_date is not None:
        lines.append(f'<schedule_grid effective_date="{root_effective_version or ""}"{root_roster_attr}>')
    elif root_effective_version:
        lines.append(f'<schedule_grid effective_date="{root_effective_version}"{root_roster_attr}>')
    else:
        lines.append(f"<schedule_grid{root_roster_attr}>")
    last_header = ""
    for row in rows[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        roster_code = ("" if row[0] is None else str(row[0])).strip()
        time_value = ("" if row[1] is None else str(row[1])).strip()
        content_value = ("" if row[2] is None else str(row[2])).strip()
        if not _TIME_RE.fullmatch(time_value):
            continue
        date_value = normalize_schedule_grid_effective_date(row[4]) if len(row) >= 5 else ""
        iso = (
            normalize_schedule_grid_effective_date(section_date)
            if section_date is not None
            else (date_value if date_value else _BLANK_EFFECTIVE_DATE_SENTINEL)
        )
        header = f"{iso} {roster_code}".strip()
        if header != last_header:
            lines.append(f"<section>{_escape_xml_text(header)}</section>")
            last_header = header
        text_label = content_value
        lines.append(f"<alarm_time>{_escape_xml_text(time_value)}</alarm_time>")
        lines.append(f"<alarm_label>{_escape_xml_text(text_label)}</alarm_label>")
    lines.append("</schedule_grid>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def resolve_default_schedule_grid_xml() -> Path | None:
    settings = get_settings()
    target = settings.data_folder / SCHEDULE_GRID_EXPORT_FILE_NAME
    return target if target.is_file() else None


def build_current_schedule_grid_xml_export() -> tuple[str, bytes]:
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
    target_date, roster_code, export_version, target_schedule_rows = export_target
    if not any(grid_row_matches_roster(getattr(row, "code", ""), roster_code) for row in target_schedule_rows):
        raise ScheduleGridNotFound(f"搵唔到 {roster_code} 行位表")
    exported_rows = _schedule_rows_to_grid_rows(target_schedule_rows)
    if not exported_rows:
        raise ScheduleGridNotFound(f"搵唔到 {target_date} {roster_code} 對應嘅行位表版本。")
    rows = [SCHEDULE_GRID_HEADER[:], *[list(row) for row in exported_rows if isinstance(row, (list, tuple))]]
    return export_version, build_schedule_grid_xml(
        rows,
        fallback_effective_date=export_version,
        section_date=target_date,
    )


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

    variants: list[dict[str, Any]] = []
    for code in code_order:
        variant_rows = _exact_schedule_rows_for_code_on_day(parsed_rows, code, target_day)
        exported_rows = _schedule_rows_to_grid_rows(variant_rows)
        if not exported_rows:
            continue
        variant_version = _schedule_grid_effective_iso(variant_rows) or export_version
        xml_data = build_schedule_grid_xml(
            [SCHEDULE_GRID_HEADER[:], *exported_rows],
            fallback_effective_date=variant_version,
            section_date=target_date,
        )
        variants.append(
            {
                "roster_code": code,
                "target_date": target_date,
                "effective_date": variant_version,
                "alarm_count": len(exported_rows),
                "is_current": grid_row_matches_roster(code, roster_code),
                "xml": xml_data.decode("utf-8"),
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
