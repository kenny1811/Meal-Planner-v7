"""Local FastAPI: web UI + date expression -> meal plan JSON."""

from __future__ import annotations

import os
import hashlib
import math
import subprocess
import json
import copy
import time
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from meal_planner.dates_input import DateValidationError, parse_date_expression
from meal_planner.dashboard_notify import notify_dashboard_meals
from meal_planner.free_port import free_tcp_port
from meal_planner.google_calendar_sync import authorize_google_calendar, google_calendar_auth_status, sync_roster_to_google_calendar
from meal_planner.indicators import NUTRIENT_KEYS
from meal_planner.meal_schedule import MEAL_LABELS, restaurant_lunch_label, visible_meals_from_resolved
from meal_planner.maintenance_db import (
    MAINTENANCE_SHEETS,
    MaintenanceDatabaseError,
    list_maintenance_sheets,
    load_roster_code_definitions,
    load_roster_post_mapping,
    load_sheet_rows,
    roster_code_defs,
    roster_post_for_code,
    save_roster_code_definitions,
    save_roster_post_mapping,
    save_sheet_rows,
)
from meal_planner.nutrition_db import (
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
from meal_planner.schedule_grid_sync import (
    ScheduleGridDataError,
    ScheduleGridNotFound,
    build_schedule_grid_all_variants_export,
    check_roster_codes_against_schedule_grid,
    collect_schedule_grid_import_codes,
    merge_schedule_grid_rows_for_import,
    parse_schedule_grid_push_payload,
)
from meal_planner.phone_push import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    phone_endpoint,
    capture_watch,
    push_schedule_grid,
    remember_phone_host,
)
from meal_planner.roster import code_for_date, load_roster_map
from meal_planner.roster_codes import CATCH_ALL_PATTERN, is_work_day, match_roster_code
from meal_planner.schedule_grid import (
    ScheduleRow,
    load_schedule_rows_from_rows,
    rows_for_roster,
    weekday_allows,
)
from meal_planner.shift_time import payroll_coverage_issues
from meal_planner.timeparse import business_date, hhmm30, minutes_30h
from meal_planner.storage import (
    _STORE_LOCK,
    batch_ui_updates,
    load_ui_snapshot,
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
    load_latest_plan_revision,
    load_memory_payload,
    load_plan_date_neighbours,
    load_sidebar_width,
    load_show_past,
    load_target_editor_layout,
    load_typhoon_state,
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
    save_typhoon_state,
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
        "web_version": _web_version_name(),
        "primary_data_source": "sqlite",
        "project_root": str(settings.project_root),
        "system_folder": str(settings.system_folder),
        "data_folder": str(settings.data_folder),
        "database": str(settings.database_path),
        "database_exists": settings.database_path.is_file(),
    }


@app.middleware("http")
async def record_debug_stats(request: Request, call_next):
    # 電話會喺 header 報上名——記低佢個 IP，之後打風 Apply 就 push 得返落電話。
    if request.headers.get(CLIENT_HEADER) == CLIENT_HEADER_VALUE:
        remember_phone_host(
            request.client.host if request.client else "",
            request.headers.get("x-alarm-token"),
        )
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


@app.exception_handler(ScheduleGridDataError)
async def schedule_grid_data_error_handler(request: Request, exc: ScheduleGridDataError) -> JSONResponse:
    return await http_error_handler(request, HTTPException(status_code=400, detail=str(exc)))


@app.exception_handler(ScheduleGridNotFound)
async def schedule_grid_not_found_handler(request: Request, exc: ScheduleGridNotFound) -> JSONResponse:
    return await http_error_handler(request, HTTPException(status_code=404, detail=str(exc)))


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


class MealItemSwap(BaseModel):
    """指定食材：邊一餐、邊一格、換做營養清單邊一行。"""

    meal: str
    item_index: int
    row_index: int


class OutOfStockResolveRequest(BaseModel):
    date: str
    row_index: int | None = None  # None＝唔標記冇貨，齋做 partial re-solve
    locked_meals: list[str] = Field(default_factory=list)
    nutrient_indicators: dict[str, Any] = Field(default_factory=dict)
    meal_plan: dict[str, Any] = Field(default_factory=dict)
    swaps: list[MealItemSwap] = Field(default_factory=list)  # 指定食材，空＝唔指定
    meal: str | None = None  # 右 click 咗邊餐（純為記 log；鎖邊幾餐仍然睇 locked_meals）


class UiStateRequest(BaseModel):
    column_widths: dict[str, float] | None = None
    sidebar_width: float | None = None
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
    typhoon_state: dict[str, Any] | None = None


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


class RiceConversionRow(BaseModel):
    name_contains: str
    ratio: float = Field(..., gt=0)


class DetailSettingsRequest(BaseModel):
    # 全部 optional：冇帶嘅欄唔碰（以前 default [] 會將更碼定義／Post mapping／米換算清空）。
    rice_conversions: list[RiceConversionRow] | None = None
    system_folder: str | None = None
    data_folder: str | None = None
    google_calendar_sync: dict[str, Any] | None = None
    roster_code_definitions: list[dict[str, Any]] | None = None
    roster_post_mapping: list[dict[str, Any]] | None = None


class MaintenanceSheetRequest(BaseModel):
    rows: list[list[Any]] = Field(default_factory=list)


class DutyReportOverrideRequest(BaseModel):
    mode: str | None = None
    segments: list[dict[str, str]] | None = None
    slot: dict[str, Any] | None = None
    extra_slots: list[dict[str, Any]] | None = None
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


class OnOffDutyOverrideRequest(BaseModel):
    date_iso: str | None = None
    start: str | None = None
    end: str | None = None
    note: str | None = None


class OnOffDutyHoldSendRequest(BaseModel):
    action: str  # hold | release | send_now
    kind: str = "end"  # start | end（舊版電話 app 冇呢個欄，當收工）
    note: str = ""


class OnOffDutyRosterCodeRequest(BaseModel):
    date_iso: str | None = None
    code: str


class TyphoonApplyRequest(BaseModel):
    date_iso: str | None = None
    signal_time: str = ""
    code: str | None = None
    day_off: bool = False
    name: str = ""


def _stored_meal_plan_payloads(
    date_isos: set[str], payload: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not date_isos:
        return found

    payload = payload if payload is not None else load_memory_payload()
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
    """餐時文字（可以夾住其他字）→ 30 小時制分鐘；冇時間或時間無效回 None。

    餐時可以係 24:xx–29:xx（resolve_meal_times_display 出嘅就係咁），00:00–05:59
    亦當翌日凌晨計——換算交畀 timeparse.minutes_30h，唔喺呢度自己 +24。
    """
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", str(raw or ""))
    if not match:
        return None
    try:
        return minutes_30h(match.group(0))
    except ValueError:
        return None


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
    return minutes_30h(now) < first_meal  # 30 小時制


def _preview_regeneration_blocked_dates(dates: list[date]) -> list[date]:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.dates.timezone))
    today = business_date(now)  # 30 小時制：00:00–05:59 仍係前一日
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




@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    return _health_payload()


@app.get("/api/debug/stats")
def api_debug_stats() -> dict[str, Any]:
    """Request 計數／最後一個 error（前端唔會叫；手動 curl 用嚟睇 server 有冇事）。"""
    return {
        "ok": True,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "stats": _DEBUG_STATS,
        "health": _health_payload(),
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



def _apk_path(module: str) -> Path:
    name = "app" if module == "app" else "wear"
    return (_WEB_DIR.parent.parent / "android_alarm_app" / name / "build"
            / "outputs" / "apk" / "debug" / f"{name}-debug.apk")


_CHANGELOG_PATH = _WEB_DIR.parent.parent / "CHANGELOG.md"
_CHANGELOG_CACHE: tuple[float, str] | None = None


def _changelog_text() -> str:
    """committed 版 changelog（git show HEAD:CHANGELOG.md）：改動 commit 咗先算數，
    未 commit 嘅 WIP 唔會跳 version、唔會喺 dialog 出現。冇 git 先 fallback 讀 working copy。"""
    global _CHANGELOG_CACHE
    now = time.time()
    if _CHANGELOG_CACHE is not None and now - _CHANGELOG_CACHE[0] < 5.0:
        return _CHANGELOG_CACHE[1]
    text = ""
    try:
        shown = subprocess.run(
            ["git", "show", "HEAD:CHANGELOG.md"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=_WEB_DIR.parent.parent, timeout=5,
        )
        if shown.returncode == 0:
            text = shown.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    if not text:
        try:
            text = _CHANGELOG_PATH.read_text(encoding="utf-8")
        except OSError:
            text = ""
    _CHANGELOG_CACHE = (now, text)
    return text


def _web_version_name() -> str:
    """網頁版 versionName X.Y.Z：committed CHANGELOG.md 最頂 `## X.Y.Z` 標題。
    完成改動 commit 時先加 entry 跳 version（entry 同 code 同一 commit）：
    Z=修補/微調、Y=功能級、X=大改版。"""
    for line in _changelog_text().splitlines():
        found = re.match(r"##\s*v?(\d+\.\d+\.\d+)\b", line)
        if found:
            return found.group(1)
    return "7.0.0"


def _gradle_version(module: str) -> tuple[int, str]:
    # 由 build.gradle 讀 versionName（source of truth；免拆 APK）。
    # versionCode 同 gradle 一樣由 versionName 計：major*100 + minor（7.0 → 700）。
    gradle = _WEB_DIR.parent.parent / "android_alarm_app" / module / "build.gradle"
    try:
        text = gradle.read_text(encoding="utf-8")
    except OSError:
        return 0, ""
    match = re.search(r'versionName\s+"(\d+)\.(\d+)"', text)
    if match:
        major, minor = int(match.group(1)), int(match.group(2))
        return major * 100 + minor, f"{major}.{minor}"
    match = re.search(r"versionCode\s+(\d+)", text)
    return (int(match.group(1)) if match else 0), ""


@app.get("/api/app-version")
def app_version() -> dict:
    # 電話 in-app updater 用：報最新 build 嘅 version + APK 檔案資料。
    out: dict = {}
    for module in ("app", "wear"):
        path = _apk_path(module)
        code, name = _gradle_version(module)
        out[module] = {
            "version_code": code,
            "version_name": name,
            "apk_ready": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
            "mtime": int(path.stat().st_mtime) if path.is_file() else 0,
        }
    return out


@app.get("/api/changelog")
def api_changelog() -> Response:
    # sidebar 版本號 click 用：回 committed 版 markdown，前端自己 render。
    return Response(content=_changelog_text(), media_type="text/markdown; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/apk/watch")
def watch_apk() -> FileResponse:
    # 手錶 APK：電話 updater 下載後經 ChannelClient 推去手錶安裝。
    path = _apk_path("wear")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Cannot find wear-debug.apk (build first)")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename="oneshotalarm-wear.apk",
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
        "planner-typhoon.js",
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read planning data: {e}") from e


@app.get("/api/mobile-meal-plan")
def api_mobile_meal_plan(date_iso: str, meta_only: bool = False) -> dict[str, Any]:
    try:
        target_date = date.fromisoformat(str(date_iso).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="date_iso must be YYYY-MM-DD.") from e

    try:
        # 手機要邊日就淨係 refresh 嗰一日——唔好對成個儲存期做全量重計。
        target_iso = target_date.isoformat()
        base = load_memory_payload()
        stored = _stored_meal_plan_payloads({target_iso}, base)
        day_payload = stored.get(target_iso)
        if day_payload is None:
            return {
                "ok": False,
                "date": target_iso,
                "content_version": "",
                "message": "Meal plan has not been generated for this date.",
            }
        payload = refresh_payload_with_latest_indicators(
            {
                "headers": base.get("headers", []),
                "indicator_rows": base.get("indicator_rows", {}),
                "nutrient_keys": base.get("nutrient_keys", list(NUTRIENT_KEYS)),
                "days": [day_payload],
            }
        )
        days = payload.get("days", []) if isinstance(payload.get("days"), list) else []
        day_payload = days[0] if days else None
        if day_payload is None:
            return {
                "ok": False,
                "date": target_iso,
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
                "conversions": [
                    {"name_contains": c.name_contains, "ratio": c.ratio} for c in settings.rice.conversions
                ],
                "water_multiplier": settings.rice.water_multiplier,
            },
            "nutrition_format": {
                "kcal_per_fat_g": settings.nutrition_format.kcal_per_fat_g,
            },
        }
    except IndicatorDataError as e:
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
    ingredients["午餐"] = [restaurant_lunch_label(rest)]
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {e}") from e


def _is_yesterday_last_meal(body: "OutOfStockResolveRequest", today_iso: str) -> bool:
    """前一日 + 撳緊嗰日最後一餐（通常係晚餐）＝仲未食，照准重算。"""
    try:
        yesterday = (date.fromisoformat(today_iso) - timedelta(days=1)).isoformat()
    except ValueError:
        return False
    if str(body.date or "") != yesterday or not body.meal:
        return False
    visible = visible_meals_from_resolved(body.meal_plan if isinstance(body.meal_plan, dict) else {})
    ordered = [m for m in MEAL_LABELS if m in visible]
    return bool(ordered) and str(body.meal) == ordered[-1]


@app.post("/api/oos-resolve")
def api_oos_resolve(body: OutOfStockResolveRequest, request: Request) -> dict[str, Any]:
    """標記食材冇貨（營養清單暫停）並對未食嘅餐次做 partial-day re-solve。"""
    from meal_planner.nutrition_db import set_catalog_paused
    from meal_planner.preview import resolve_day_out_of_stock
    from meal_planner.storage import log_resolve_event

    settings = get_settings()
    today_iso = business_date(datetime.now(ZoneInfo(settings.dates.timezone))).isoformat()
    client = request.client.host if request.client else None
    action = "swap" if body.swaps else ("out_of_stock" if body.row_index is not None else "regenerate")

    # 過去嘅日子唔准再郁——嗰啲餐已經食咗，重算只會洗走食過乜嘅記錄。
    # 例外：前一日嘅最後一餐照准。用戶過咗 24:00 先食晚餐，喺佢嚟講嗰餐仲未食，
    # 但系統日曆已經跳咗做第二日。
    if str(body.date or "") < today_iso and not _is_yesterday_last_meal(body, today_iso):
        log_resolve_event(
            plan_date=body.date, meal=body.meal, action=action,
            row_index=body.row_index, row_name=None,
            locked_meals=body.locked_meals,
            swaps=[s.model_dump() for s in body.swaps],
            client=client, outcome="blocked_past_date",
        )
        raise HTTPException(
            status_code=400,
            detail=f"{body.date} 已經過去，唔可以再重算（過去嘅餐單係食過乜嘅記錄）。",
        )

    try:
        paused_name = set_catalog_paused(body.row_index, True) if body.row_index is not None else None
        forced = {(s.meal, int(s.item_index)): int(s.row_index) for s in body.swaps}
        day = resolve_day_out_of_stock(
            {
                "date": body.date,
                "nutrient_indicators": body.nutrient_indicators,
                "meal_plan": body.meal_plan,
            },
            body.locked_meals,
            forced_item_rows=forced or None,
        )
        log_resolve_event(
            plan_date=body.date, meal=body.meal, action=action,
            row_index=body.row_index, row_name=paused_name,
            locked_meals=body.locked_meals,
            swaps=[s.model_dump() for s in body.swaps],
            client=client, outcome="ok",
        )
        return {"paused_name": paused_name, **day}
    except IndicatorDataError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Out-of-stock resolve failed: {e}") from e


@app.get("/api/item-candidates")
def api_item_candidates() -> dict[str, Any]:
    """每餐每格可以指定嘅食材（畀「Swap → 指定食材」個 picker 用）。"""
    from meal_planner.preview import meal_item_candidates

    try:
        return {"meals": meal_item_candidates()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Load item candidates failed: {e}") from e


@app.get("/api/memory-list")
def api_memory_list_get(background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        # 讀→改→寫要鎖住，否則兩個 tab 同時 GET/POST 會 lost update。
        with _STORE_LOCK:
            payload = load_memory_payload()
            if isinstance(payload.get("days"), list):
                # refresh 會 in-place 郁 meal_plan，所以要喺 refresh 前影低原樣先比較得準。
                before = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                payload = refresh_payload_with_latest_indicators(payload)
                after = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if after != before:
                    changed_dates = save_memory_payload(payload)
                    if changed_dates:
                        background_tasks.add_task(notify_dashboard_meals, changed_dates)
        return {"payload": payload}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load memory list failed: {e}") from e


@app.post("/api/memory-list")
def api_memory_list_set(body: MemoryPayloadRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        with _STORE_LOCK:
            payload = merge_memory_payload(load_memory_payload(), body.payload)
            changed_dates = save_memory_payload(payload)
        if changed_dates:
            background_tasks.add_task(notify_dashboard_meals, changed_dates)
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
                "conversions": [
                    {"name_contains": c.name_contains, "ratio": c.ratio} for c in settings.rice.conversions
                ],
                "note_name_contains": list(settings.rice.note_name_contains),
            },
        }
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
            "conversions": [
                {"name_contains": c.name_contains, "ratio": c.ratio} for c in settings.rice.conversions
            ],
        },
        "google_calendar_sync": load_google_calendar_sync_settings(),
        "roster_code_definitions": load_roster_code_definitions(settings),
        "roster_post_mapping": load_roster_post_mapping(settings),
    }


@app.get("/api/detail-settings")
def api_get_detail_settings() -> dict[str, Any]:
    try:
        return _detail_settings_payload()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load detail settings failed: {e}") from e


@app.post("/api/detail-settings")
def api_set_detail_settings(body: DetailSettingsRequest) -> dict[str, Any]:
    try:
        if body.rice_conversions is not None:
            save_rice_detail_settings(
                conversions=[(row.name_contains, row.ratio) for row in body.rice_conversions],
            )
        if body.system_folder is not None or body.data_folder is not None:
            current = get_settings()
            save_folder_settings(
                system_folder=body.system_folder if body.system_folder is not None else str(current.system_folder),
                data_folder=body.data_folder if body.data_folder is not None else str(current.data_folder),
            )
        if body.google_calendar_sync is not None:
            save_google_calendar_sync_settings(body.google_calendar_sync)
        if body.roster_code_definitions is not None:
            save_roster_code_definitions(body.roster_code_definitions, get_settings())
        if body.roster_post_mapping is not None:
            save_roster_post_mapping(body.roster_post_mapping, get_settings())
        return {"ok": True, **_detail_settings_payload()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save detail settings failed: {e}") from e


@app.get("/api/maint/sheets")
def api_maint_sheets() -> dict[str, Any]:
    try:
        return {"sheets": list_maintenance_sheets(get_settings())}
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load maintenance sheets failed: {e}") from e


@app.get("/api/maint/sheets/{sheet_key}")
def api_maint_sheet(sheet_key: str) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key(sheet_key)
    try:
        return load_sheet_rows(sheet_key, get_settings())
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
        if sheet_key == "payroll_times":
            # Coverage 檢查：邊個更碼有星期字 resolve 唔到（唔阻止儲存，淨係 warning）。
            try:
                issues = payroll_coverage_issues(body.rows)
                response["payroll_check"] = {
                    "status": "warning" if issues else "ok",
                    "issues": issues,
                }
            except Exception as e:
                response["payroll_check"] = {"status": "error", "detail": str(e), "issues": []}
        if sheet_key == "roster":
            # 更碼檢查唔喺度做：前端離開每行更表時已經逐行問過（/api/maint/roster/check-line）。
            try:
                response["google_calendar_sync"] = sync_roster_to_google_calendar(body.rows, settings)
            except Exception as e:
                response["google_calendar_sync"] = {"status": "error", "detail": str(e)}
        return response
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown maintenance sheet: {sheet_key}") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save maintenance sheet failed: {e}") from e


class RosterLineCheckRequest(BaseModel):
    text: str = ""
    rows: list[Any] | None = None


@app.post("/api/maint/roster/check-line")
def api_check_roster_line(body: RosterLineCheckRequest) -> dict[str, Any]:
    # 離開一行時淨係傳嗰行（text）；儲存前會傳成張表（rows）。
    try:
        rows = body.rows if body.rows is not None else [[body.text]]
        return check_roster_codes_against_schedule_grid(rows)
    except Exception as e:
        return {"status": "error", "detail": str(e), "issues": []}


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


def _normalize_schedule_grid_push(payload: Any) -> tuple[list[list[Any]], set[str]]:
    """電話推上嚟嘅 JSON payload → 正規化 rows + 生效日期。"""
    try:
        return parse_schedule_grid_push_payload(payload)
    except ScheduleGridDataError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _import_normalized_schedule_grid_rows(
    rows: list[list[Any]],
    imported_dates: set[str],
) -> dict[str, Any]:
    sheet_key = _validate_maintenance_key("schedule_grid")
    settings = get_settings()
    try:
        sheet = load_sheet_rows(sheet_key, settings)
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load existing schedule_grid failed: {e}") from e

    existing_rows = sheet.get("rows", [])
    imported_codes = collect_schedule_grid_import_codes(rows)
    # rows 由 parse_schedule_grid_push_payload 砌，每行生效日期同 imported_dates 一樣，
    # 所以唔使再由 rows 度抽多次。
    effective_versions = imported_dates
    if not effective_versions:
        has_existing_rows = isinstance(existing_rows, list) and len(existing_rows) > 1
        if has_existing_rows:
            raise HTTPException(
                status_code=400,
                detail="Pushed schedule_grid has no effective date version. "
                       "請重新從電腦匯出再更新 seed。",
            )
    imported_row_count = max(0, len(rows) - 1)
    merged_rows, replaced_row_count = merge_schedule_grid_rows_for_import(
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


@app.get("/api/maint/sheets/schedule_grid/export-all")
def api_export_all_schedule_grid() -> dict[str, Any]:
    return build_schedule_grid_all_variants_export()


@app.post("/api/maint/sheets/schedule_grid/import-phone-push")
async def api_import_schedule_grid_from_phone_push(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e
    rows, imported_dates = _normalize_schedule_grid_push(payload)
    import_result = _import_normalized_schedule_grid_rows(rows, imported_dates)
    return {
        **import_result,
        "ok": True,
        "source": "phone_push",
    }


@app.get("/api/targets")
def api_get_targets() -> dict[str, Any]:
    settings = get_settings()
    try:
        headers, workday, nonworkday = load_target_rows(settings)
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
        entries = load_catalog_entries(settings)
        return {
            "nutrient_keys": list(NUTRIENT_KEYS),
            "rows": [_catalog_entry_payload(entry) for entry in entries],
        }
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
    ui = load_ui_snapshot()  # 讀一次，13 個 loader 共用，唔使開 13 次 db
    target_column_widths, catalog_column_widths = load_target_editor_layout(ui)
    return {
        "column_widths": load_column_widths(ui),
        "sidebar_width": load_sidebar_width(ui),
        "target_column_widths": target_column_widths,
        "catalog_column_widths": catalog_column_widths,
        "form_column_widths": load_form_column_widths(ui),
        "show_past": load_show_past(ui),
        "active_panel": load_active_panel(ui),
        "active_config_view": load_active_config_view(ui),
        "active_menu_path": load_active_menu_path(ui),
        "menu_order": load_menu_order(ui),
        "menu_labels": load_menu_labels(ui),
        "menu_hidden_keys": load_menu_hidden_keys(ui),
        "menu_tree_open": load_menu_tree_open(ui),
        "google_calendar_sync": load_google_calendar_sync_settings(ui),
        "typhoon_state": load_typhoon_state(ui),
    }


@app.post("/api/ui-state")
def api_set_ui_state(body: UiStateRequest) -> dict[str, Any]:
    try:
        with batch_ui_updates():
            _apply_ui_state_patch(body)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"UI state save failed: {e}") from e


def _apply_ui_state_patch(body: UiStateRequest) -> None:
    if body.column_widths is not None:
        save_column_widths(body.column_widths)
    if body.target_column_widths is not None or body.catalog_column_widths is not None:
        save_target_editor_layout(body.target_column_widths or {}, body.catalog_column_widths)
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
    if body.typhoon_state is not None:
        save_typhoon_state(body.typhoon_state)
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
            extra_slots=body.extra_slots,
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
    from meal_planner.duty_form import build_day_plan, record_onoff_log, record_onoff_open

    if body.kind not in {"start", "end"}:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {body.kind}")
    if body.status not in {"opened", "sent", "failed"}:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        plan = build_day_plan(settings, biz_date=biz_date)
        action = next((a for a in plan.get("actions", []) if a.get("kind") == body.kind), None)
        time_text = str(action.get("time") if action else "")
        if body.status == "opened":
            # 開過預填連結：淨係留 history 記錄，唔改狀態、唔阻夠鐘自動交。
            record_onoff_open(settings, biz_date, body.kind, time_text=time_text, source=body.source)
        else:
            record_onoff_log(
                settings,
                biz_date,
                body.kind,
                body.status,
                time_text=time_text,
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

    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        set_time_override(settings, biz_date, start=body.start, end=body.end, note=body.note)
        phone_sync = None
        if body.start is not None or body.end is not None:
            from meal_planner.phone_push import push_schedule_grid

            # 儲存及排程更新已完成；網絡等候喺時間／發送鎖之外，唔阻報更。
            phone_sync = push_schedule_grid()
        # 等候電話期間可能已 sent；回傳最新狀態，唔重新打開舊嘅時間編輯入口。
        plan = build_day_plan(settings, biz_date=biz_date)
        if phone_sync is not None:
            plan["phone_sync"] = phone_sync
            if (plan["phone_sync"].get("status") == "ok"
                    and plan["phone_sync"].get("plan_date") != plan["date_iso"]):
                plan["phone_sync"]["status"] = "different_date"
                plan["phone_sync"]["detail"] = (
                    f"電話目前匯入 {plan['phone_sync'].get('plan_date') or '另一日'} 行位表；"
                    f"{plan['date_iso']} 嘅時間已儲存，會喺該日成為匯入目標時套用。"
                )
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty override failed: {e}") from e


@app.post("/api/onoffduty/roster-code")
def api_onoffduty_roster_code(body: OnOffDutyRosterCodeRequest) -> dict[str, Any]:
    from meal_planner.duty_form import build_day_plan, set_roster_code

    try:
        settings = get_settings()
        if body.date_iso:
            biz_date = date.fromisoformat(body.date_iso)
        else:
            biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
        set_roster_code(settings, biz_date, body.code)
        return build_day_plan(settings, biz_date=biz_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty roster-code failed: {e}") from e


@app.post("/api/onoffduty/lateoff")
def api_onoffduty_holdsend(body: OnOffDutyHoldSendRequest) -> dict[str, Any]:
    """開工／收工嘅 hold・resume・send now（路徑保留舊名，舊版電話 app 仲用緊）。"""
    from meal_planner.duty_form import duty_hold, duty_send_now

    if body.kind not in {"start", "end"}:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {body.kind}")
    try:
        settings = get_settings()
        if body.action == "hold":
            return duty_hold(settings, body.kind, True)
        if body.action == "release":
            return duty_hold(settings, body.kind, False)
        if body.action == "send_now":
            return duty_send_now(settings, body.kind, note=body.note)
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OnOffDuty hold/send failed: {e}") from e


@app.get("/api/typhoon/plan")
def api_typhoon_plan(
    date_iso: str | None = None,
    signal_time: str = "",
    code: str | None = None,
    confirmed: bool = False,
    day_off: bool = False,
    name: str = "",
) -> dict[str, Any]:
    from meal_planner.typhoon import build_typhoon_plan

    biz_date: date | None = None
    if date_iso:
        try:
            biz_date = date.fromisoformat(date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {date_iso}") from e
    try:
        return build_typhoon_plan(
            get_settings(),
            biz_date=biz_date,
            signal_time=signal_time,
            roster_code=code,
            confirmed=confirmed,
            day_off_announced=day_off,
            name=name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Typhoon plan failed: {e}") from e


@app.get("/api/typhoon/current-name")
def api_typhoon_current_name(force: bool = False) -> dict[str, Any]:
    from meal_planner.typhoon import current_typhoon_names

    data = current_typhoon_names(force=force)
    first = data["names"][0] if data["names"] else {}
    return {
        "name": first.get("zh") or first.get("en", ""),
        "english": first.get("en", ""),
        "names": data["names"],
        "note": data["note"],
        "source": data["source"],
        "status": data["status"],
        "checked_at": data["checked_at"],
    }


class TyphoonMealPlanRequest(BaseModel):
    date_iso: str | None = None
    signal_time: str = ""
    code: str | None = None
    day_off: bool = False
    reroll_nonce: int = 0


@app.post("/api/typhoon/meal-plan")
def api_typhoon_meal_plan(body: TyphoonMealPlanRequest) -> dict[str, Any]:
    """當日餐單按打風時間重新計一次（要行 LP，所以係 POST，唔會自動跑）。"""
    from meal_planner.typhoon import build_typhoon_meal_plan

    biz_date: date | None = None
    if body.date_iso:
        try:
            biz_date = date.fromisoformat(body.date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {body.date_iso}") from e
    if biz_date is None:
        biz_date = business_date(datetime.now(ZoneInfo(get_settings().dates.timezone)))
    try:
        return build_typhoon_meal_plan(
            get_settings(), biz_date=biz_date, signal_time=body.signal_time,
            roster_code=body.code, day_off_announced=body.day_off,
            reroll_nonce=body.reroll_nonce,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Typhoon meal plan failed: {e}") from e


@app.get("/api/phone/endpoint")
def api_phone_endpoint() -> dict[str, Any]:
    """電腦最後一次見到電話嘅位置（電話每次打上嚟會報上名）。前端唔叫；手動 curl 排錯用。"""
    return phone_endpoint()


@app.post("/api/phone/push-schedule-grid")
def api_phone_push_schedule_grid() -> dict[str, Any]:
    """叫電話即刻重新匯入行位表（電話跟住會排鬧鐘 + 通知手錶）。

    前端唔叫（打風 Apply 係 typhoon.apply_typhoon 直接 call push_schedule_grid）；手動 curl 用。
    """
    return push_schedule_grid()


@app.get("/api/phone/capture-watch")
def api_phone_capture_watch() -> Response:
    """經電話攞手錶截圖（電腦帶 token 去打電話 8765，唔使自己知 token）。前端唔叫；手動 curl 用。"""
    status, body, content_type = capture_watch()
    return Response(content=body, status_code=status, media_type=content_type)


@app.post("/api/typhoon/apply")
def api_typhoon_apply(body: TyphoonApplyRequest) -> dict[str, Any]:
    from meal_planner.typhoon import apply_typhoon

    biz_date: date | None = None
    if body.date_iso:
        try:
            biz_date = date.fromisoformat(body.date_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date_iso: {body.date_iso}") from e
    try:
        return apply_typhoon(
            get_settings(),
            biz_date=biz_date,
            signal_time=body.signal_time,
            roster_code=body.code,
            day_off_announced=body.day_off,
            name=body.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Typhoon apply failed: {e}") from e


# ---------------------------------------------------------------------------
# Dashboard 專用（D:\Projects\Dashboard，門前 kiosk 嘅 Express server）
# ---------------------------------------------------------------------------
# 門前 Dashboard 以前自己用 node:sqlite 讀呢邊個 DB、用 JS 抄咗一次行位表／餐單嘅規則；
# 2026-09 決定「規則只留餐單一份」——Dashboard 改為打下面兩條唯讀 endpoint。
# 輸出 JSON 嘅 shape（欄名、型別、null 規則、排序）係同 Dashboard `server/schedule-grid.js`、
# `server/meal.js` 同佢個 web/ 嘅合約，**唔可以隨便改**；要改就要兩邊一齊改、一齊驗。
# 規則全部用返現成嘅 schedule_grid / roster / roster_codes / storage，呢度只係砌 shape。

_DASHBOARD_MAX_RANGE_DAYS = 62
_DASHBOARD_ROSTER_EN = {
    "年假": "Annual leave",
    "Stand by": "Non-working day",  # SB 照門前直樹要求顯示 Non-working day
    "勞工假": "Statutory holiday",
    "病假": "Sick leave",
    "颱風假": "Typhoon day",
    "週假": "Weekly off",
    "返工日": "Work day",
}
# 10 項營養固定次序（同 CLAUDE.md 用戶慣例一致）：key、中文名、單位
_DASHBOARD_NUTRITION = (
    ("kcal", "卡路里", "kCal"),
    ("protein_g", "蛋白質", "g"),
    ("carb_g", "碳水", "g"),
    ("sugar_g", "天然糖", "g"),
    ("cholesterol_mg", "膽固醇", "mg"),
    ("sodium_mg", "鈉", "mg"),
    ("calcium_mg", "鈣", "mg"),
    ("fat_total_g", "總脂肪", "g"),
    ("fat_sat_g", "飽和脂肪", "g"),
    ("fat_trans_g", "反式脂肪", "g"),
)
_DASHBOARD_INGREDIENT_RE = re.compile(r"^(.*?)\s*[（(]([^()（）]*)[)）]\s*$")
_DASHBOARD_POST_PREFIX_RE = re.compile(r"^\s*(\S+)\s*[-–—:]\s*(.+)$")


def _dashboard_iso_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{name} must be YYYY-MM-DD") from e


def _dashboard_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dashboard_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dashboard_at(items: list[Any], idx: int) -> Any:
    return items[idx] if idx < len(items) else None


def _dashboard_strip_post_code(place: str | None, code: str) -> str | None:
    """更表嘅 post 原文係「ELEB - Chanel 圓方」；Dashboard 已經有綠牌顯示更碼，
    剝走開頭重覆嘅更碼（唔分大小寫）。"""
    if not place:
        return None
    m = _DASHBOARD_POST_PREFIX_RE.match(place)
    if m and m.group(1).lower() == code.lower():
        return m.group(2).strip()
    return place


def _dashboard_duty(
    grid_rows: list[ScheduleRow], posts: dict[str, str], code: str, day: date
) -> dict[str, Any]:
    """一個更碼喺某日嘅行位表：當日生效版本、剔走停用行、(日-四)/(五六) 過濾、30 小時制時間。"""
    known = rows_for_roster(grid_rows, code)
    version = rows_for_roster(grid_rows, code, day)
    rows = [
        {
            "time": hhmm30(row.t) if row.t is not None else "",
            "content": row.content.strip(),
            "duration": row.duration_min,
            "marker": row.is_marker,
        }
        for row in version
        if weekday_allows(row.content, day)
    ]
    effective = version[0].effective_from if version else None
    return {
        "code": code,
        "place": _dashboard_strip_post_code(posts.get(code), code),
        "effectiveFrom": effective.isoformat() if effective else None,
        "rows": rows,
        "known": bool(known),
    }


@app.get("/api/dashboard/schedule-grid")
def api_dashboard_schedule_grid(start: str, end: str, code: str | None = None) -> dict[str, Any]:
    """門前 Dashboard 用，shape 唔可以隨便改。

    每日一個 {date, codes, duties}：codes 係更表當日嘅更碼（冇更表／冇更碼就 []），
    duties 逐個更碼出 {code, place, effectiveFrom, rows:[{time, content, duration, marker}], known}。
    傳咗 code= 就唔睇更表，每日都當係呢個更碼（Dashboard 嘅更碼由更表 Google Calendar 嚟，
    佢就係咁用）。日期範圍包含 end，最多 62 日。
    """
    d0 = _dashboard_iso_date(start, "start")
    d1 = _dashboard_iso_date(end, "end")
    if d1 < d0:
        raise HTTPException(status_code=400, detail="end must not be before start")
    if (d1 - d0).days >= _DASHBOARD_MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"range must be at most {_DASHBOARD_MAX_RANGE_DAYS} days")
    settings = get_settings()
    try:
        sheet = load_sheet_rows("schedule_grid", settings)
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    grid_rows = load_schedule_rows_from_rows(sheet.get("rows") or [])
    posts = roster_post_for_code(settings)
    roster: dict[tuple[int, int], Any] = {}
    if code is None:
        try:
            roster = load_roster_map(settings)
        except MaintenanceDatabaseError:
            roster = {}
    days: list[dict[str, Any]] = []
    d = d0
    while d <= d1:
        if code is not None:
            codes = [code]
        else:
            rm = roster.get((d.year, d.month))
            found = code_for_date(rm, d) if rm else None
            codes = [found] if found else []
        days.append(
            {
                "date": d.isoformat(),
                "codes": codes,
                "duties": [_dashboard_duty(grid_rows, posts, c, d) for c in codes],
            }
        )
        d += timedelta(days=1)
    return {"start": d0.isoformat(), "end": d1.isoformat(), "days": days}


def _dashboard_roster_label(defs, code: str | None) -> str | None:
    if not code:
        return None
    hit = match_roster_code(defs, code)
    if hit is None:
        hit = next((x for x in defs if x.pattern == CATCH_ALL_PATTERN), None)
    if hit is None:
        return None
    return _DASHBOARD_ROSTER_EN.get(hit.label, hit.label)


def _dashboard_split_ingredient(raw: Any) -> dict[str, str]:
    """「燕麥(59g)」→ {name: 燕麥, amount: 59g}；冇括號就 amount 留空。"""
    text = str(raw).strip()
    m = _DASHBOARD_INGREDIENT_RE.match(text)
    if m:
        return {"name": m.group(1).strip(), "amount": m.group(2).strip()}
    return {"name": text, "amount": ""}


def _dashboard_round(value: Any) -> int | None:
    """JS Math.round（.5 向上），唔係 Python 嘅銀行家捨入。"""
    try:
        return int(math.floor(float(value) + 0.5))
    except (TypeError, ValueError):
        return None


@app.get("/api/dashboard/meal-revision")
def api_dashboard_meal_revision() -> dict[str, str | None]:
    """Latest saved plan version for Dashboard's missed-notification check."""
    return {"revision": load_latest_plan_revision()}


@app.get("/api/dashboard/meal")
def api_dashboard_meal(date: str) -> dict[str, Any]:
    """門前 Dashboard 用，shape 唔可以隨便改。

    該日 plan_versions 最新一版餐單，砌成 Dashboard Meals 頁要嘅樣：
    {date, prevDate, nextDate, generatedAt, rosterCode, rosterLabel, isWorkDay, meals, riceNote, note, nutrition}。
    冇餐單就 {date, missing: true, prevDate, nextDate}。prevDate／nextDate 係前後最近一日有餐單嘅日子，
    俾前端撥到盡就停。餐次只出有嘢食（有 items／餐廳午餐／有 skipped 原因）嗰啲；營養 10 項固定次序，
    紅旗完全跟餐單 summary 計好嘅旗。
    """
    day_iso = _dashboard_iso_date(date, "date").isoformat()
    prev_date, next_date = load_plan_date_neighbours(day_iso)
    latest = load_latest_versions([day_iso])
    if not latest["days"]:
        return {"date": day_iso, "missing": True, "prevDate": prev_date, "nextDate": next_date}
    day = latest["days"][0]
    generated_at = latest["versions"][day_iso][-1]
    mp = _dashboard_dict(day.get("meal_plan"))
    times = _dashboard_dict(mp.get("meal_times_resolved"))
    skipped_map = _dashboard_dict(times.get("_skipped"))
    ingredients = _dashboard_dict(mp.get("meal_ingredients"))
    nutrients = _dashboard_dict(mp.get("meal_nutrients"))
    restaurant = _dashboard_dict(mp.get("restaurant_lunch"))

    meals: list[dict[str, Any]] = []
    for name in MEAL_LABELS:
        items = [_dashboard_split_ingredient(x) for x in _dashboard_list(ingredients.get(name))]
        meal_time = times.get(name)
        # 餐廳午餐要午餐真係有排時間先算（EleM 呢類更冇午餐，但 day_json 仍然留住 restaurant_lunch 參考資料，summary 亦冇計佢）
        is_restaurant = (
            name == "午餐" and bool(restaurant.get("choice")) and not items and meal_time is not None
        )
        kcal_raw = _dashboard_dict(nutrients.get(name)).get("kcal")
        skipped = skipped_map.get(name)
        meal = {
            "name": name,
            "time": meal_time,
            "items": items,
            "restaurant": (
                {"choice": restaurant.get("choice"), "store": restaurant.get("store"), "hours": restaurant.get("hours")}
                if is_restaurant
                else None
            ),
            "kcal": _dashboard_round(kcal_raw) if kcal_raw is not None else None,
            "skipped": skipped,
        }
        if items or meal["restaurant"] or skipped:
            meals.append(meal)

    indicators = _dashboard_dict(day.get("nutrient_indicators"))
    summary = _dashboard_dict(mp.get("summary"))
    totals = _dashboard_list(summary.get("totals"))
    errors = _dashboard_list(summary.get("errors"))
    total_red = _dashboard_list(summary.get("total_red_flags"))
    error_red = _dashboard_list(summary.get("error_red_flags"))
    nutrition = []
    for i, (key, label, unit) in enumerate(_DASHBOARD_NUTRITION):
        ind = _dashboard_dict(indicators.get(key))
        raw = ind.get("raw")
        nutrition.append(
            {
                "key": key,
                "name": label,
                "unit": unit,
                "total": _dashboard_at(totals, i),
                "error": _dashboard_at(errors, i),
                "target": raw if raw is not None else "",
                "totalRed": bool(_dashboard_at(total_red, i)),
                "errorRed": bool(_dashboard_at(error_red, i)),
            }
        )

    roster_code = day.get("roster_code")
    defs = roster_code_defs(get_settings())
    is_wd = day.get("is_work_day")
    if is_wd is None and roster_code:
        # day_json 冇記低（舊格式）先照更碼定義計；正常 preview 出嘅 day_json 都有
        is_wd = is_work_day(defs, str(roster_code))
    return {
        "date": day_iso,
        "prevDate": prev_date,
        "nextDate": next_date,
        "generatedAt": generated_at,
        "rosterCode": roster_code,
        "rosterLabel": _dashboard_roster_label(defs, roster_code),
        "isWorkDay": bool(is_wd),
        "meals": meals,
        "riceNote": mp.get("rice_note"),
        "note": mp.get("note"),
        "nutrition": nutrition,
    }


def main() -> None:
    import uvicorn

    from meal_planner.duty_scheduler import start_scheduler

    # 0.0.0.0：同時聽 LAN（192.168.x）同 Tailscale（100.x），電話出街先連到。
    host = os.environ.get("MENU_API_HOST", "0.0.0.0")
    port = int(os.environ.get("MENU_API_PORT", "8765"))
    free_tcp_port(port)
    start_scheduler()
    uvicorn.run("meal_planner.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
