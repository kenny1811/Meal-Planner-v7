"""SQLite persistence for the Phase 1 nutrition catalog and target rows."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from openpyxl.workbook.workbook import Workbook

from meal_planner.indicators import NUTRIENT_KEYS, parse_indicator_cell
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings, get_settings

SCHEMA_VERSION = 1
TARGET_PROFILES = ("workday", "nonworkday")


class NutritionDatabaseError(RuntimeError):
    """SQLite nutrition data is unavailable and cannot be bootstrapped."""


def database_path(settings: AppSettings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.database_path


def _connect(settings: AppSettings) -> sqlite3.Connection:
    path = database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nutrition_catalog (
            row_index INTEGER PRIMARY KEY,
            paused INTEGER NOT NULL,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            min_g REAL,
            max_g REAL,
            daymax_g REAL,
            kcal REAL NOT NULL,
            protein_g REAL NOT NULL,
            carb_g REAL NOT NULL,
            sugar_g REAL NOT NULL,
            cholesterol_mg REAL NOT NULL,
            sodium_mg REAL NOT NULL,
            calcium_mg REAL NOT NULL,
            fat_total_g REAL NOT NULL,
            fat_sat_g REAL NOT NULL,
            fat_trans_g REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nutrition_targets (
            profile TEXT NOT NULL CHECK(profile IN ('workday', 'nonworkday')),
            nutrient_key TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            header TEXT,
            raw_value TEXT,
            PRIMARY KEY (profile, nutrient_key)
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def _has_rows(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
    return row is not None


def _seed_catalog(conn: sqlite3.Connection, entries: list[NutritionEntry]) -> None:
    conn.executemany(
        """
        INSERT INTO nutrition_catalog (
            row_index, paused, category, name, min_g, max_g, daymax_g,
            kcal, protein_g, carb_g, sugar_g, cholesterol_mg,
            sodium_mg, calcium_mg, fat_total_g, fat_sat_g, fat_trans_g
        ) VALUES (
            :row_index, :paused, :category, :name, :min_g, :max_g, :daymax_g,
            :kcal, :protein_g, :carb_g, :sugar_g, :cholesterol_mg,
            :sodium_mg, :calcium_mg, :fat_total_g, :fat_sat_g, :fat_trans_g
        )
        """,
        [
            {
                "row_index": entry.row_index,
                "paused": int(entry.paused),
                "category": entry.category,
                "name": entry.name,
                "min_g": entry.min_g,
                "max_g": entry.max_g,
                "daymax_g": entry.daymax_g,
                **{key: float(entry.nutrients.get(key, 0.0)) for key in NUTRIENT_KEYS},
            }
            for entry in entries
        ],
    )


def _seed_targets(
    conn: sqlite3.Connection,
    headers: list[Any],
    work_vals: list[Any],
    nonwork_vals: list[Any],
) -> None:
    rows: list[dict[str, Any]] = []
    values_by_profile = {
        "workday": work_vals,
        "nonworkday": nonwork_vals,
    }
    for sort_order, nutrient_key in enumerate(NUTRIENT_KEYS):
        header = headers[sort_order] if sort_order < len(headers) else None
        for profile, values in values_by_profile.items():
            value = values[sort_order] if sort_order < len(values) else None
            rows.append(
                {
                    "profile": profile,
                    "nutrient_key": nutrient_key,
                    "sort_order": sort_order,
                    "header": None if header is None else str(header),
                    "raw_value": None if value is None else str(value),
                }
            )
    conn.executemany(
        """
        INSERT INTO nutrition_targets(profile, nutrient_key, sort_order, header, raw_value)
        VALUES (:profile, :nutrient_key, :sort_order, :header, :raw_value)
        """,
        rows,
    )


def bootstrap_from_workbook(
    settings: AppSettings,
    wb: Workbook,
    *,
    need_catalog: bool = True,
    need_targets: bool = True,
) -> None:
    """Seed missing Phase 1 tables once from the legacy workbook."""
    from meal_planner.excel_io import get_sheet, read_menu_v5_indicators
    from meal_planner.nutrition_catalog import load_nutrition_entries

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        seed_catalog = bool(need_catalog and not _has_rows(conn, "nutrition_catalog"))
        seed_targets = bool(need_targets and not _has_rows(conn, "nutrition_targets"))
        if not seed_catalog and not seed_targets:
            return

        try:
            if seed_catalog:
                entries = load_nutrition_entries(get_sheet(wb, settings.sheets.nutrition_list))
                _seed_catalog(conn, entries)
            if seed_targets:
                headers, work_vals, nonwork_vals = read_menu_v5_indicators(settings, wb)
                _seed_targets(conn, headers, work_vals, nonwork_vals)
        except Exception as exc:
            conn.rollback()
            raise NutritionDatabaseError(
                "SQLite nutrition data is empty and Excel bootstrap failed."
            ) from exc
        conn.commit()


def load_catalog_entries(settings: AppSettings | None = None, wb: Workbook | None = None) -> list[NutritionEntry]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        has_catalog = _has_rows(conn, "nutrition_catalog")
    if not has_catalog:
        if wb is None:
            raise NutritionDatabaseError("SQLite nutrition catalog is empty and no workbook was provided.")
        bootstrap_from_workbook(settings, wb, need_targets=False)

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM nutrition_catalog
            ORDER BY row_index
            """
        ).fetchall()
    return [
        NutritionEntry(
            row_index=int(row["row_index"]),
            paused=bool(row["paused"]),
            category=str(row["category"]),
            name=str(row["name"]),
            nutrients={key: float(row[key] or 0.0) for key in NUTRIENT_KEYS},
            min_g=float(row["min_g"]) if row["min_g"] is not None else None,
            max_g=float(row["max_g"]) if row["max_g"] is not None else None,
            daymax_g=float(row["daymax_g"]) if row["daymax_g"] is not None else None,
        )
        for row in rows
    ]


def _catalog_float(raw: Any, *, label: str, optional: bool = False) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None if optional else 0.0
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Nutrition catalog {label} must be numeric.") from exc


def save_catalog_entries(
    rows: list[dict[str, Any]],
    settings: AppSettings | None = None,
) -> list[NutritionEntry]:
    """Replace the editable SQLite nutrition catalog in displayed row order."""
    settings = settings or get_settings()
    clean_rows: list[dict[str, Any]] = []
    seen_rows: set[int] = set()
    next_row_index = 2
    for pos, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not category and not name:
            continue
        if not category or not name:
            raise ValueError(f"Nutrition catalog row {pos} requires Category and Name.")
        row_index_raw = raw.get("row_index")
        try:
            row_index = int(row_index_raw) if row_index_raw not in (None, "") else None
        except (TypeError, ValueError):
            row_index = None
        if row_index is None or row_index < 2 or row_index in seen_rows:
            while next_row_index in seen_rows:
                next_row_index += 1
            row_index = next_row_index
        seen_rows.add(row_index)
        next_row_index = max(next_row_index, row_index + 1)
        nutrients_raw = raw.get("nutrients") if isinstance(raw.get("nutrients"), dict) else {}
        clean_rows.append(
            {
                "row_index": row_index,
                "paused": int(bool(raw.get("paused"))),
                "category": category,
                "name": name,
                "min_g": _catalog_float(raw.get("min_g"), label=f"row {pos} Min (g)", optional=True),
                "max_g": _catalog_float(raw.get("max_g"), label=f"row {pos} Max (g)", optional=True),
                "daymax_g": _catalog_float(raw.get("daymax_g"), label=f"row {pos} DayMax (g)", optional=True),
                **{
                    key: _catalog_float(nutrients_raw.get(key), label=f"row {pos} {key}") or 0.0
                    for key in NUTRIENT_KEYS
                },
            }
        )

    if not clean_rows:
        raise ValueError("Nutrition catalog cannot be empty.")

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM nutrition_catalog")
        conn.executemany(
            """
            INSERT INTO nutrition_catalog (
                row_index, paused, category, name, min_g, max_g, daymax_g,
                kcal, protein_g, carb_g, sugar_g, cholesterol_mg,
                sodium_mg, calcium_mg, fat_total_g, fat_sat_g, fat_trans_g
            ) VALUES (
                :row_index, :paused, :category, :name, :min_g, :max_g, :daymax_g,
                :kcal, :protein_g, :carb_g, :sugar_g, :cholesterol_mg,
                :sodium_mg, :calcium_mg, :fat_total_g, :fat_sat_g, :fat_trans_g
            )
            """,
            clean_rows,
        )
        conn.commit()
    return load_catalog_entries(settings)


def load_target_rows(
    settings: AppSettings | None = None,
    wb: Workbook | None = None,
) -> tuple[list[str | None], list[str | None], list[str | None]]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        has_targets = _has_rows(conn, "nutrition_targets")
    if not has_targets:
        if wb is None:
            raise NutritionDatabaseError("SQLite nutrition targets are empty and no workbook was provided.")
        bootstrap_from_workbook(settings, wb, need_catalog=False)

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT profile, nutrient_key, sort_order, header, raw_value
            FROM nutrition_targets
            ORDER BY sort_order, profile
            """
        ).fetchall()

    by_profile = {profile: {} for profile in TARGET_PROFILES}
    headers: dict[str, str | None] = {}
    for row in rows:
        nutrient_key = str(row["nutrient_key"])
        profile = str(row["profile"])
        if nutrient_key not in NUTRIENT_KEYS or profile not in by_profile:
            continue
        headers[nutrient_key] = row["header"]
        by_profile[profile][nutrient_key] = row["raw_value"]
    return (
        [headers.get(key) for key in NUTRIENT_KEYS],
        [by_profile["workday"].get(key) for key in NUTRIENT_KEYS],
        [by_profile["nonworkday"].get(key) for key in NUTRIENT_KEYS],
    )


def save_target_rows(
    headers: list[Any],
    work_vals: list[Any],
    nonwork_vals: list[Any],
    settings: AppSettings | None = None,
) -> tuple[list[str | None], list[str | None], list[str | None]]:
    """Replace the editable target rows stored in SQLite."""
    settings = settings or get_settings()
    missing: list[str] = []
    invalid: list[str] = []
    values_by_profile = {
        "workday": work_vals,
        "nonworkday": nonwork_vals,
    }
    for profile, values in values_by_profile.items():
        for idx, nutrient_key in enumerate(NUTRIENT_KEYS):
            value = values[idx] if idx < len(values) else None
            raw = "" if value is None else str(value).strip()
            if not raw:
                missing.append(f"{profile}/{nutrient_key}")
            elif parse_indicator_cell(raw) is None:
                invalid.append(f"{profile}/{nutrient_key}")
    if missing:
        raise ValueError("Target values cannot be blank: " + ", ".join(missing))
    if invalid:
        raise ValueError("Target values are not valid indicators: " + ", ".join(invalid))

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM nutrition_targets")
        _seed_targets(conn, headers, work_vals, nonwork_vals)
        conn.commit()
    return load_target_rows(settings)
