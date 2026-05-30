"""Local FastAPI: web UI + date expression -> meal plan JSON."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from meal_planner.dates_input import DateValidationError, cutoff_date, parse_date_expression
from meal_planner.diagnostics import run_integrity_checks
from meal_planner.excel_io import WorkbookValidationError, load_workbook_data
from meal_planner.free_port import free_tcp_port
from meal_planner.indicators import NUTRIENT_KEYS
from meal_planner.maintenance_db import (
    MAINTENANCE_SHEETS,
    MaintenanceDatabaseError,
    bootstrap_sheet_from_workbook,
    import_runtime_inputs_from_workbook,
    list_maintenance_sheets,
    list_runtime_input_status,
    load_roster_code_definitions,
    load_sheet_rows,
    save_roster_code_definitions,
    save_sheet_rows,
)
from meal_planner.nutrition_db import (
    NutritionDatabaseError,
    load_catalog_entries,
    load_target_rows,
    save_catalog_entries,
    save_target_rows,
)
from meal_planner.preview import (
    IndicatorDataError,
    preview_days_with_cutoff,
    recalc_days_from_edits,
    refresh_payload_with_latest_indicators,
)
from meal_planner.settings import get_settings, save_rice_detail_settings
from meal_planner.storage import (
    load_active_panel,
    load_column_widths,
    load_form_column_widths,
    load_latest_versions,
    load_menu_hidden_keys,
    load_menu_labels,
    load_menu_order,
    load_menu_tree_open,
    load_memory_payload,
    load_sidebar_width,
    load_show_past,
    load_target_editor_layout,
    save_active_panel,
    save_column_widths,
    save_form_column_widths,
    save_menu_hidden_keys,
    save_menu_labels,
    save_menu_order,
    save_menu_tree_open,
    save_memory_payload,
    save_plan_versions,
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
    skip_date_validation: bool = False
    reroll_nonce: int = 0
    fast_mode: bool = True


class RecalcDayRequest(BaseModel):
    date: str
    nutrient_indicators: dict[str, Any] = Field(default_factory=dict)
    meal_plan: dict[str, Any] = Field(default_factory=dict)
    edited_lines: dict[str, str] = Field(default_factory=dict)


class RecalcRequest(BaseModel):
    days: list[RecalcDayRequest] = Field(default_factory=list)


class SavePlansRequest(BaseModel):
    days: list[dict[str, Any]] = Field(default_factory=list)


class LoadPlansRequest(BaseModel):
    dates: list[str] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)


class UiStateRequest(BaseModel):
    column_widths: dict[str, float] | None = None
    sidebar_width: float | None = None
    target_editor_width: float | None = None
    target_column_widths: dict[str, float] | None = None
    catalog_column_widths: dict[str, float] | None = None
    form_column_widths: dict[str, float] | None = None
    show_past: bool | None = None
    active_panel: str | None = None
    menu_order: dict[str, list[str]] | None = None
    menu_labels: dict[str, str] | None = None
    menu_hidden_keys: list[str] | None = None
    menu_tree_open: dict[str, bool] | None = None


class MemoryPayloadRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class TargetRowsRequest(BaseModel):
    headers: list[Any] = Field(default_factory=list)
    workday: list[Any] = Field(default_factory=list)
    nonworkday: list[Any] = Field(default_factory=list)


class CatalogRowsRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DetailSettingsRequest(BaseModel):
    cooked_to_raw_brown: float = Field(..., gt=0)
    cooked_to_raw_other: float = Field(..., gt=0)
    roster_code_definitions: list[dict[str, Any]] = Field(default_factory=list)


class MaintenanceSheetRequest(BaseModel):
    rows: list[list[Any]] = Field(default_factory=list)


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
    return {
        "ok": True,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "stats": _DEBUG_STATS,
        "health": _health_payload(),
    }


@app.get("/api/diagnostics")
def api_diagnostics() -> dict[str, Any]:
    try:
        return run_integrity_checks(get_settings())
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {e}") from e


@app.get("/api/cutoff")
def api_cutoff() -> dict[str, Any]:
    s = get_settings()
    d = cutoff_date(
        s.dates.timezone,
        s.dates.reject_days_before_today,
    ).isoformat()
    return {"cutoff": d}


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


@app.get("/{asset_name}")
def web_asset(asset_name: str) -> FileResponse:
    if asset_name not in {
        "style.css",
        "api.js",
        "shopping.js",
        "planner.js",
        "planner-maint.js",
        "planner-config.js",
        "planner-render.js",
        "planner-events.js",
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

    try:
        return preview_days_with_cutoff(
            dates,
            skip_date_validation=body.skip_date_validation,
            reroll_nonce=body.reroll_nonce,
            fast_mode=body.fast_mode,
        )
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


@app.post("/api/save-plans")
def api_save_plans(body: SavePlansRequest) -> dict[str, Any]:
    try:
        return save_plan_versions(body.days)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {e}") from e


@app.post("/api/load-plans")
def api_load_plans(body: LoadPlansRequest) -> dict[str, Any]:
    try:
        return load_latest_versions(body.dates, body.versions)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load failed: {e}") from e


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
        save_memory_payload(body.payload)
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
        "rice": {
            "cooked_to_raw_brown": settings.rice.cooked_to_raw_brown,
            "cooked_to_raw_other": settings.rice.cooked_to_raw_other,
        },
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


@app.get("/api/runtime-inputs")
def api_runtime_inputs() -> dict[str, Any]:
    try:
        return list_runtime_input_status(get_settings())
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Load runtime inputs failed: {e}") from e


@app.post("/api/runtime-inputs/import")
def api_import_runtime_inputs() -> dict[str, Any]:
    try:
        settings = get_settings()
        wb = load_workbook_data(settings.workbook_path, validate=False)
        try:
            payload = import_runtime_inputs_from_workbook(settings, wb, replace_existing=True)
        finally:
            wb.close()
        return {"ok": True, **payload}
    except WorkbookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MaintenanceDatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Import runtime inputs failed: {e}") from e


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
        return {"ok": True, **save_sheet_rows(sheet_key, body.rows, get_settings())}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown maintenance sheet: {sheet_key}") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save maintenance sheet failed: {e}") from e


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
        return {
            "ok": True,
            "headers": headers,
            "nutrient_keys": list(NUTRIENT_KEYS),
            "indicator_rows": {
                "workday": workday,
                "nonworkday": nonworkday,
            },
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
        "menu_order": load_menu_order(),
        "menu_labels": load_menu_labels(),
        "menu_hidden_keys": load_menu_hidden_keys(),
        "menu_tree_open": load_menu_tree_open(),
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
        if body.sidebar_width is not None:
            save_sidebar_width(body.sidebar_width)
        if body.show_past is not None:
            save_show_past(body.show_past)
        if body.active_panel is not None:
            save_active_panel(body.active_panel)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"UI state save failed: {e}") from e


def main() -> None:
    import uvicorn

    host = os.environ.get("MENU_API_HOST", "127.0.0.1")
    port = int(os.environ.get("MENU_API_PORT", "8765"))
    free_tcp_port(port)
    uvicorn.run("meal_planner.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
