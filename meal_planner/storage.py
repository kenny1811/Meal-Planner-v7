"""Persistence for planner data and UI state."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
from threading import RLock
from typing import Any

from meal_planner.settings import get_settings

# The UI has no restore picker, so per-day history should not grow invisibly.
MAX_VERSIONS_PER_DATE = 1
_STORE_LOCK = RLock()


def _default_memory_payload() -> dict[str, Any]:
    return {"headers": [], "indicator_rows": {}, "nutrient_keys": [], "days": []}


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
            "top": ["planner", "shopping", "config", "maint"],
            "config": ["details", "target"],
            "maint": [
                "catalog",
                "roster",
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
            "target": "營養指標",
            "catalog": "營養清單",
            "details": "系統參數",
            "roster": "更表",
            "overtime": "加班表",
            "payroll_times": "更時表",
            "schedule_grid": "行位表",
            "public_holidays": "公眾假期",
            "medical_appointments": "醫療行程",
            "meal_times": "飯時表",
            "restaurant": "餐廳選擇",
        },
        "menu_hidden_keys": [],
        "menu_tree_open": {"config": True, "maint": False},
    }


def _normalise_ui(raw: Any) -> dict[str, Any]:
    ui = _default_ui()
    if isinstance(raw, dict):
        if isinstance(raw.get("column_widths"), dict):
            ui["column_widths"] = raw["column_widths"]
        try:
            ui["sidebar_width"] = float(raw.get("sidebar_width", ui["sidebar_width"]))
        except Exception:
            pass
        ui["show_past"] = bool(raw.get("show_past", ui["show_past"]))
        panel = str(raw.get("active_panel", ui["active_panel"]))
        ui["active_panel"] = panel if panel in {"planner", "config", "maint", "shopping", "alarm_sync"} else "planner"
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
                for candidate in ("top", "config", "maint"):
                    values = raw_order.get(candidate)
                    if isinstance(values, list) and leaf in [str(v) for v in values]:
                        group = candidate
                        break
            ui["active_menu_path"] = [group, leaf]
        if ui["active_menu_path"] and ui["active_menu_path"][-1] in {"diagnostics", "runtime_import"}:
            ui["active_menu_path"] = ["top", "planner"]
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
            for group in ("top", "config", "maint"):
                values = raw["menu_order"].get(group)
                if isinstance(values, list):
                    order[group] = [str(v) for v in values if str(v)]
            ui["menu_order"] = {**ui["menu_order"], **order}
        if isinstance(raw.get("menu_labels"), dict):
            ui["menu_labels"] = {
                str(k): str(v).strip()
                for k, v in raw["menu_labels"].items()
                if str(k) and str(v).strip()
            }
        if isinstance(raw.get("menu_hidden_keys"), list):
            ui["menu_hidden_keys"] = [str(v) for v in raw["menu_hidden_keys"] if str(v)]
        if isinstance(raw.get("menu_tree_open"), dict):
            ui["menu_tree_open"] = {
                "config": bool(raw["menu_tree_open"].get("config", ui["menu_tree_open"]["config"])),
                "maint": bool(raw["menu_tree_open"].get("maint", ui["menu_tree_open"]["maint"])),
            }
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


@contextmanager
def _plan_db():
    conn = _connect_plan_db()
    try:
        _ensure_plan_schema(conn)
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


def _update_ui(mutator) -> None:
    with _STORE_LOCK:
        ui = _load_ui()
        mutator(ui)
        _save_ui(ui)


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


def load_all_versions_meta() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with _plan_db() as conn:
        rows = conn.execute("SELECT date, timestamp FROM plan_versions ORDER BY date, timestamp").fetchall()
    for row in rows:
        out.setdefault(str(row["date"]), []).append(str(row["timestamp"]))
    return out


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


def load_column_widths() -> dict[str, float]:
    ui = _load_ui()
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


def load_sidebar_width() -> float:
    ui = _load_ui()
    try:
        return float(ui.get("sidebar_width", 260.0))
    except Exception:
        return 260.0


def load_target_editor_layout() -> tuple[float | None, dict[str, float], dict[str, float]]:
    ui = _load_ui()
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


def load_form_column_widths() -> dict[str, float]:
    ui = _load_ui()
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


def save_menu_order(order: dict[str, list[str]]) -> None:
    clean: dict[str, list[str]] = {}
    for group in ("top", "config", "maint"):
        values = order.get(group) if isinstance(order, dict) else None
        clean[group] = [str(v) for v in values if str(v)] if isinstance(values, list) else []
    _update_ui(lambda ui: ui.update({"menu_order": clean}))


def load_menu_order() -> dict[str, list[str]]:
    ui = _load_ui()
    raw = ui.get("menu_order", {})
    if not isinstance(raw, dict):
        return _default_ui()["menu_order"]
    out: dict[str, list[str]] = {}
    for group, defaults in _default_ui()["menu_order"].items():
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


def load_menu_labels() -> dict[str, str]:
    ui = _load_ui()
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


def load_menu_hidden_keys() -> list[str]:
    ui = _load_ui()
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
            for key in ("config", "maint"):
                if key in open_state:
                    current[key] = bool(open_state[key])
        ui["menu_tree_open"] = current

    _update_ui(mutate)


def load_menu_tree_open() -> dict[str, bool]:
    ui = _load_ui()
    raw = ui.get("menu_tree_open", {})
    defaults = _default_ui()["menu_tree_open"]
    if not isinstance(raw, dict):
        return dict(defaults)
    return {
        "config": bool(raw.get("config", defaults["config"])),
        "maint": bool(raw.get("maint", defaults["maint"])),
    }


def save_show_past(show_past: bool) -> None:
    _update_ui(lambda ui: ui.update({"show_past": bool(show_past)}))


def load_show_past() -> bool:
    ui = _load_ui()
    return bool(ui.get("show_past", True))


def save_active_panel(panel: str) -> None:
    value = panel if panel in {"planner", "config", "maint", "shopping", "alarm_sync"} else "planner"
    _update_ui(lambda ui: ui.update({"active_panel": value}))


def load_active_panel() -> str:
    ui = _load_ui()
    panel = str(ui.get("active_panel", "planner"))
    return panel if panel in {"planner", "config", "maint", "shopping", "alarm_sync"} else "planner"


def save_active_config_view(view: str) -> None:
    value = view if view in {"targets", "catalog", "details"} else "targets"
    _update_ui(lambda ui: ui.update({"active_config_view": value}))


def load_active_config_view() -> str:
    ui = _load_ui()
    view = str(ui.get("active_config_view", "targets"))
    return view if view in {"targets", "catalog", "details"} else "targets"


def save_active_menu_path(path: list[str]) -> None:
    clean = [str(v) for v in path if str(v)] if isinstance(path, list) else []
    _update_ui(lambda ui: ui.update({"active_menu_path": clean or ["top", "planner"]}))


def load_active_menu_path() -> list[str]:
    ui = _load_ui()
    path = ui.get("active_menu_path", ["top", "planner"])
    if not isinstance(path, list):
        return ["top", "planner"]
    clean = [str(v) for v in path if str(v)]
    return clean or ["top", "planner"]
