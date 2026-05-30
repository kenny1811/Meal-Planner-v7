"""JSON persistence for plan versions and UI state."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from meal_planner.settings import get_settings

STORE_SCHEMA_VERSION = 1
# The UI has no restore picker, so per-day history should not grow invisibly.
# File-level backups below cover corruption/accidental overwrite recovery.
MAX_VERSIONS_PER_DATE = 1
MAX_STORE_BACKUPS = 5


def _default_memory_payload() -> dict[str, Any]:
    return {"headers": [], "indicator_rows": {}, "nutrient_keys": [], "days": []}


def _default_ui() -> dict[str, Any]:
    return {
        "column_widths": {},
        "sidebar_width": 260.0,
        "show_past": True,
        "active_panel": "planner",
        "target_editor_width": None,
        "target_column_widths": {},
        "catalog_column_widths": {},
        "form_column_widths": {},
        "menu_order": {
            "top": ["config", "maint", "planner", "shopping", "diagnostics"],
            "config": ["target", "catalog", "details"],
            "maint": [],
        },
        "menu_labels": {},
        "menu_hidden_keys": [],
        "menu_tree_open": {"config": True, "maint": False},
    }


def _default_store() -> dict[str, Any]:
    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "versions_by_date": {},
        "memory_payload": _default_memory_payload(),
        "ui": _default_ui(),
    }


def _store_path() -> Path:
    return get_settings().project_root / "plans_store.json"


def _backup_dir() -> Path:
    return _store_path().parent / ".plans_store_backups"


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _normalise_versions_by_date(raw: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for raw_date, raw_versions in raw.items():
        date_s = str(raw_date or "")
        if not date_s or not isinstance(raw_versions, list):
            continue

        versions: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_versions):
            if not isinstance(item, dict):
                continue
            day = item.get("day")
            if isinstance(day, dict):
                timestamp = str(item.get("timestamp") or f"legacy-{idx + 1:04d}")
                versions.append({"timestamp": timestamp, "day": day})
                continue

            # Older development builds sometimes stored the day object directly.
            if isinstance(item.get("date"), str):
                timestamp = str(item.get("timestamp") or item.get("summary_timestamp") or f"legacy-{idx + 1:04d}")
                versions.append({"timestamp": timestamp, "day": item})

        if versions:
            out[date_s] = versions[-MAX_VERSIONS_PER_DATE:]
    return out


def _normalise_memory_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _default_memory_payload()
    return {
        "headers": raw.get("headers", []),
        "indicator_rows": raw.get("indicator_rows", {}),
        "nutrient_keys": raw.get("nutrient_keys", []),
        "days": raw.get("days", []),
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
        ui["active_panel"] = panel if panel in {"planner", "config", "maint", "shopping", "diagnostics"} else "planner"
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


def _normalise_store(raw: dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return _default_store()
    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "versions_by_date": _normalise_versions_by_date(raw.get("versions_by_date", {})),
        "memory_payload": _normalise_memory_payload(raw.get("memory_payload", {})),
        "ui": _normalise_ui(raw.get("ui", {})),
    }


def _load_store() -> dict[str, Any]:
    data = _read_json_file(_store_path())
    if data is not None:
        return _normalise_store(data)

    for backup in sorted(_backup_dir().glob("plans_store.*.json"), reverse=True):
        data = _read_json_file(backup)
        if data is not None:
            return _normalise_store(data)
    return _default_store()


def _cleanup_backups() -> None:
    backups = sorted(_backup_dir().glob("plans_store.*.json"), reverse=True)
    for backup in backups[MAX_STORE_BACKUPS:]:
        try:
            backup.unlink()
        except OSError:
            continue


def _backup_existing_store() -> None:
    p = _store_path()
    if not p.is_file():
        return

    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"plans_store.{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.json"
    try:
        backup_path.write_bytes(p.read_bytes())
    except OSError:
        return
    _cleanup_backups()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _save_store(data: dict[str, Any]) -> None:
    p = _store_path()
    clean_data = _normalise_store(data)
    payload = json.dumps(clean_data, ensure_ascii=False, indent=2)
    _backup_existing_store()
    _atomic_write_text(p, payload)


def save_plan_versions(days: list[dict[str, Any]]) -> dict[str, Any]:
    data = _load_store()
    versions_by_date = data["versions_by_date"]
    ts = datetime.now().isoformat(timespec="seconds")
    saved_dates: list[str] = []
    for day in days:
        date_s = str(day.get("date") or "")
        if not date_s:
            continue
        versions = versions_by_date.get(date_s)
        if not isinstance(versions, list):
            versions = []
        versions.append({"timestamp": ts, "day": day})
        versions_by_date[date_s] = versions[-MAX_VERSIONS_PER_DATE:]
        saved_dates.append(date_s)
    data["versions_by_date"] = versions_by_date
    _save_store(data)
    return {"timestamp": ts, "saved_dates": saved_dates}


def load_latest_versions(dates: list[str], versions: dict[str, str] | None = None) -> dict[str, Any]:
    data = _load_store()
    versions_by_date = data.get("versions_by_date", {})
    out_days: list[dict[str, Any]] = []
    meta: dict[str, list[str]] = {}
    sel = versions or {}
    for d in dates:
        versions = versions_by_date.get(d)
        if not isinstance(versions, list) or not versions:
            continue
        pick = None
        want_ts = sel.get(d)
        if want_ts:
            for item in versions:
                if isinstance(item, dict) and str(item.get("timestamp") or "") == str(want_ts):
                    pick = item
                    break
        last = pick or versions[-1]
        day = last.get("day")
        if isinstance(day, dict):
            out_days.append(day)
        ts_list = [str(x.get("timestamp")) for x in versions if isinstance(x, dict) and x.get("timestamp")]
        meta[d] = ts_list
    return {"days": out_days, "versions": meta}


def load_all_versions_meta() -> dict[str, list[str]]:
    data = _load_store()
    versions_by_date = data.get("versions_by_date", {})
    if not isinstance(versions_by_date, dict):
        return {}
    out: dict[str, list[str]] = {}
    for d, versions in versions_by_date.items():
        if not isinstance(versions, list) or not versions:
            continue
        ts_list = [str(x.get("timestamp")) for x in versions if isinstance(x, dict) and x.get("timestamp")]
        if ts_list:
            out[str(d)] = ts_list
    return out


def save_memory_payload(payload: dict[str, Any]) -> None:
    data = _load_store()
    base = {
        "headers": payload.get("headers", []),
        "indicator_rows": payload.get("indicator_rows", {}),
        "nutrient_keys": payload.get("nutrient_keys", []),
        "days": payload.get("days", []),
    }
    data["memory_payload"] = base
    _save_store(data)


def load_memory_payload() -> dict[str, Any]:
    data = _load_store()
    p = data.get("memory_payload", {})
    if not isinstance(p, dict):
        return {"headers": [], "indicator_rows": {}, "nutrient_keys": [], "days": []}
    return {
        "headers": p.get("headers", []),
        "indicator_rows": p.get("indicator_rows", {}),
        "nutrient_keys": p.get("nutrient_keys", []),
        "days": p.get("days", []),
    }


def save_column_widths(widths: dict[str, float]) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["column_widths"] = {str(k): float(v) for k, v in widths.items()}
    data["ui"] = ui
    _save_store(data)


def save_sidebar_width(width: float) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["sidebar_width"] = float(width)
    data["ui"] = ui
    _save_store(data)


def save_target_editor_layout(
    width: float | None,
    column_widths: dict[str, float],
    catalog_column_widths: dict[str, float] | None = None,
) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["target_editor_width"] = float(width) if width is not None else None
    ui["target_column_widths"] = {str(k): float(v) for k, v in column_widths.items()}
    if catalog_column_widths is not None:
        ui["catalog_column_widths"] = {str(k): float(v) for k, v in catalog_column_widths.items()}
    data["ui"] = ui
    _save_store(data)


def load_column_widths() -> dict[str, float]:
    data = _load_store()
    ui = data.get("ui", {})
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
    data = _load_store()
    ui = data.get("ui", {})
    try:
        return float(ui.get("sidebar_width", 260.0))
    except Exception:
        return 260.0


def load_target_editor_layout() -> tuple[float | None, dict[str, float], dict[str, float]]:
    data = _load_store()
    ui = data.get("ui", {})
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
    data = _load_store()
    ui = data.get("ui", {})
    ui["form_column_widths"] = {str(k): float(v) for k, v in widths.items()}
    data["ui"] = ui
    _save_store(data)


def load_form_column_widths() -> dict[str, float]:
    data = _load_store()
    ui = data.get("ui", {})
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
    data = _load_store()
    ui = data.get("ui", {})
    clean: dict[str, list[str]] = {}
    for group in ("top", "config", "maint"):
        values = order.get(group) if isinstance(order, dict) else None
        clean[group] = [str(v) for v in values if str(v)] if isinstance(values, list) else []
    ui["menu_order"] = clean
    data["ui"] = ui
    _save_store(data)


def load_menu_order() -> dict[str, list[str]]:
    data = _load_store()
    ui = data.get("ui", {})
    raw = ui.get("menu_order", {})
    if not isinstance(raw, dict):
        return _default_ui()["menu_order"]
    out: dict[str, list[str]] = {}
    for group, defaults in _default_ui()["menu_order"].items():
        values = raw.get(group)
        out[group] = [str(v) for v in values if str(v)] if isinstance(values, list) else list(defaults)
    return out


def save_menu_labels(labels: dict[str, str]) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["menu_labels"] = {
        str(k): str(v).strip()
        for k, v in labels.items()
        if str(k) and str(v).strip()
    } if isinstance(labels, dict) else {}
    data["ui"] = ui
    _save_store(data)


def load_menu_labels() -> dict[str, str]:
    data = _load_store()
    ui = data.get("ui", {})
    raw = ui.get("menu_labels", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): str(v).strip()
        for k, v in raw.items()
        if str(k) and str(v).strip()
    }


def save_menu_hidden_keys(keys: list[str]) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["menu_hidden_keys"] = [str(v) for v in keys if str(v)] if isinstance(keys, list) else []
    data["ui"] = ui
    _save_store(data)


def load_menu_hidden_keys() -> list[str]:
    data = _load_store()
    ui = data.get("ui", {})
    raw = ui.get("menu_hidden_keys", [])
    if not isinstance(raw, list):
        return []
    return [str(v) for v in raw if str(v)]


def save_menu_tree_open(open_state: dict[str, bool]) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    current = load_menu_tree_open()
    if isinstance(open_state, dict):
        for key in ("config", "maint"):
            if key in open_state:
                current[key] = bool(open_state[key])
    ui["menu_tree_open"] = current
    data["ui"] = ui
    _save_store(data)


def load_menu_tree_open() -> dict[str, bool]:
    data = _load_store()
    ui = data.get("ui", {})
    raw = ui.get("menu_tree_open", {})
    defaults = _default_ui()["menu_tree_open"]
    if not isinstance(raw, dict):
        return dict(defaults)
    return {
        "config": bool(raw.get("config", defaults["config"])),
        "maint": bool(raw.get("maint", defaults["maint"])),
    }


def save_show_past(show_past: bool) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["show_past"] = bool(show_past)
    data["ui"] = ui
    _save_store(data)


def load_show_past() -> bool:
    data = _load_store()
    ui = data.get("ui", {})
    return bool(ui.get("show_past", True))


def save_active_panel(panel: str) -> None:
    data = _load_store()
    ui = data.get("ui", {})
    ui["active_panel"] = panel if panel in {"planner", "config", "maint", "shopping", "diagnostics"} else "planner"
    data["ui"] = ui
    _save_store(data)


def load_active_panel() -> str:
    data = _load_store()
    ui = data.get("ui", {})
    panel = str(ui.get("active_panel", "planner"))
    return panel if panel in {"planner", "config", "maint", "shopping", "diagnostics"} else "planner"
