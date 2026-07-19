"""Local FastAPI: web UI + date expression -> meal plan JSON."""

from __future__ import annotations

import os
import hashlib
import json
import copy
import time
import threading
import urllib.request
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from meal_planner.dates_input import DateValidationError, parse_date_expression
from meal_planner.excel_io import WorkbookValidationError, load_workbook_data
from meal_planner.free_port import free_tcp_port
from meal_planner.google_calendar_sync import authorize_google_calendar, check_nonwork_calendar_consistency, google_calendar_auth_status, sync_roster_to_google_calendar
from meal_planner.indicators import NUTRIENT_KEYS
from meal_planner.maintenance_db import (
    MAINTENANCE_SHEETS,
    MaintenanceDatabaseError,
    bootstrap_roster_code_definitions,
    bootstrap_sheet_from_workbook,
    list_maintenance_sheets,
    load_roster_code_definitions,
    load_sheet_rows,
    save_roster_code_definitions,
    save_sheet_rows,
)
from meal_planner.nutrition_db import (
    NutritionDatabaseError,
    load_catalog_entries,
    load_nutrition_profile,
    load_target_settings,
    load_target_rows,
    save_catalog_entries,
    save_nutrition_profile,
    save_target_settings,
    save_target_rows,
)
from meal_planner.preview import (
    IndicatorDataError,
    preview_days,
    recalc_days_from_edits,
    refresh_payload_with_latest_indicators,
)
from meal_planner.settings import (
    get_settings,
    save_folder_settings,
    save_rice_detail_settings,
)
from meal_planner.roster import code_for_date, is_work_day, roster_for_month
from meal_planner.schedule_grid import load_schedule_rows_from_rows, rows_for_roster
from meal_planner.storage import (
    load_active_panel,
    load_active_config_view,
    load_active_menu_path,
    load_column_widths,
    load_form_column_widths,
    load_google_calendar_sync_settings,
    load_latest_versions,
    load_menu_hidden_keys,
    load_menu_labels,
    load_menu_order,
    load_menu_tree_open,
    load_memory_payload,
    load_sidebar_width,
    load_show_past,
    load_target_editor_layout,
    merge_memory_payload,
    save_active_panel,
    save_active_config_view,
    save_active_menu_path,
    save_column_widths,
    save_form_column_widths,
    save_google_calendar_sync_settings,
    save_menu_hidden_keys,
    save_menu_labels,
    save_menu_order,
    save_menu_tree_open,
    save_memory_payload,
    save_show_past,
    save_sidebar_width,
    save_target_editor_layout,
)

_WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="Meal Planner", version="0.2.0")

_STARTED_AT = time.time()
_DEBUG_STATS: dict[str, Any] = {
    "requests_total": 0,
    "errors_total": 0,
    "by_path": {},
    "by_status": {},
    "last_error": None,
}
_LAST_SCHEDULE_GRID_EXPORT_VERSION: str | None = None
_PHONE_SCHEDULE_GRID_EXPORT_URL = "http://192.168.15.102:8765/export.xml"
_PHONE_SCHEDULE_GRID_PENDING_XML: bytes | None = None
_PHONE_SCHEDULE_GRID_PENDING_LOCK = threading.Lock()
_DESKTOP_LAN_HOST = "192.168.15.125"
_DESKTOP_LAN_SERVER = f"http://{_DESKTOP_LAN_HOST}:8765"


def _error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def _normalise_error_detail(detail: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("error") or "Request failed")
        details = {k: v for k, v in detail.items() if k not in {"message", "error"}}
        return message, details
    return str(detail or "Request failed"), {}


def _error_code_for_status(status_code: int) -> str:
    if status_code == 400:
        return "bad_request"
    if status_code == 404:
        return "not_found"
    if status_code == 422:
        return "validation_error"
    if status_code >= 500:
        return "internal_error"
    return "request_error"


def _record_request(path: str, status_code: int, elapsed_ms: float) -> None:
    _DEBUG_STATS["requests_total"] += 1
    by_status = _DEBUG_STATS["by_status"]
    by_status[str(status_code)] = int(by_status.get(str(status_code), 0)) + 1
    by_path = _DEBUG_STATS["by_path"]
    row = by_path.setdefault(path, {"count": 0, "errors": 0, "last_ms": 0.0})
    row["count"] = int(row.get("count", 0)) + 1
    row["last_ms"] = round(elapsed_ms, 1)
    if status_code >= 400:
        _DEBUG_STATS["errors_total"] += 1
        row["errors"] = int(row.get("errors", 0)) + 1


def _health_payload() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": app.version,
        "primary_data_source": "sqlite",
        "excel_role": "import_only",
        "project_root": str(settings.project_root),
        "system_folder": str(settings.system_folder),
        "data_folder": str(settings.data_folder),
        "workbook": str(settings.workbook_path),
        "workbook_exists": settings.workbook_path.is_file(),
        "database": str(settings.database_path),
        "database_exists": settings.database_path.is_file(),
    }


@app.middleware("http")
async def record_debug_stats(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _record_request(request.url.path, response.status_code, elapsed_ms)
    response.headers["X-MealPlanner-Elapsed-Ms"] = f"{elapsed_ms:.1f}"
    return response


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message, details = _normalise_error_detail(exc.detail)
    code = _error_code_for_status(exc.status_code)
    _DEBUG_STATS["last_error"] = {
        "path": request.url.path,
        "status": exc.status_code,
        "code": code,
        "message": message,
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(code, message, details),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    code = "validation_error"
    message = "Request validation failed"
    details = {"errors": exc.errors()}
    _DEBUG_STATS["last_error"] = {
        "path": request.url.path,
        "status": 422,
        "code": code,
        "message": message,
    }
    return JSONResponse(status_code=422, content=_error_payload(code, message, details))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    code = "internal_error"
    message = str(exc) or exc.__class__.__name__
    _DEBUG_STATS["last_error"] = {
        "path": request.url.path,
        "status": 500,
        "code": code,
        "message": message,
    }
    return JSONResponse(status_code=500, content=_error_payload(code, message))


class PreviewRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    dates_expr: str
    reroll_nonce: int = 0
    fast_mode: bool = True


class RecalcDayRequest(BaseModel):
    date: str
    nutrient_indicators: dict[str, Any] = Field(default_factory=dict)
    meal_plan: dict[str, Any] = Field(default_factory=dict)
    edited_lines: dict[str, str] = Field(default_factory=dict)


class RecalcRequest(BaseModel):
    days: list[RecalcDayRequest] = Field(default_factory=list)


class UiStateRequest(BaseModel):
    column_widths: dict[str, float] | None = None
    sidebar_width: float | None = None
    target_editor_width: float | None = None
    target_column_widths: dict[str, float] | None = None
    catalog_column_widths: dict[str, float] | None = None
    form_column_widths: dict[str, float] | None = None
    show_past: bool | None = None
    active_panel: str | None = None
    active_config_view: str | None = None
    active_menu_path: list[str] | None = None
    menu_order: dict[str, list[str]] | None = None
    menu_labels: dict[str, str] | None = None
    menu_hidden_keys: list[str] | None = None
    menu_tree_open: dict[str, bool] | None = None
    google_calendar_sync: dict[str, Any] | None = None


class MemoryPayloadRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class TargetRowsRequest(BaseModel):
    headers: list[Any] = Field(default_factory=list)
    workday: list[Any] = Field(default_factory=list)
    nonworkday: list[Any] = Field(default_factory=list)
    profile: dict[str, Any] | None = None
    target_settings: dict[str, Any] | None = None


class CatalogRowsRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DetailSettingsRequest(BaseModel):
    cooked_to_raw_brown: float = Field(..., gt=0)
    cooked_to_raw_other: float = Field(..., gt=0)
    system_folder: str | None = None
    data_folder: str | None = None
    google_calendar_sync: dict[str, Any] | None = None
    roster_code_definitions: list[dict[str, Any]] = Field(default_factory=list)


class MaintenanceSheetRequest(BaseModel):
    rows: list[list[Any]] = Field(default_factory=list)


class RosterCalendarConsistencyRequest(BaseModel):
    roster_text: str = ""


class DutyReportOverrideRequest(BaseModel):
    mode: str | None = None
    segments: list[dict[str, str]] | None = None
    slot: dict[str, Any] | None = None
    source: str = "web"
    date_iso: str | None = None


class DutyReportSendRequest(BaseModel):
    slot_id: str
    source: str = "web"
    date_iso: str | None = None


class DutyReportConfigRequest(BaseModel):
    mapping: dict[str, str] | None = None
    message_template: str | None = None
    auto_send: bool | None = None


class OnOffDutyLogRequest(BaseModel):
    kind: str
    status: str = "opened"
    source: str = "web"
    date_iso: str | None = None


class OnOffDutyConfigRequest(BaseModel):
    auto_send: bool | None = None


class OnOffDutyOverrideRequest(BaseModel):
    date_iso: str | None = None
    start: str | None = None
    end: str | None = None
    note: str | None = None


class OnOffDutyLateOffRequest(BaseModel):
    action: str  # hold | release | send_now
    note: str = ""


class OnOffDutyRosterCodeRequest(BaseModel):
    date_iso: str | None = None
    code: str


def _stored_meal_plan_payloads(date_isos: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not date_isos:
        return found

    payload = load_memory_payload()
    days = payload.get("days") if isinstance(payload, dict) else []
    if isinstance(days, list):
        for item in days:
            if not isinstance(item, dict):
                continue
            date_text = str(item.get("date") or "")
            if date_text in date_isos:
                found[date_text] = item

    missing = sorted(date_isos - set(found))
    if missing:
        latest = load_latest_versions(missing)
        latest_days = latest.get("days") if isinstance(latest, dict) else []
        if isinstance(latest_days, list):
            for item in latest_days:
                if not isinstance(item, dict):
                    continue
                date_text = str(item.get("date") or "")
                if date_text in date_isos:
                    found[date_text] = item
    return found


def _meal_time_minutes(raw: Any) -> int | None:
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", str(raw or ""))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _first_meal_minutes(day_payload: dict[str, Any]) -> int | None:
    meal_plan = day_payload.get("meal_plan") if isinstance(day_payload, dict) else None
    if not isinstance(meal_plan, dict):
        return None
    minutes: list[int] = []
    resolved = meal_plan.get("meal_times_resolved")
    primary = meal_plan.get("primary_rule")
    for meal in ("早餐", "午餐", "小食", "晚餐"):
        raw = resolved.get(meal) if isinstance(resolved, dict) else None
        minute_value = _meal_time_minutes(raw)
        if minute_value is None and isinstance(primary, dict):
            minute_value = _meal_time_minutes(primary.get(meal))
        if minute_value is not None:
            minutes.append(minute_value)
    return min(minutes) if minutes else None


def _can_regenerate_existing_today(day_payload: dict[str, Any], now: datetime) -> bool:
    first_meal = _first_meal_minutes(day_payload)
    if first_meal is None:
        return False
    now_minutes = now.hour * 60 + now.minute
    return now_minutes < first_meal


def _preview_regeneration_blocked_dates(dates: list[date]) -> list[date]:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.dates.timezone))
    today = now.date()
    requested = sorted(set(dates))
    stored_payloads = _stored_meal_plan_payloads({d.isoformat() for d in requested if d == today})
    blocked: list[date] = []
    for requested_date in requested:
        if requested_date < today:
            blocked.append(requested_date)
            continue
        day_payload = stored_payloads.get(requested_date.isoformat())
        if requested_date == today and day_payload and not _can_regenerate_existing_today(day_payload, now):
            blocked.append(requested_date)
    return blocked


def _raise_if_preview_regeneration_blocked(dates: list[date]) -> None:
    blocked = _preview_regeneration_blocked_dates(dates)
    if not blocked:
        return
    raise HTTPException(
        status_code=400,
        detail={
            "message": "今日第一餐後及過去嘅餐單唔可以重新生成；今日只有喺餐單未存在或第一餐前先可以生成。",
            "rejected": [d.isoformat() for d in blocked],
        },
    )


def _validate_maintenance_key(sheet_key: str) -> str:
    valid = {key for key, _ in MAINTENANCE_SHEETS}
    if sheet_key not in valid:
        raise HTTPException(status_code=404, detail=f"Unknown maintenance sheet: {sheet_key}")
    return sheet_key


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_SCHEDULE_GRID_HEADER_RE = re.compile(
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
_SCHEDULE_GRID_HEADER = ["更碼", "時間", "內容", "時長", "生效日期"]
_BLANK_EFFECTIVE_DATE_SENTINEL = "0001-01-01"
_SCHEDULE_GRID_EXPORT_FILE_NAME = "export.xml"


def _extract_xml_texts(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    return [
        text.strip()
        for text in root.itertext()
        if isinstance(text, str) and text.strip()
    ]


def _schedule_grid_xml_metadata(xml_bytes: bytes) -> tuple[str | None, str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None, ""
    effective = _normalize_schedule_grid_effective_date(root.attrib.get("effective_date", ""))
    roster_code = str(root.attrib.get("roster_code", "") or "").strip()
    return (effective or None), roster_code


def _apply_schedule_grid_xml_metadata(
    rows: list[list[Any]],
    *,
    effective_version: str | None,
    roster_code: str,
) -> list[list[Any]]:
    normalized_version = (
        _normalize_schedule_grid_effective_date(str(effective_version).strip())
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
        if normalized_version and not _normalize_schedule_grid_effective_date(row[4]):
            row[4] = normalized_version
    return rows


def _parse_header_date(raw: str) -> str:
    text = raw.strip()
    match = _SCHEDULE_GRID_HEADER_RE.fullmatch(text)
    if match:
        if match.group(1).count("-") == 2:
            return match.group(1)
        day = int(match.group(2))
        month = int(match.group(3))
        year = int(match.group(4))
        return f"{year:04d}-{month:02d}-{day:02d}"
    raise HTTPException(status_code=400, detail=f"Invalid header date: {raw}")


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


def _normalize_schedule_grid_effective_date(raw: Any) -> str:
    normalized = _parse_date_iso(str(raw).strip())
    if normalized == _BLANK_EFFECTIVE_DATE_SENTINEL:
        return ""
    return normalized


def _time_to_minutes(raw_time: str) -> int:
    token = raw_time.strip()
    if not _TIME_RE.fullmatch(token):
        return -1
    hour, minute = token.split(":", 1)
    return int(hour) * 60 + int(minute)


def _collect_roster_cell_texts(rows: list[list[Any]]) -> list[str | None]:
    out: list[str | None] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        for value in row:
            if value is None:
                continue
            out.append(str(value))
    return out


def _roster_workday_code_map(sheet_rows: list[Any]) -> dict[tuple[int, int], Any]:
    row_lists = sheet_rows if isinstance(sheet_rows, list) else []
    return roster_for_month(_collect_roster_cell_texts(row_lists))


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


def _next_workday_schedule_from(
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
        current += timedelta(days=1)
    return None, None, []


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

    roster_map = _roster_workday_code_map(roster_rows)
    if not roster_map:
        return None

    candidate_date, code, candidate_rows = _next_workday_schedule_from(
        now.date(),
        roster_map,
        parsed_rows,
    )
    if candidate_date is None or not code or not candidate_rows:
        candidate_date, code, candidate_rows = _latest_workday_schedule_before(
            now.date() - timedelta(days=1),
            roster_map,
            parsed_rows,
        )
        if candidate_date is None or not code or not candidate_rows:
            return None

    if candidate_date == now.date():
        _, max_time = _schedule_day_minutes(candidate_rows)
        if max_time >= 0 and now_minutes > max_time:
            next_date, next_code, next_rows = _next_workday_schedule_from(
                candidate_date + timedelta(days=1),
                roster_map,
                parsed_rows,
            )
            if next_date is None or not next_code or not next_rows:
                return None
            candidate_date = next_date
            code = next_code
            candidate_rows = next_rows

    if not candidate_rows:
        return None

    return candidate_date.isoformat(), str(code), _schedule_grid_effective_iso(candidate_rows), candidate_rows


def _parse_schedule_grid_rows_by_version(rows: list[list[Any]], effective_iso: str) -> list[list[Any]]:
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        effective = (
            _normalize_schedule_grid_effective_date(row[4])
            if len(row) >= 5
            else ""
        )
        if effective == effective_iso:
            out.append(list(row))
    return out


def _rows_for_dates(
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
            (_normalize_schedule_grid_effective_date(row[4]) if len(row) >= 5 else "")
            in dates
        )
        and (
            ("" if row[0] is None else str(row[0]).strip()) in imported_codes
        )
    ]


def _extract_schedule_grid_effective_dates(
    imported_rows: list[list[Any]],
    existing_rows: list[Any],
) -> set[str]:
    if not isinstance(imported_rows, list):
        return set()

    versions: set[str] = set()
    for row in imported_rows[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        effective = _normalize_schedule_grid_effective_date(row[4])
        if effective:
            versions.add(effective)

    return versions


def _collect_schedule_grid_import_codes(rows: list[list[Any]]) -> set[str]:
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


def _parse_schedule_grid_texts(rows: list[str]) -> tuple[list[list[Any]], set[str]]:
    rows_out: list[list[Any]] = [_SCHEDULE_GRID_HEADER[:]]
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
            current_effective = _normalize_schedule_grid_effective_date(_parse_header_date(token))
            i += 1
            continue

        header_match = _SCHEDULE_GRID_HEADER_RE.fullmatch(token)
        if header_match:
            current_effective = _normalize_schedule_grid_effective_date(_parse_header_date(token))
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
                if _TIME_RE.match(next_token) or _SCHEDULE_GRID_DATE_ONLY_RE.fullmatch(next_token) or _SCHEDULE_GRID_HEADER_RE.fullmatch(next_token):
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
        raise HTTPException(status_code=400, detail="No alarm rows found in the uploaded XML.")

    imported_dates: set[str] = set()
    for row in rows_out[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        effective = _normalize_schedule_grid_effective_date(row[4])
        if effective:
            imported_dates.add(effective)
    return rows_out, imported_dates


def _merge_schedule_grid_rows_for_import(
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
            effective = _normalize_schedule_grid_effective_date(row[4])
        code = ("" if len(row) <= 0 or row[0] is None else str(row[0]).strip())
        if imported_codes and effective in imported_dates and code in imported_codes:
            continue
        kept_rows.append(list(row))
    merged = [_SCHEDULE_GRID_HEADER[:]]
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


def _build_schedule_grid_xml(
    rows: list[list[Any]],
    *,
    fallback_effective_date: str | None = None,
    section_date: str | None = None,
) -> bytes:
    root_effective_version: str | None = (
        _normalize_schedule_grid_effective_date(str(fallback_effective_date).strip())
        if fallback_effective_date is not None
        else None
    )
    if root_effective_version is None:
        for row in rows[1:]:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                continue
            row_version = _normalize_schedule_grid_effective_date(row[4])
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
        date_value = _normalize_schedule_grid_effective_date(row[4]) if len(row) >= 5 else ""
        iso = (
            _normalize_schedule_grid_effective_date(section_date)
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


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    return _health_payload()


@app.get("/api/debug/stats")
def api_debug_stats() -> dict[str, Any]:
    return {
        "ok": True,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "stats": _DEBUG_STATS,
        "health": _health_payload(),
    }


def _resolve_default_schedule_grid_xml() -> Path | None:
    settings = get_settings()
    target = settings.data_folder / _SCHEDULE_GRID_EXPORT_FILE_NAME
    return target if target.is_file() else None


def _build_current_schedule_grid_xml_export() -> tuple[str, bytes]:
    settings = get_settings()
    try:
        sheet = load_sheet_rows("schedule_grid", settings)
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Export schedule_grid XML failed: {e}") from e
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
        raise HTTPException(status_code=404, detail="更表之後冇返工日記錄")
    target_date, roster_code, export_version, target_schedule_rows = export_target
    if not any(str(getattr(row, "code", "") or "").strip() == roster_code for row in target_schedule_rows):
        raise HTTPException(status_code=404, detail=f"搵唔到 {roster_code} 行位表")
    global _LAST_SCHEDULE_GRID_EXPORT_VERSION
    _LAST_SCHEDULE_GRID_EXPORT_VERSION = export_version
    exported_rows = _schedule_rows_to_grid_rows(target_schedule_rows)
    if not exported_rows:
        raise HTTPException(status_code=404, detail=f"搵唔到 {target_date} {roster_code} 對應嘅行位表版本。")
    rows = [_SCHEDULE_GRID_HEADER[:], *[list(row) for row in exported_rows if isinstance(row, (list, tuple))]]
    return export_version, _build_schedule_grid_xml(
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
    matched = [row for row in parsed_rows if str(getattr(row, "code", "") or "").strip() == code]
    dated = [
        row for row in matched
        if getattr(row, "effective_from", None) is not None
        and getattr(row, "effective_from") <= target_day
    ]
    if dated:
        latest = max(getattr(row, "effective_from") for row in dated)
        return [row for row in dated if getattr(row, "effective_from") == latest]
    return [row for row in matched if getattr(row, "effective_from", None) is None]


def _build_schedule_grid_all_variants_export() -> dict[str, Any]:
    settings = get_settings()
    try:
        sheet = load_sheet_rows("schedule_grid", settings)
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Export schedule_grid XML failed: {e}") from e
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
        raise HTTPException(status_code=404, detail="更表之後冇返工日記錄")
    target_date, roster_code, export_version, _ = export_target
    try:
        target_day = datetime.fromisoformat(target_date).date()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Invalid schedule target date: {target_date}") from e

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
        xml_data = _build_schedule_grid_xml(
            [_SCHEDULE_GRID_HEADER[:], *exported_rows],
            fallback_effective_date=variant_version,
            section_date=target_date,
        )
        variants.append(
            {
                "roster_code": code,
                "target_date": target_date,
                "effective_date": variant_version,
                "alarm_count": len(exported_rows),
                "is_current": code == roster_code,
                "xml": xml_data.decode("utf-8"),
            }
        )
    if not variants:
        raise HTTPException(status_code=404, detail=f"搵唔到 {target_date} 可用嘅行位表版本。")
    if roster_code and not any(item["is_current"] for item in variants):
        raise HTTPException(status_code=404, detail=f"搵唔到 {roster_code} 行位表")
    return {
        "ok": True,
        "target_date": target_date,
        "current_roster_code": roster_code,
        "effective_date": export_version,
        "variant_count": len(variants),
        "variants": variants,
    }


@app.get("/")
def index_page() -> FileResponse:
    path = _WEB_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Cannot find index.html")
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/apk")
def phone_apk() -> FileResponse:
    # 電話出街經 meshnet 用瀏覽器下載最新 build（adb 條線太飄時嘅後備安裝路徑）。
    # 必須排喺 /{asset_name} catch-all 之前，否則會被佢截咗。
    path = _WEB_DIR.parent.parent / "android_alarm_app" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Cannot find app-debug.apk (build first)")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename="oneshotalarm.apk",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/{asset_name}")
def web_asset(asset_name: str) -> FileResponse:
    if asset_name not in {
        "style.css",
        "api.js",
        "shopping.js",
        "planner.js",
        "planner-menu.js",
        "planner-maint.js",
        "planner-maint-editor.js",
        "planner-config.js",
        "planner-render.js",
        "planner-events.js",
        "planner-duty.js",
        "planner-onoffduty.js",
        "favicon.svg",
    }:
        raise HTTPException(status_code=404, detail="Cannot find web asset")
    path = _WEB_DIR / asset_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Cannot find {asset_name}")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.post("/api/preview")
def api_preview(body: PreviewRequest) -> dict[str, Any]:
    try:
        dates = parse_date_expression(body.dates_expr, year=body.year, month=body.month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    _raise_if_preview_regeneration_blocked(dates)

    try:
        payload = preview_days(
            dates,
            reroll_nonce=body.reroll_nonce,
            fast_mode=body.fast_mode,
        )
        return payload
    except DateValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"message": str(e), "rejected": [d.isoformat() for d in e.rejected_dates]},
        ) from e
    except IndicatorDataError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read workbook: {e}") from e


@app.get("/api/mobile-meal-plan")
def api_mobile_meal_plan(date_iso: str, meta_only: bool = False) -> dict[str, Any]:
    try:
        target_date = date.fromisoformat(str(date_iso).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="date_iso must be YYYY-MM-DD.") from e

    try:
        payload = load_memory_payload()
        if isinstance(payload.get("days"), list):
            payload = refresh_payload_with_latest_indicators(payload)
        day_payload = next(
            (
                item for item in (payload.get("days", []) if isinstance(payload.get("days"), list) else [])
                if isinstance(item, dict) and str(item.get("date") or "") == target_date.isoformat()
            ),
            None,
        )
        if day_payload is None:
            latest = load_latest_versions([target_date.isoformat()])
            latest_days = latest.get("days", []) if isinstance(latest.get("days"), list) else []
            if latest_days:
                payload = {
                    "headers": payload.get("headers", []),
                    "indicator_rows": payload.get("indicator_rows", {}),
                    "nutrient_keys": payload.get("nutrient_keys", list(NUTRIENT_KEYS)),
                    "days": latest_days,
                }
                payload = refresh_payload_with_latest_indicators(payload)
                day_payload = next(
                    (
                        item for item in (payload.get("days", []) if isinstance(payload.get("days"), list) else [])
                        if isinstance(item, dict) and str(item.get("date") or "") == target_date.isoformat()
                    ),
                    None,
                )
        if day_payload is None:
            return {
                "ok": False,
                "date": target_date.isoformat(),
                "content_version": "",
                "message": "Meal plan has not been generated for this date.",
            }
        day_payload = _with_mobile_restaurant_lunch_label(day_payload)
        # 更碼即場跟更表（權威）——snapshot 生成後更表可能改咗（例如電話現場轉更）。
        # 有出入時用現時碼顯示，並標記餐單內容仍按舊碼生成（要重新生成先跟得切）。
        try:
            from meal_planner.duty_form import roster_code_for

            live_code = roster_code_for(get_settings(), target_date)
        except Exception:
            live_code = ""
        stored_code = str(day_payload.get("roster_code") or "").strip()
        if live_code and live_code != stored_code:
            day_payload["roster_code"] = live_code
            day_payload["stale_plan_code"] = stored_code
        content_seed = {
            "date": target_date.isoformat(),
            "headers": payload.get("headers", []),
            "nutrient_keys": payload.get("nutrient_keys", list(NUTRIENT_KEYS)),
            "day": day_payload,
        }
        content_version = hashlib.sha1(
            json.dumps(content_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        settings = get_settings()
        if meta_only:
            return {
                "ok": True,
                "date": target_date.isoformat(),
                "content_version": content_version,
            }
        return {
            "ok": True,
            "date": target_date.isoformat(),
            "content_version": content_version,
            "headers": payload.get("headers", []),
            "nutrient_keys": payload.get("nutrient_keys", list(NUTRIENT_KEYS)),
            "day": day_payload,
            "rice_settings": {
                "cooked_to_raw_brown": settings.rice.cooked_to_raw_brown,
                "cooked_to_raw_other": settings.rice.cooked_to_raw_other,
                "water_multiplier": settings.rice.water_multiplier,
            },
            "nutrition_format": {
                "kcal_per_fat_g": settings.nutrition_format.kcal_per_fat_g,
            },
        }
    except IndicatorDataError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot build mobile meal plan: {e}") from e


def _with_mobile_restaurant_lunch_label(day_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(day_payload, dict):
        return day_payload
    out = copy.deepcopy(day_payload)
    meal_plan = out.get("meal_plan")
    if not isinstance(meal_plan, dict):
        return out
    rest = meal_plan.get("restaurant_lunch")
    if not isinstance(rest, dict) or not isinstance(rest.get("nutrients"), dict):
        return out
    ingredients = meal_plan.get("meal_ingredients")
    if not isinstance(ingredients, dict):
        ingredients = {}
        meal_plan["meal_ingredients"] = ingredients
    lunch_items = ingredients.get("午餐")
    if isinstance(lunch_items, list) and any(str(x).strip() for x in lunch_items):
        return out
    choice = str(rest.get("choice") or "").strip()
    store = str(rest.get("store") or "").strip()
    if choice or store:
        label = f'Lunch — "{choice}"'
        if store:
            label += f" ({store})"
    else:
        label = "Lunch — restaurant meal"
    ingredients["午餐"] = [label]
    items = meal_plan.get("meal_items")
    if not isinstance(items, dict):
        items = {}
        meal_plan["meal_items"] = items
    items["午餐"] = []
    return out


@app.post("/api/recalc")
def api_recalc(body: RecalcRequest) -> dict[str, Any]:
    try:
        payload = [x.model_dump() for x in body.days]
        return recalc_days_from_edits(payload)
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {e}") from e


@app.get("/api/memory-list")
def api_memory_list_get() -> dict[str, Any]:
    try:
        payload = load_memory_payload()
        if isinstance(payload.get("days"), list):
            payload = refresh_payload_with_latest_indicators(payload)
            save_memory_payload(payload)
        return {"payload": payload}
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load memory list failed: {e}") from e


@app.post("/api/memory-list")
def api_memory_list_set(body: MemoryPayloadRequest) -> dict[str, Any]:
    try:
        payload = merge_memory_payload(load_memory_payload(), body.payload)
        save_memory_payload(payload)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save memory list failed: {e}") from e


@app.get("/api/shopping-catalog")
def api_shopping_catalog() -> dict[str, Any]:
    try:
        settings = get_settings()
        entries = load_catalog_entries(settings)
        by_name = {e.name: e.category for e in entries}
        return {
            "by_name": by_name,
            "rice": {
                "cooked_to_raw_brown": settings.rice.cooked_to_raw_brown,
                "cooked_to_raw_other": settings.rice.cooked_to_raw_other,
                "note_name_contains": list(settings.rice.note_name_contains),
                "brown_name_contains": settings.rice.brown_name_contains,
            },
        }
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Load shopping catalog failed: {e}") from e


def _detail_settings_payload() -> dict[str, Any]:
    settings = get_settings()
    return {
        "folders": {
            "system_folder": str(settings.system_folder),
            "data_folder": str(settings.data_folder),
        },
        "rice": {
            "cooked_to_raw_brown": settings.rice.cooked_to_raw_brown,
            "cooked_to_raw_other": settings.rice.cooked_to_raw_other,
        },
        "google_calendar_sync": load_google_calendar_sync_settings(),
        "roster_code_definitions": load_roster_code_definitions(settings),
    }


@app.get("/api/detail-settings")
def api_get_detail_settings() -> dict[str, Any]:
    try:
        return _detail_settings_payload()
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load detail settings failed: {e}") from e


@app.post("/api/detail-settings")
def api_set_detail_settings(body: DetailSettingsRequest) -> dict[str, Any]:
    try:
        save_rice_detail_settings(
            cooked_to_raw_brown=body.cooked_to_raw_brown,
            cooked_to_raw_other=body.cooked_to_raw_other,
        )
        if body.system_folder is not None or body.data_folder is not None:
            current = get_settings()
            save_folder_settings(
                system_folder=body.system_folder if body.system_folder is not None else str(current.system_folder),
                data_folder=body.data_folder if body.data_folder is not None else str(current.data_folder),
            )
        if body.google_calendar_sync is not None:
            save_google_calendar_sync_settings(body.google_calendar_sync)
        save_roster_code_definitions(body.roster_code_definitions, get_settings())
        return {"ok": True, **_detail_settings_payload()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save detail settings failed: {e}") from e


@app.get("/api/maint/sheets")
def api_maint_sheets() -> dict[str, Any]:
    try:
        return {"sheets": list_maintenance_sheets(get_settings())}
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load maintenance sheets failed: {e}") from e


@app.get("/api/maint/sheets/{sheet_key}")
def api_maint_sheet(sheet_key: str) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key(sheet_key)
    try:
        return load_sheet_rows(sheet_key, get_settings())
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MaintenanceDatabaseError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e} Use Import to load this sheet from Excel.",
        ) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load maintenance sheet failed: {e}") from e


@app.post("/api/maint/sheets/{sheet_key}")
def api_save_maint_sheet(sheet_key: str, body: MaintenanceSheetRequest) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key(sheet_key)
    try:
        settings = get_settings()
        response = {"ok": True, **save_sheet_rows(sheet_key, body.rows, settings)}
        if sheet_key == "roster":
            try:
                response["google_calendar_sync"] = sync_roster_to_google_calendar(body.rows, settings)
            except Exception as e:
                response["google_calendar_sync"] = {"status": "error", "detail": str(e)}
        return response
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown maintenance sheet: {sheet_key}") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save maintenance sheet failed: {e}") from e


@app.post("/api/google-calendar/roster-sync")
def api_google_calendar_roster_sync() -> dict[str, Any]:
    try:
        settings = get_settings()
        payload = load_sheet_rows("roster", settings)
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        return {"ok": True, **sync_roster_to_google_calendar(rows if isinstance(rows, list) else [], settings)}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Calendar roster sync failed: {e}") from e


@app.post("/api/maint/sheets/{sheet_key}/import")
def api_import_maint_sheet(sheet_key: str) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key(sheet_key)
    try:
        settings = get_settings()
        wb = load_workbook_data(settings.workbook_path, validate=False)
        try:
            bootstrap_sheet_from_workbook(settings, wb, sheet_key, replace_existing=True)
        finally:
            wb.close()
        return {"ok": True, **load_sheet_rows(sheet_key, settings)}
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Import maintenance sheet failed: {e}") from e


@app.post("/api/maint/sheets/schedule_grid/import-xml")
async def api_import_schedule_grid_from_xml(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    data = await file.read()
    await file.close()
    return _import_schedule_grid_from_xml_bytes(data)


@app.post("/api/maint/sheets/schedule_grid/import-default-xml")
def api_import_schedule_grid_from_default_xml() -> dict[str, Any]:
    target = _resolve_default_schedule_grid_xml()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Default schedule_grid seed file not found: "
                f"{get_settings().data_folder / _SCHEDULE_GRID_EXPORT_FILE_NAME}"
            ),
        )
    try:
        data = target.read_bytes()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Read schedule_grid.xml failed: {e}") from e
    return _import_schedule_grid_from_xml_bytes(data)


def _import_schedule_grid_from_xml_bytes(data: bytes) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key("schedule_grid")
    settings = get_settings()
    if not data:
        raise HTTPException(status_code=400, detail="Empty XML upload.")
    try:
        rows = _parse_schedule_grid_texts(_extract_xml_texts(data))[0]
        seed_version, root_roster_code = _schedule_grid_xml_metadata(data)
        if seed_version is None:
            seed_version = _extract_seed_effective_version_from_xml_bytes(data)
        rows = _apply_schedule_grid_xml_metadata(
            rows,
            effective_version=seed_version,
            roster_code=root_roster_code,
        )
        rows, imported_dates = _fill_missing_schedule_grid_version(rows, seed_version)
    except HTTPException:
        raise
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML content: {e}") from e
    try:
        sheet = load_sheet_rows(sheet_key, settings)
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load existing schedule_grid failed: {e}") from e

    existing_rows = sheet.get("rows", [])
    imported_codes = _collect_schedule_grid_import_codes(rows)
    effective_versions = (
        imported_dates
        if imported_dates
        else _extract_schedule_grid_effective_dates(rows, existing_rows)
    )
    if not effective_versions:
        has_existing_rows = isinstance(existing_rows, list) and len(existing_rows) > 1
        if has_existing_rows:
            raise HTTPException(
                status_code=400,
                detail="Uploaded schedule_grid XML has no effective date version. "
                       "請重新從電腦匯出再更新 seed。",
            )
    imported_row_count = max(0, len(rows) - 1)
    replaced_row_count = len(_rows_for_dates(existing_rows, effective_versions, imported_codes))
    merged_rows = _merge_schedule_grid_rows_for_import(
        existing_rows,
        rows,
        effective_versions,
        imported_codes,
    )

    saved = save_sheet_rows(sheet_key, merged_rows, settings)
    return {
        "ok": True,
        **saved,
        "imported_row_count": imported_row_count,
        "replaced_row_count": replaced_row_count,
        "imported_versions": sorted(effective_versions),
    }


@app.get("/api/maint/sheets/schedule_grid/export-xml")
def api_export_schedule_grid_to_xml() -> Response:
    _, xml_data = _build_current_schedule_grid_xml_export()
    filename = _SCHEDULE_GRID_EXPORT_FILE_NAME
    return Response(
        content=xml_data,
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/maint/sheets/schedule_grid/export")
def api_export_schedule_grid_to_xml_compat() -> Response:
    return api_export_schedule_grid_to_xml()


@app.get("/api/maint/sheets/schedule_grid/export-all-xml")
def api_export_all_schedule_grid_to_xml() -> dict[str, Any]:
    return _build_schedule_grid_all_variants_export()


@app.post("/api/maint/sheets/schedule_grid/export-xml-to-file")
def api_export_schedule_grid_to_file() -> dict[str, Any]:
    settings = get_settings()
    version, xml_data = _build_current_schedule_grid_xml_export()
    target_path = settings.data_folder / _SCHEDULE_GRID_EXPORT_FILE_NAME
    try:
        settings.data_folder.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(xml_data)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save schedule_grid.xml to data folder failed: {e}") from e
    return {
        "ok": True,
        "path": str(target_path),
        "filename": _SCHEDULE_GRID_EXPORT_FILE_NAME,
        "size": len(xml_data),
        "effective_date": version,
    }


def _extract_seed_effective_version_from_xml_bytes(data: bytes) -> str | None:
    try:
        ET.fromstring(data)
    except ET.ParseError:
        return None
    for token in _extract_xml_texts(data):
        token = (token or "").strip()
        if not token:
            continue
        header_match = _SCHEDULE_GRID_HEADER_RE.fullmatch(token)
        if header_match:
            normalized = _normalize_schedule_grid_effective_date(_parse_header_date(token))
            if normalized:
                return normalized


def _fill_missing_schedule_grid_version(
    rows: list[list[Any]],
    fallback_version: str | None,
) -> tuple[list[list[Any]], set[str]]:
    if not rows:
        return rows, set()

    version_candidates: set[str] = set()
    for row in rows[1:]:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        version_candidates.add(_normalize_schedule_grid_effective_date(row[4]))
    version_candidates.discard("")
    if version_candidates:
        return rows, version_candidates

    if fallback_version is None:
        return rows, set()

    normalized = _normalize_schedule_grid_effective_date(str(fallback_version).strip())
    if not normalized:
        return rows, set()

    for row in rows[1:]:
        if not isinstance(row, (list, tuple)):
            continue
        while len(row) < 5:
            row.append("")
        row[4] = normalized
    return rows, {normalized}


def _import_schedule_grid_from_phone_bytes(data: bytes) -> dict[str, Any]:
    if not data:
        raise HTTPException(status_code=400, detail="No XML content uploaded.")
    try:
        rows = _parse_schedule_grid_texts(_extract_xml_texts(data))[0]
    except HTTPException:
        raise
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML content: {e}") from e

    effective_version, root_roster_code = _schedule_grid_xml_metadata(data)
    if effective_version is None:
        effective_version = _extract_seed_effective_version_from_xml_bytes(data)
    rows = _apply_schedule_grid_xml_metadata(
        rows,
        effective_version=effective_version,
        roster_code=root_roster_code,
    )
    rows, _ = _fill_missing_schedule_grid_version(rows, effective_version)
    normalized_data = _build_schedule_grid_xml(
        rows,
        fallback_effective_date=effective_version,
    )

    try:
        import_result = _import_schedule_grid_from_xml_bytes(normalized_data)
    except HTTPException:
        raise
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML content: {e}") from e

    return {
        **import_result,
        "ok": True,
    }


@app.post("/api/maint/sheets/schedule_grid/import-phone-push")
async def api_import_schedule_grid_from_phone_push(request: Request) -> dict[str, Any]:
    data = await request.body()
    result = _import_schedule_grid_from_phone_bytes(data)
    return {
        **result,
        "ok": True,
        "source": "phone_push",
    }


def _fetch_schedule_grid_xml_from_phone_ip() -> bytes:
    try:
        with urllib.request.urlopen(_PHONE_SCHEDULE_GRID_EXPORT_URL, timeout=12) as response:
            return response.read()
    except OSError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot fetch phone schedule_grid from {_PHONE_SCHEDULE_GRID_EXPORT_URL}: {e}",
        ) from e


@app.post("/api/maint/sheets/schedule_grid/preview-from-phone-ip")
def api_preview_schedule_grid_from_phone_ip() -> dict[str, Any]:
    xml_data = _fetch_schedule_grid_xml_from_phone_ip()
    try:
        rows = _parse_schedule_grid_texts(_extract_xml_texts(xml_data))[0]
        effective_version, root_roster_code = _schedule_grid_xml_metadata(xml_data)
        if effective_version is None:
            effective_version = _extract_seed_effective_version_from_xml_bytes(xml_data)
        rows = _apply_schedule_grid_xml_metadata(
            rows,
            effective_version=effective_version,
            roster_code=root_roster_code,
        )
        rows, imported_dates = _fill_missing_schedule_grid_version(rows, effective_version)
        normalized_data = _build_schedule_grid_xml(
            rows,
            fallback_effective_date=effective_version,
        )
    except HTTPException:
        raise
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML content: {e}") from e

    with _PHONE_SCHEDULE_GRID_PENDING_LOCK:
        global _PHONE_SCHEDULE_GRID_PENDING_XML
        _PHONE_SCHEDULE_GRID_PENDING_XML = normalized_data

    return {
        "ok": True,
        "source": "phone_ip",
        "phone_url": _PHONE_SCHEDULE_GRID_EXPORT_URL,
        "rows": rows,
        "row_count": max(0, len(rows) - 1),
        "imported_versions": sorted(imported_dates),
        "pending": True,
    }


@app.post("/api/maint/sheets/schedule_grid/confirm-phone-ip-import")
def api_confirm_schedule_grid_from_phone_ip() -> dict[str, Any]:
    with _PHONE_SCHEDULE_GRID_PENDING_LOCK:
        global _PHONE_SCHEDULE_GRID_PENDING_XML
        xml_data = _PHONE_SCHEDULE_GRID_PENDING_XML
        _PHONE_SCHEDULE_GRID_PENDING_XML = None
    if not xml_data:
        raise HTTPException(status_code=400, detail="No pending phone schedule_grid import. Press import first.")
    result = _import_schedule_grid_from_xml_bytes(xml_data)
    return {
        **result,
        "ok": True,
        "phone_url": _PHONE_SCHEDULE_GRID_EXPORT_URL,
        "source": "phone_ip",
    }


@app.get("/api/targets")
def api_get_targets() -> dict[str, Any]:
    settings = get_settings()
    try:
        try:
            headers, workday, nonworkday = load_target_rows(settings)
        except NutritionDatabaseError:
            wb = load_workbook_data(settings.workbook_path)
            try:
                headers, workday, nonworkday = load_target_rows(settings, wb)
            finally:
                wb.close()
        return {
            "headers": headers,
            "nutrient_keys": list(NUTRIENT_KEYS),
            "indicator_rows": {
                "workday": workday,
                "nonworkday": nonworkday,
            },
            "profile": load_nutrition_profile(settings),
            "target_settings": load_target_settings(settings),
        }
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load targets failed: {e}") from e


@app.post("/api/targets")
def api_set_targets(body: TargetRowsRequest) -> dict[str, Any]:
    try:
        headers, workday, nonworkday = save_target_rows(
            body.headers,
            body.workday,
            body.nonworkday,
            get_settings(),
        )
        profile = (
            save_nutrition_profile(body.profile, get_settings())
            if body.profile is not None
            else load_nutrition_profile(get_settings())
        )
        target_settings = (
            save_target_settings(body.target_settings, get_settings())
            if body.target_settings is not None
            else load_target_settings(get_settings())
        )
        return {
            "ok": True,
            "headers": headers,
            "nutrient_keys": list(NUTRIENT_KEYS),
            "indicator_rows": {
                "workday": workday,
                "nonworkday": nonworkday,
            },
            "profile": profile,
            "target_settings": target_settings,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save targets failed: {e}") from e


def _catalog_entry_payload(entry) -> dict[str, Any]:
    return {
        "row_index": entry.row_index,
        "paused": entry.paused,
        "category": entry.category,
        "name": entry.name,
        "min_g": entry.min_g,
        "max_g": entry.max_g,
        "daymax_g": entry.daymax_g,
        "nutrients": {key: float(entry.nutrients.get(key, 0.0)) for key in NUTRIENT_KEYS},
    }


@app.get("/api/nutrition-catalog")
def api_get_nutrition_catalog() -> dict[str, Any]:
    settings = get_settings()
    try:
        try:
            entries = load_catalog_entries(settings)
        except NutritionDatabaseError:
            wb = load_workbook_data(settings.workbook_path)
            try:
                entries = load_catalog_entries(settings, wb)
            finally:
                wb.close()
        return {
            "nutrient_keys": list(NUTRIENT_KEYS),
            "rows": [_catalog_entry_payload(entry) for entry in entries],
        }
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load nutrition catalog failed: {e}") from e


@app.post("/api/nutrition-catalog")
def api_set_nutrition_catalog(body: CatalogRowsRequest) -> dict[str, Any]:
    try:
        entries = save_catalog_entries(body.rows, get_settings())
        return {
            "ok": True,
            "nutrient_keys": list(NUTRIENT_KEYS),
            "rows": [_catalog_entry_payload(entry) for entry in entries],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save nutrition catalog failed: {e}") from e


@app.get("/api/ui-state")
def api_get_ui_state() -> dict[str, Any]:
    target_editor_width, target_column_widths, catalog_column_widths = load_target_editor_layout()
    return {
        "column_widths": load_column_widths(),
        "sidebar_width": load_sidebar_width(),
        "target_editor_width": target_editor_width,
        "target_column_widths": target_column_widths,
        "catalog_column_widths": catalog_column_widths,
        "form_column_widths": load_form_column_widths(),
        "show_past": load_show_past(),
        "active_panel": load_active_panel(),
        "active_config_view": load_active_config_view(),
        "active_menu_path": load_active_menu_path(),
        "menu_order": load_menu_order(),
        "menu_labels": load_menu_labels(),
        "menu_hidden_keys": load_menu_hidden_keys(),
        "menu_tree_open": load_menu_tree_open(),
        "google_calendar_sync": load_google_calendar_sync_settings(),
    }


@app.post("/api/ui-state")
def api_set_ui_state(body: UiStateRequest) -> dict[str, Any]:
    try:
        if body.column_widths is not None:
            save_column_widths(body.column_widths)
        if (
            body.target_editor_width is not None
            or body.target_column_widths is not None
            or body.catalog_column_widths is not None
        ):
            save_target_editor_layout(
                body.target_editor_width,
                body.target_column_widths or {},
                body.catalog_column_widths,
            )
        if body.form_column_widths is not None:
            save_form_column_widths(body.form_column_widths)
        if body.menu_order is not None:
            save_menu_order(body.menu_order)
        if body.menu_labels is not None:
            save_menu_labels(body.menu_labels)
        if body.menu_hidden_keys is not None:
            save_menu_hidden_keys(body.menu_hidden_keys)
        if body.menu_tree_open is not None:
            save_menu_tree_open(body.menu_tree_open)
        if body.google_calendar_sync is not None:
            save_google_calendar_sync_settings(body.google_calendar_sync)
        if body.sidebar_width is not None:
            save_sidebar_width(body.sidebar_width)
        if body.show_past is not None:
            save_show_past(body.show_past)
        if body.active_panel is not None:
            save_active_panel(body.active_panel)
        if body.active_config_view is not None:
            save_active_config_view(body.active_config_view)
        if body.active_menu_path is not None:
            save_active_menu_path(body.active_menu_path)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"UI state save failed: {e}") from e


@app.post("/api/google-calendar/auth")
def api_google_calendar_auth() -> dict[str, Any]:
    try:
        return {"ok": True, **authorize_google_calendar(get_settings())}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Calendar login failed: {e}") from e


@app.get("/api/google-calendar/auth-status")
def api_google_calendar_auth_status() -> dict[str, Any]:
    try:
        return {"ok": True, **google_calendar_auth_status(get_settings())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Calendar auth status failed: {e}") from e


@app.post("/api/google-calendar/nonwork-consistency")
def api_google_calendar_nonwork_consistency(body: RosterCalendarConsistencyRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **check_nonwork_calendar_consistency(body.roster_text, get_settings())}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Calendar non-work consistency check failed: {e}") from e


@app.get("/api/duty-report/plan")
def api_duty_report_plan(date_iso: str | None = None) -> dict[str, Any]:
    from meal_planner.duty_report import build_plan
    from meal_planner.whatsapp_send import cdp_health

    biz_date: date | None = None
    if date_iso:
        try:
            biz_date = date.fromisoformat(date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {date_iso}") from e
    try:
        plan = build_plan(get_settings(), biz_date=biz_date)
        plan["health"] = cdp_health()
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duty report plan failed: {e}") from e


@app.post("/api/duty-report/override")
def api_duty_report_override(body: DutyReportOverrideRequest) -> dict[str, Any]:
    from meal_planner.duty_report import apply_override
    from meal_planner.whatsapp_send import cdp_health

    biz_date: date | None = None
    if body.date_iso:
        try:
            biz_date = date.fromisoformat(body.date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {body.date_iso}") from e
    try:
        plan = apply_override(
            get_settings(),
            mode=body.mode,
            segments=body.segments,
            slot_patch=body.slot,
            source=body.source,
            biz_date=biz_date,
        )
        plan["health"] = cdp_health()
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duty report override failed: {e}") from e


@app.post("/api/duty-report/send")
def api_duty_report_send(body: DutyReportSendRequest) -> dict[str, Any]:
    from meal_planner.duty_report import send_slot
    from meal_planner.whatsapp_send import WhatsAppSendError, cdp_health

    try:
        plan = send_slot(get_settings(), body.slot_id, manual=True, source=body.source, date_iso=body.date_iso)
        plan["health"] = cdp_health()
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WhatsAppSendError as e:
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duty report send failed: {e}") from e


@app.post("/api/duty-report/config")
def api_duty_report_config(body: DutyReportConfigRequest) -> dict[str, Any]:
    from meal_planner.duty_report import build_plan, record_event, save_config
    from meal_planner.whatsapp_send import cdp_health

    try:
        settings = get_settings()
        patch: dict[str, Any] = {}
        if body.mapping is not None:
            patch["mapping"] = body.mapping
        if body.message_template is not None:
            patch["message_template"] = body.message_template
        if body.auto_send is not None:
            patch["auto_send"] = body.auto_send
        save_config(settings, patch)
        if body.auto_send is not None:
            record_event(settings, "auto_send", "on" if body.auto_send else "off", source="web")
        if body.mapping is not None:
            record_event(settings, "mapping", "code→group mapping updated", source="web")
        plan = build_plan(settings)
        plan["health"] = cdp_health()
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duty report config failed: {e}") from e


@app.get("/api/onoffduty/plan")
def api_onoffduty_plan(date_iso: str | None = None) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan

    biz_date: date | None = None
    if date_iso:
        try:
            biz_date = date.fromisoformat(date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {date_iso}") from e
    try:
        return build_day_plan(get_settings(), biz_date=biz_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty plan failed: {e}") from e


@app.post("/api/onoffduty/log")
def api_onoffduty_log(body: OnOffDutyLogRequest) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan, record_onoff_log
    from meal_planner.duty_report import business_date

    if body.kind not in {"start", "end"}:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {body.kind}")
    if body.status not in {"opened", "sent", "failed"}:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            from zoneinfo import ZoneInfo

            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        plan = build_day_plan(settings, biz_date=biz_date)
        action = next((a for a in plan.get("actions", []) if a.get("kind") == body.kind), None)
        record_onoff_log(
            settings,
            biz_date,
            body.kind,
            body.status,
            time_text=str(action.get("time") if action else ""),
            source=body.source,
        )
        return build_day_plan(settings, biz_date=biz_date)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty log failed: {e}") from e


@app.post("/api/onoffduty/override")
def api_onoffduty_override(body: OnOffDutyOverrideRequest) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan, set_time_override
    from meal_planner.duty_report import business_date

    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            from zoneinfo import ZoneInfo

            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        set_time_override(settings, biz_date, start=body.start, end=body.end, note=body.note)
        return build_day_plan(settings, biz_date=biz_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty override failed: {e}") from e


@app.post("/api/onoffduty/roster-code")
def api_onoffduty_roster_code(body: OnOffDutyRosterCodeRequest) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan, set_roster_code
    from meal_planner.duty_report import business_date

    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            from zoneinfo import ZoneInfo

            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        set_roster_code(settings, biz_date, body.code)
        return build_day_plan(settings, biz_date=biz_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty roster-code failed: {e}") from e


@app.post("/api/onoffduty/lateoff")
def api_onoffduty_lateoff(body: OnOffDutyLateOffRequest) -> dict[str, Any]:
    from meal_planner.duty_form import late_off_hold, late_off_send_now

    try:
        settings = get_settings()
        if body.action == "hold":
            return late_off_hold(settings, True)
        if body.action == "release":
            return late_off_hold(settings, False)
        if body.action == "send_now":
            return late_off_send_now(settings, note=body.note)
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty lateoff failed: {e}") from e


@app.post("/api/onoffduty/config")
def api_onoffduty_config(body: OnOffDutyConfigRequest) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan, save_onoff_config

    try:
        settings = get_settings()
        save_onoff_config(settings, {"auto_send": body.auto_send})
        return build_day_plan(settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty config failed: {e}") from e


def main() -> None:
    import uvicorn

    from meal_planner.duty_report_scheduler import start_scheduler

    # 0.0.0.0：同時聽 LAN（192.168.x）同 Tailscale（100.x），電話出街先連到。
    host = os.environ.get("MENU_API_HOST", "0.0.0.0")
    port = int(os.environ.get("MENU_API_PORT", "8765"))
    free_tcp_port(port)
    start_scheduler()
    uvicorn.run("meal_planner.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
