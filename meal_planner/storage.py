"""Persistence for planner data and UI state."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
import threading
from threading import RLock
from typing import Any

from meal_planner.settings import get_settings

# The UI has no restore picker, so per-day history should not grow invisibly.
MAX_VERSIONS_PER_DATE = 1
_STORE_LOCK = RLock()
# 起身表 no longer has its own menu leaf; it is edited via the roster report.
_REMOVED_MENU_KEYS = {"runtime_import", "diagnostics", "wake_alarms"}

DEFAULT_WAKE_OFFSET_HOURS = 3.0


def _coerce_wake_offset_hours(value: Any) -> float:
    """開工前 N 個鐘：非數值或非正數一律回落 3.0 鐘。"""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return DEFAULT_WAKE_OFFSET_HOURS
    if not (hours > 0):
        return DEFAULT_WAKE_OFFSET_HOURS
    return hours


def _default_memory_payload() -> dict[str, Any]:
    return {"headers": [], "indicator_rows": {}, "nutrient_keys": [], "days": []}


# 記得住嘅 panel 得呢一份名單（同 web/planner.js 嘅 PANEL_KEYS 對應）。
# 唔喺名單入面嘅一律當 planner —— 加新 panel 唔加落嚟，refresh 之後就會彈返餐單。
# alarm_sync 係舊 panel，留住等舊 ui_state 唔會突然跳走。
PANEL_KEYS = frozenset(
    {
        "planner", "config", "maint", "shopping", "alarm_sync", "reports",
        "duty_report", "onoffduty", "typhoon",
    }
)


def _default_ui() -> dict[str, Any]:
    return {
        "column_widths": {},
        "sidebar_width": 260.0,
        "show_past": True,
        "active_panel": "planner",
        "active_config_view": "targets",
        "active_menu_path": ["top", "planner"],
        "target_editor_width": None,
        "target_column_widths": {},
        "catalog_column_widths": {},
        "form_column_widths": {},
        "menu_order": {
            "top": ["planner", "shopping", "alarm_sync", "config", "maint", "reports"],
            "config": ["details", "target"],
            "reports": ["shift_code_analysis"],
            "maint": [
                "catalog",
                "roster",
                "wake_alarms",
                "payroll_times",
                "schedule_grid",
                "overtime",
                "public_holidays",
                "medical_appointments",
                "meal_times",
                "meal_patterns",
                "restaurant",
            ],
        },
        "menu_labels": {
            "planner": "餐單",
            "shopping": "購物清單",
            "config": "設置",
            "maint": "餐單參數",
            "reports": "報表",
            "shift_code_analysis": "更碼分析",
            "target": "營養指標",
            "catalog": "營養清單",
            "details": "系統參數",
            "roster": "更表",
            "wake_alarms": "起身表",
            "overtime": "加班表",
            "payroll_times": "更時表",
            "schedule_grid": "行位表",
            "public_holidays": "公眾假期",
            "medical_appointments": "醫療行程",
            "meal_times": "飯時表",
            "restaurant": "餐廳選擇",
        },
        "menu_hidden_keys": [],
        "menu_tree_open": {"config": True, "maint": False, "reports": False},
        "typhoon_state": {},
        "phone_endpoint": {},
        "google_calendar_sync": {
            "enabled": False,
            "write": False,
            "client_secret_file": "",
            "token_file": "",
            "service_account_file": "",
            "nonwork_calendar_id": "",
            "work_calendar_id": "",
            "alarm_calendar_id": "",
            "wake_offset_hours": DEFAULT_WAKE_OFFSET_HOURS,
        },
    }


def _normalise_ui(raw: Any) -> dict[str, Any]:
    ui = _default_ui()
    if isinstance(raw, dict):
        if isinstance(raw.get("column_widths"), dict):
            ui["column_widths"] = raw["column_widths"]
        if isinstance(raw.get("typhoon_state"), dict):
            ui["typhoon_state"] = dict(raw["typhoon_state"])
        if isinstance(raw.get("phone_endpoint"), dict):
            ui["phone_endpoint"] = dict(raw["phone_endpoint"])
        try:
            ui["sidebar_width"] = float(raw.get("sidebar_width", ui["sidebar_width"]))
        except Exception:
            pass
        ui["show_past"] = bool(raw.get("show_past", ui["show_past"]))
        panel = str(raw.get("active_panel", ui["active_panel"]))
        ui["active_panel"] = panel if panel in PANEL_KEYS else "planner"
        fallback_config_view = "catalog" if ui["active_panel"] == "config" and "active_config_view" not in raw else ui["active_config_view"]
        config_view = str(raw.get("active_config_view", fallback_config_view))
        ui["active_config_view"] = config_view if config_view in {"targets", "catalog", "details"} else "targets"
        raw_path = raw.get("active_menu_path")
        if isinstance(raw_path, list) and raw_path:
            ui["active_menu_path"] = [str(v) for v in raw_path if str(v)]
        elif isinstance(raw_path, str) and raw_path.strip():
            ui["active_menu_path"] = [part for part in raw_path.strip().split("/") if part]
        elif ui["active_panel"] == "config":
            leaf = "catalog" if ui["active_config_view"] == "catalog" else ("details" if ui["active_config_view"] == "details" else "target")
            group = "config"
            raw_order = raw.get("menu_order")
            if isinstance(raw_order, dict):
                for candidate in ("top", "config", "maint", "reports"):
                    values = raw_order.get(candidate)
                    if isinstance(values, list) and leaf in [str(v) for v in values]:
                        group = candidate
                        break
            ui["active_menu_path"] = [group, leaf]
        try:
            target_width = raw.get("target_editor_width")
            ui["target_editor_width"] = float(target_width) if target_width is not None else None
        except Exception:
            pass
        if isinstance(raw.get("target_column_widths"), dict):
            widths: dict[str, float] = {}
            for k, v in raw["target_column_widths"].items():
                try:
                    widths[str(k)] = float(v)
                except Exception:
                    continue
            ui["target_column_widths"] = widths
        if isinstance(raw.get("catalog_column_widths"), dict):
            widths: dict[str, float] = {}
            for k, v in raw["catalog_column_widths"].items():
                try:
                    widths[str(k)] = float(v)
                except Exception:
                    continue
            ui["catalog_column_widths"] = widths
        if isinstance(raw.get("form_column_widths"), dict):
            widths: dict[str, float] = {}
            for k, v in raw["form_column_widths"].items():
                try:
                    widths[str(k)] = float(v)
                except Exception:
                    continue
            ui["form_column_widths"] = widths
        if isinstance(raw.get("menu_order"), dict):
            order: dict[str, list[str]] = {}
            groups = list(dict.fromkeys([*ui["menu_order"].keys(), *[str(k) for k in raw["menu_order"].keys() if str(k)]]))
            for group in groups:
                values = raw["menu_order"].get(group)
                if isinstance(values, list):
                    order[group] = [str(v) for v in values if str(v) and str(v) not in _REMOVED_MENU_KEYS]
            ui["menu_order"] = {**ui["menu_order"], **order}
        if isinstance(raw.get("menu_labels"), dict):
            ui["menu_labels"] = {
                str(k): str(v).strip()
                for k, v in raw["menu_labels"].items()
                if str(k) and str(k) not in _REMOVED_MENU_KEYS and str(v).strip()
            }
        if isinstance(raw.get("menu_hidden_keys"), list):
            ui["menu_hidden_keys"] = [str(v) for v in raw["menu_hidden_keys"] if str(v) and str(v) not in _REMOVED_MENU_KEYS]
        if isinstance(raw.get("menu_tree_open"), dict):
            ui["menu_tree_open"] = {
                "config": bool(raw["menu_tree_open"].get("config", ui["menu_tree_open"]["config"])),
                "maint": bool(raw["menu_tree_open"].get("maint", ui["menu_tree_open"]["maint"])),
                "reports": bool(raw["menu_tree_open"].get("reports", ui["menu_tree_open"]["reports"])),
            }
            for key, value in raw["menu_tree_open"].items():
                key_s = str(key)
                if key_s and key_s not in ui["menu_tree_open"]:
                    ui["menu_tree_open"][key_s] = bool(value)
        if isinstance(raw.get("google_calendar_sync"), dict):
            gc = raw["google_calendar_sync"]
            ui["google_calendar_sync"] = {
                "enabled": bool(gc.get("enabled", ui["google_calendar_sync"]["enabled"])),
                "write": bool(gc.get("write", ui["google_calendar_sync"]["write"])),
                "client_secret_file": str(gc.get("client_secret_file") or ""),
                "token_file": str(gc.get("token_file") or ""),
                "service_account_file": str(gc.get("service_account_file") or ""),
                "nonwork_calendar_id": str(gc.get("nonwork_calendar_id") or ""),
                "work_calendar_id": str(gc.get("work_calendar_id") or ""),
                "alarm_calendar_id": str(gc.get("alarm_calendar_id") or ""),
                "wake_offset_hours": _coerce_wake_offset_hours(
                    gc.get("wake_offset_hours", ui["google_calendar_sync"]["wake_offset_hours"])
                ),
            }
    if ui["active_menu_path"] and ui["active_menu_path"][-1] in _REMOVED_MENU_KEYS:
        ui["active_menu_path"] = ["top", "planner"]
    return ui


def _connect_plan_db() -> sqlite3.Connection:
    path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_plan_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS planner_snapshots (
            snapshot_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS plan_versions (
            date TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            day_json TEXT NOT NULL,
            PRIMARY KEY (date, timestamp)
        );
        CREATE TABLE IF NOT EXISTS ui_state (
            state_key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


# Schema DDL 每個 process 每個 db 檔跑一次就夠（CREATE IF NOT EXISTS 本身冪等，
# 但每次讀都跑一輪 executescript 係白蝕，亦令讀操作揸住 write lock）。
_PLAN_SCHEMA_READY: set[str] = set()


@contextmanager
def _plan_db():
    conn = _connect_plan_db()
    try:
        key = str(conn.execute("PRAGMA database_list").fetchone()["file"])
        if key not in _PLAN_SCHEMA_READY:
            _ensure_plan_schema(conn)
            _PLAN_SCHEMA_READY.add(key)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _sqlite_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sqlite_json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _load_ui() -> dict[str, Any]:
    with _plan_db() as conn:
        row = conn.execute("SELECT value_json FROM ui_state WHERE state_key = 'current'").fetchone()
    if row is None:
        return _default_ui()
    return _normalise_ui(_sqlite_json_loads(str(row["value_json"]), {}))


def _save_ui(ui: dict[str, Any]) -> None:
    clean = _normalise_ui(ui)
    ts = datetime.now().isoformat(timespec="seconds")
    with _plan_db() as conn:
        conn.execute(
            """
            INSERT INTO ui_state(state_key, value_json, updated_at)
            VALUES ('current', ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (_sqlite_json_dumps(clean), ts),
        )


_UI_BATCH = threading.local()


def _update_ui(mutator) -> None:
    batched = getattr(_UI_BATCH, "ui", None)
    if batched is not None:
        mutator(batched)
        return
    with _STORE_LOCK:
        ui = _load_ui()
        mutator(ui)
        _save_ui(ui)


@contextmanager
def batch_ui_updates():
    """將 block 內所有 save_*（_update_ui）合併成一次 load + normalise + write。

    /api/ui-state POST 一個 patch 可以掂十幾個欄位；冇呢個 batch 就係
    每個欄位各自開 connection 重讀重寫成個 UI blob。
    """
    if getattr(_UI_BATCH, "ui", None) is not None:
        yield
        return
    with _STORE_LOCK:
        _UI_BATCH.ui = _load_ui()
        try:
            yield
            _save_ui(_UI_BATCH.ui)
        finally:
            _UI_BATCH.ui = None


def load_ui_snapshot() -> dict[str, Any]:
    """成個 UI state 讀一次，俾 load_*(ui=...) 共用，唔使每個欄位開一次 db。"""
    return _load_ui()


def save_plan_versions(days: list[dict[str, Any]]) -> dict[str, Any]:
    ts = datetime.now().isoformat(timespec="seconds")
    saved_dates: list[str] = []
    with _plan_db() as conn:
        for day in days:
            date_s = str(day.get("date") or "")
            if not date_s:
                continue
            conn.execute("DELETE FROM plan_versions WHERE date = ?", (date_s,))
            conn.execute(
                "INSERT INTO plan_versions(date, timestamp, day_json) VALUES (?, ?, ?)",
                (date_s, ts, _sqlite_json_dumps(day)),
            )
            saved_dates.append(date_s)
    return {"timestamp": ts, "saved_dates": saved_dates}


def load_latest_versions(dates: list[str], versions: dict[str, str] | None = None) -> dict[str, Any]:
    out_days: list[dict[str, Any]] = []
    meta: dict[str, list[str]] = {}
    sel = versions or {}
    with _plan_db() as conn:
        for d in dates:
            rows = conn.execute(
                "SELECT timestamp, day_json FROM plan_versions WHERE date = ? ORDER BY timestamp",
                (str(d),),
            ).fetchall()
            if not rows:
                continue
            want_ts = str(sel.get(d) or "")
            pick = next((row for row in rows if str(row["timestamp"]) == want_ts), rows[-1])
            day = _sqlite_json_loads(str(pick["day_json"]), {})
            if isinstance(day, dict):
                out_days.append(day)
            meta[str(d)] = [str(row["timestamp"]) for row in rows]
    return {"days": out_days, "versions": meta}


def merge_memory_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial UI memory save without dropping days absent from the browser payload."""
    existing = existing if isinstance(existing, dict) else {}
    incoming = incoming if isinstance(incoming, dict) else {}
    by_date: dict[str, dict[str, Any]] = {}
    for source in (existing.get("days", []), incoming.get("days", [])):
        if not isinstance(source, list):
            continue
        for day in source:
            if not isinstance(day, dict):
                continue
            date_s = str(day.get("date") or "")
            if date_s:
                by_date[date_s] = day
    return {
        "headers": incoming.get("headers") or existing.get("headers", []),
        "indicator_rows": incoming.get("indicator_rows") or existing.get("indicator_rows", {}),
        "nutrient_keys": incoming.get("nutrient_keys") or existing.get("nutrient_keys", []),
        "days": [by_date[k] for k in sorted(by_date)],
    }


def save_memory_payload(payload: dict[str, Any]) -> None:
    base = {
        "headers": payload.get("headers", []),
        "indicator_rows": payload.get("indicator_rows", {}),
        "nutrient_keys": payload.get("nutrient_keys", []),
        "days": payload.get("days", []),
    }
    ts = datetime.now().isoformat(timespec="seconds")
    with _plan_db() as conn:
        conn.execute(
            """
            INSERT INTO planner_snapshots(snapshot_key, payload_json, updated_at)
            VALUES ('current', ?, ?)
            ON CONFLICT(snapshot_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (_sqlite_json_dumps(base), ts),
        )
    # 同步鏡射每日餐單入 plan_versions，令直接讀 sqlite（一行一日嘅 plan_versions 表）
    # 都見到最新資料，而唔止收埋喺 planner_snapshots 嗰浸大 JSON blob 入面。
    days = base.get("days")
    if isinstance(days, list) and days:
        save_plan_versions(days)


def load_memory_payload() -> dict[str, Any]:
    with _plan_db() as conn:
        row = conn.execute(
            "SELECT payload_json FROM planner_snapshots WHERE snapshot_key = 'current'"
        ).fetchone()
    if row is None:
        p = _default_memory_payload()
    else:
        p = _sqlite_json_loads(str(row["payload_json"]), {})
    if not isinstance(p, dict):
        return {"headers": [], "indicator_rows": {}, "nutrient_keys": [], "days": []}
    return {
        "headers": p.get("headers", []),
        "indicator_rows": p.get("indicator_rows", {}),
        "nutrient_keys": p.get("nutrient_keys", []),
        "days": p.get("days", []),
    }


def save_column_widths(widths: dict[str, float]) -> None:
    def mutate(ui: dict[str, Any]) -> None:
        current = ui.get("column_widths") if isinstance(ui.get("column_widths"), dict) else {}
        current = {str(k): float(v) for k, v in current.items()}
        current.update({str(k): float(v) for k, v in widths.items()})
        ui["column_widths"] = current

    _update_ui(mutate)


def save_sidebar_width(width: float) -> None:
    _update_ui(lambda ui: ui.update({"sidebar_width": float(width)}))


def save_target_editor_layout(
    width: float | None,
    column_widths: dict[str, float] | None,
    catalog_column_widths: dict[str, float] | None = None,
) -> None:
    def mutate(ui: dict[str, Any]) -> None:
        ui["target_editor_width"] = float(width) if width is not None else None
        if column_widths is not None:
            current = ui.get("target_column_widths") if isinstance(ui.get("target_column_widths"), dict) else {}
            current = {str(k): float(v) for k, v in current.items()}
            current.update({str(k): float(v) for k, v in column_widths.items()})
            ui["target_column_widths"] = current
        if catalog_column_widths is not None:
            current = ui.get("catalog_column_widths") if isinstance(ui.get("catalog_column_widths"), dict) else {}
            current = {str(k): float(v) for k, v in current.items()}
            current.update({str(k): float(v) for k, v in catalog_column_widths.items()})
            ui["catalog_column_widths"] = current

    _update_ui(mutate)


def load_column_widths(ui: dict[str, Any] | None = None) -> dict[str, float]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("column_widths", {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


def load_sidebar_width(ui: dict[str, Any] | None = None) -> float:
    ui = _load_ui() if ui is None else ui
    try:
        return float(ui.get("sidebar_width", 260.0))
    except Exception:
        return 260.0


def load_target_editor_layout(ui: dict[str, Any] | None = None) -> tuple[float | None, dict[str, float], dict[str, float]]:
    ui = _load_ui() if ui is None else ui
    try:
        width_raw = ui.get("target_editor_width")
        width = float(width_raw) if width_raw is not None else None
    except Exception:
        width = None
    raw = ui.get("target_column_widths", {})
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
    catalog_raw = ui.get("catalog_column_widths", {})
    catalog_out: dict[str, float] = {}
    if isinstance(catalog_raw, dict):
        for k, v in catalog_raw.items():
            try:
                catalog_out[str(k)] = float(v)
            except Exception:
                continue
    return width, out, catalog_out


def save_form_column_widths(widths: dict[str, float]) -> None:
    def mutate(ui: dict[str, Any]) -> None:
        current = ui.get("form_column_widths") if isinstance(ui.get("form_column_widths"), dict) else {}
        current = {str(k): float(v) for k, v in current.items()}
        current.update({str(k): float(v) for k, v in widths.items()})
        ui["form_column_widths"] = current

    _update_ui(mutate)


def load_form_column_widths(ui: dict[str, Any] | None = None) -> dict[str, float]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("form_column_widths", {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


def save_google_calendar_sync_settings(settings: dict[str, Any]) -> None:
    def mutate(ui: dict[str, Any]) -> None:
        current = ui.get("google_calendar_sync") if isinstance(ui.get("google_calendar_sync"), dict) else {}
        ui["google_calendar_sync"] = {
            "enabled": bool(settings.get("enabled")) if isinstance(settings, dict) and "enabled" in settings else bool(current.get("enabled")),
            "write": bool(settings.get("write")) if isinstance(settings, dict) and "write" in settings else bool(current.get("write")),
            "client_secret_file": str(settings.get("client_secret_file", current.get("client_secret_file", "")) or "") if isinstance(settings, dict) else str(current.get("client_secret_file", "") or ""),
            "token_file": str(settings.get("token_file", current.get("token_file", "")) or "") if isinstance(settings, dict) else str(current.get("token_file", "") or ""),
            "service_account_file": str(settings.get("service_account_file", current.get("service_account_file", "")) or "") if isinstance(settings, dict) else str(current.get("service_account_file", "") or ""),
            "nonwork_calendar_id": str(settings.get("nonwork_calendar_id", current.get("nonwork_calendar_id", "")) or "") if isinstance(settings, dict) else str(current.get("nonwork_calendar_id", "") or ""),
            "work_calendar_id": str(settings.get("work_calendar_id", current.get("work_calendar_id", "")) or "") if isinstance(settings, dict) else str(current.get("work_calendar_id", "") or ""),
            "alarm_calendar_id": str(settings.get("alarm_calendar_id", current.get("alarm_calendar_id", "")) or "") if isinstance(settings, dict) else str(current.get("alarm_calendar_id", "") or ""),
            "wake_offset_hours": _coerce_wake_offset_hours(settings.get("wake_offset_hours", current.get("wake_offset_hours", DEFAULT_WAKE_OFFSET_HOURS))) if isinstance(settings, dict) else _coerce_wake_offset_hours(current.get("wake_offset_hours", DEFAULT_WAKE_OFFSET_HOURS)),
        }

    _update_ui(mutate)


def _builtin_calendar_ids() -> tuple[str, str]:
    """更表 / 起身 兩個內建預設 Calendar ID（單一來源喺 google_calendar_sync）。"""
    from meal_planner.google_calendar_sync import ALARM_CALENDAR_ID, WORK_CALENDAR_ID

    return WORK_CALENDAR_ID, ALARM_CALENDAR_ID


def load_google_calendar_sync_settings(ui: dict[str, Any] | None = None) -> dict[str, Any]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("google_calendar_sync", {})
    if not isinstance(raw, dict):
        raw = {}
    default_work, default_alarm = _builtin_calendar_ids()
    return {
        "enabled": bool(raw.get("enabled")),
        "write": bool(raw.get("write")),
        "client_secret_file": str(raw.get("client_secret_file") or ""),
        "token_file": str(raw.get("token_file") or ""),
        "service_account_file": str(raw.get("service_account_file") or ""),
        "nonwork_calendar_id": str(raw.get("nonwork_calendar_id") or ""),
        "work_calendar_id": str(raw.get("work_calendar_id") or "") or default_work,
        "alarm_calendar_id": str(raw.get("alarm_calendar_id") or "") or default_alarm,
        "wake_offset_hours": _coerce_wake_offset_hours(raw.get("wake_offset_hours", DEFAULT_WAKE_OFFSET_HOURS)),
    }


def save_menu_order(order: dict[str, list[str]]) -> None:
    clean: dict[str, list[str]] = {}
    groups = list(dict.fromkeys(["top", "config", "maint", "reports", *[str(k) for k in order.keys() if str(k)]])) if isinstance(order, dict) else ["top", "config", "maint", "reports"]
    for group in groups:
        values = order.get(group) if isinstance(order, dict) else None
        clean[group] = [str(v) for v in values if str(v)] if isinstance(values, list) else []
    _update_ui(lambda ui: ui.update({"menu_order": clean}))


def load_menu_order(ui: dict[str, Any] | None = None) -> dict[str, list[str]]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("menu_order", {})
    if not isinstance(raw, dict):
        return _default_ui()["menu_order"]
    out: dict[str, list[str]] = {}
    groups = list(dict.fromkeys([*_default_ui()["menu_order"].keys(), *[str(k) for k in raw.keys() if str(k)]]))
    for group in groups:
        defaults = _default_ui()["menu_order"].get(group, [])
        values = raw.get(group)
        out[group] = [str(v) for v in values if str(v)] if isinstance(values, list) else list(defaults)
    return out


def save_menu_labels(labels: dict[str, str]) -> None:
    clean = {
        str(k): str(v).strip()
        for k, v in labels.items()
        if str(k) and str(v).strip()
    } if isinstance(labels, dict) else {}
    _update_ui(lambda ui: ui.update({"menu_labels": clean}))


def load_menu_labels(ui: dict[str, Any] | None = None) -> dict[str, str]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("menu_labels", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): str(v).strip()
        for k, v in raw.items()
        if str(k) and str(v).strip()
    }


def save_menu_hidden_keys(keys: list[str]) -> None:
    clean = [str(v) for v in keys if str(v)] if isinstance(keys, list) else []
    _update_ui(lambda ui: ui.update({"menu_hidden_keys": clean}))


def load_menu_hidden_keys(ui: dict[str, Any] | None = None) -> list[str]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("menu_hidden_keys", [])
    if not isinstance(raw, list):
        return []
    return [str(v) for v in raw if str(v)]


def save_menu_tree_open(open_state: dict[str, bool]) -> None:
    def mutate(ui: dict[str, Any]) -> None:
        current = ui.get("menu_tree_open")
        if not isinstance(current, dict):
            current = dict(_default_ui()["menu_tree_open"])
        if isinstance(open_state, dict):
            for key in list(dict.fromkeys(["config", "maint", "reports", *[str(k) for k in open_state.keys() if str(k)]])):
                if key in open_state:
                    current[key] = bool(open_state[key])
        ui["menu_tree_open"] = current

    _update_ui(mutate)


def save_typhoon_state(state: dict[str, Any]) -> None:
    """Typhoon panel 上次嘅輸入（日期／落波／個名／確實／更碼）——下次開返同一個畫面。"""
    clean = {
        str(k): ("" if v is None else v)
        for k, v in state.items()
        if str(k) in {"date_iso", "signal_time", "name", "confirmed", "day_off", "code"}
    } if isinstance(state, dict) else {}
    _update_ui(lambda ui: ui.update({"typhoon_state": clean}))


def save_phone_endpoint(endpoint: dict[str, Any]) -> None:
    """電話最後一次打上嚟嘅位置（IP + 時間）——電腦要 push 落電話嗰陣用。"""
    clean = {
        str(k): endpoint[k]
        for k in ("host", "seen_at")
        if isinstance(endpoint, dict) and k in endpoint
    }
    _update_ui(lambda ui: ui.update({"phone_endpoint": clean}))


def load_phone_endpoint(ui: dict[str, Any] | None = None) -> dict[str, Any]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("phone_endpoint", {})
    return dict(raw) if isinstance(raw, dict) else {}


def load_typhoon_state(ui: dict[str, Any] | None = None) -> dict[str, Any]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("typhoon_state", {})
    return dict(raw) if isinstance(raw, dict) else {}


def load_menu_tree_open(ui: dict[str, Any] | None = None) -> dict[str, bool]:
    ui = _load_ui() if ui is None else ui
    raw = ui.get("menu_tree_open", {})
    defaults = _default_ui()["menu_tree_open"]
    if not isinstance(raw, dict):
        return dict(defaults)
    out = {
        "config": bool(raw.get("config", defaults["config"])),
        "maint": bool(raw.get("maint", defaults["maint"])),
        "reports": bool(raw.get("reports", defaults["reports"])),
    }
    for key, value in raw.items():
        key_s = str(key)
        if key_s and key_s not in out:
            out[key_s] = bool(value)
    return out


def save_show_past(show_past: bool) -> None:
    _update_ui(lambda ui: ui.update({"show_past": bool(show_past)}))


def load_show_past(ui: dict[str, Any] | None = None) -> bool:
    ui = _load_ui() if ui is None else ui
    return bool(ui.get("show_past", True))


def save_active_panel(panel: str) -> None:
    value = panel if panel in PANEL_KEYS else "planner"
    _update_ui(lambda ui: ui.update({"active_panel": value}))


def load_active_panel(ui: dict[str, Any] | None = None) -> str:
    ui = _load_ui() if ui is None else ui
    panel = str(ui.get("active_panel", "planner"))
    return panel if panel in PANEL_KEYS else "planner"


def save_active_config_view(view: str) -> None:
    value = view if view in {"targets", "catalog", "details"} else "targets"
    _update_ui(lambda ui: ui.update({"active_config_view": value}))


def load_active_config_view(ui: dict[str, Any] | None = None) -> str:
    ui = _load_ui() if ui is None else ui
    view = str(ui.get("active_config_view", "targets"))
    return view if view in {"targets", "catalog", "details"} else "targets"


def save_active_menu_path(path: list[str]) -> None:
    clean = [str(v) for v in path if str(v)] if isinstance(path, list) else []
    _update_ui(lambda ui: ui.update({"active_menu_path": clean or ["top", "planner"]}))


def load_active_menu_path(ui: dict[str, Any] | None = None) -> list[str]:
    ui = _load_ui() if ui is None else ui
    path = ui.get("active_menu_path", ["top", "planner"])
    if not isinstance(path, list):
        return ["top", "planner"]
    clean = [str(v) for v in path if str(v)]
    return clean or ["top", "planner"]
