"""SQLite persistence for the Phase 1 nutrition catalog and target rows."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl.workbook.workbook import Workbook

from meal_planner.indicators import NUTRIENT_KEYS, parse_indicator_cell
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings, get_settings

SCHEMA_VERSION = 1
TARGET_PROFILES = ("workday", "nonworkday")
TARGET_SETTING_KEYS = (
    "activity_factor",
    "calorie_range_band",
    "protein_g_per_kg",
    "protein_range_band",
    "carb_pct",
    "calcium_mg",
    "sodium_mg",
    "sugar_g",
    "cholesterol_mg",
    "fat_total_pct",
    "fat_sat_pct",
    "fat_trans_pct",
)
DEFAULT_TARGET_SETTINGS: dict[str, dict[str, float]] = {
    "workday": {
        "activity_factor": 1.35,
        "calorie_range_band": 50.0,
        "protein_g_per_kg": 1.75,
        "protein_range_band": 10.0,
        "carb_pct": 45.0,
        "calcium_mg": 1200.0,
        "sodium_mg": 2000.0,
        "sugar_g": 35.0,
        "cholesterol_mg": 200.0,
        "fat_total_pct": 27.5,
        "fat_sat_pct": 7.0,
        "fat_trans_pct": 1.0,
    },
    "nonworkday": {
        "activity_factor": 1.20,
        "calorie_range_band": 50.0,
        "protein_g_per_kg": 1.75,
        "protein_range_band": 10.0,
        "carb_pct": 45.0,
        "calcium_mg": 1000.0,
        "sodium_mg": 1700.0,
        "sugar_g": 50.0,
        "cholesterol_mg": 200.0,
        "fat_total_pct": 27.5,
        "fat_sat_pct": 7.0,
        "fat_trans_pct": 1.0,
    },
}


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

        CREATE TABLE IF NOT EXISTS nutrition_profile (
            profile_key TEXT PRIMARY KEY CHECK(profile_key = 'current'),
            dob TEXT,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            last_updated TEXT
        );

        CREATE TABLE IF NOT EXISTS nutrition_weight_history (
            recorded_at TEXT NOT NULL,
            weight_kg REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nutrition_target_settings (
            profile TEXT NOT NULL CHECK(profile IN ('workday', 'nonworkday')),
            setting_key TEXT NOT NULL,
            value REAL NOT NULL,
            PRIMARY KEY (profile, setting_key)
        );
        """
    )
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(nutrition_profile)").fetchall()
    }
    if "dob" not in columns:
        conn.execute("ALTER TABLE nutrition_profile ADD COLUMN dob TEXT")
    if "last_updated" not in columns:
        conn.execute("ALTER TABLE nutrition_profile ADD COLUMN last_updated TEXT")
    history_count = conn.execute("SELECT COUNT(*) AS c FROM nutrition_weight_history").fetchone()
    profile_row = conn.execute(
        "SELECT weight_kg, last_updated FROM nutrition_profile WHERE profile_key = 'current'"
    ).fetchone()
    if (
        history_count is not None
        and int(history_count["c"] or 0) == 0
        and profile_row is not None
        and profile_row["weight_kg"] is not None
    ):
        recorded_at = str(profile_row["last_updated"] or "") or datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO nutrition_weight_history(recorded_at, weight_kg) VALUES (?, ?)",
            (recorded_at, float(profile_row["weight_kg"])),
        )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    for profile, values in DEFAULT_TARGET_SETTINGS.items():
        for key, value in values.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO nutrition_target_settings(profile, setting_key, value)
                VALUES (?, ?, ?)
                """,
                (profile, key, float(value)),
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


def load_target_settings(settings: AppSettings | None = None) -> dict[str, dict[str, float]]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT profile, setting_key, value
            FROM nutrition_target_settings
            ORDER BY profile, setting_key
            """
        ).fetchall()
    out = {
        profile: dict(DEFAULT_TARGET_SETTINGS[profile])
        for profile in TARGET_PROFILES
    }
    for row in rows:
        profile = str(row["profile"])
        key = str(row["setting_key"])
        if profile in out and key in TARGET_SETTING_KEYS:
            out[profile][key] = float(row["value"])
    return out


def save_target_settings(
    target_settings: dict[str, Any],
    settings: AppSettings | None = None,
) -> dict[str, dict[str, float]]:
    settings = settings or get_settings()
    clean = {
        profile: dict(DEFAULT_TARGET_SETTINGS[profile])
        for profile in TARGET_PROFILES
    }
    if isinstance(target_settings, dict):
        for profile in TARGET_PROFILES:
            raw_values = target_settings.get(profile)
            if not isinstance(raw_values, dict):
                continue
            for key in TARGET_SETTING_KEYS:
                raw = raw_values.get(key)
                if raw in (None, ""):
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Target setting {profile}/{key} must be numeric.") from exc
                if value < 0:
                    raise ValueError(f"Target setting {profile}/{key} must be zero or greater.")
                clean[profile][key] = value

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        conn.executemany(
            """
            INSERT INTO nutrition_target_settings(profile, setting_key, value)
            VALUES (:profile, :setting_key, :value)
            ON CONFLICT(profile, setting_key) DO UPDATE SET
                value = excluded.value
            """,
            [
                {"profile": profile, "setting_key": key, "value": float(value)}
                for profile, values in clean.items()
                for key, value in values.items()
            ],
        )
        conn.commit()
    return load_target_settings(settings)


def load_nutrition_profile(settings: AppSettings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT dob, age, gender, height_cm, weight_kg, last_updated
            FROM nutrition_profile
            WHERE profile_key = 'current'
            """
        ).fetchone()
        history_rows = conn.execute(
            """
            SELECT recorded_at, weight_kg
            FROM (
                SELECT rowid, recorded_at, weight_kg
                FROM nutrition_weight_history
                ORDER BY recorded_at DESC, rowid DESC
                LIMIT 30
            )
            ORDER BY recorded_at ASC, rowid ASC
            """
        ).fetchall()
    history = [
        {"recorded_at": str(item["recorded_at"]), "weight_kg": float(item["weight_kg"])}
        for item in history_rows
    ]
    if row is None:
        return {
            "age": None,
            "dob": "",
            "gender": "",
            "height_cm": None,
            "weight_kg": None,
            "last_updated": "",
            "weight_history": history,
        }
    return {
        "age": _age_from_dob(row["dob"]) if row["dob"] else (int(row["age"]) if row["age"] is not None else None),
        "dob": str(row["dob"] or ""),
        "gender": str(row["gender"] or ""),
        "height_cm": float(row["height_cm"]) if row["height_cm"] is not None else None,
        "weight_kg": float(row["weight_kg"]) if row["weight_kg"] is not None else None,
        "last_updated": str(row["last_updated"] or ""),
        "weight_history": history,
    }


def _weight_changed(existing: sqlite3.Row | None, weight_kg: float | None) -> bool:
    if weight_kg is None:
        return False
    old = float(existing["weight_kg"]) if existing is not None and existing["weight_kg"] is not None else None
    return old != weight_kg


def _normalize_weight_history(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    clean: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        weight_raw = row.get("weight_kg")
        recorded_raw = str(row.get("recorded_at") or "").strip()
        if weight_raw in (None, "") and not recorded_raw:
            continue
        if weight_raw in (None, ""):
            raise ValueError(f"Weight history row {idx} requires weight.")
        weight = float(weight_raw)
        if weight <= 0:
            raise ValueError(f"Weight history row {idx} weight must be greater than zero.")
        if not recorded_raw:
            recorded_raw = datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            datetime.strptime(recorded_raw, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"Weight history row {idx} update date must use YYYY-MM-DD HH:MM:SS.") from exc
        clean.append({"recorded_at": recorded_raw, "weight_kg": weight})
    return clean


def _age_from_dob(dob: Any) -> int | None:
    text = str(dob or "").strip()
    if not text:
        return None
    try:
        born = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("DOB must use YYYY-MM-DD.") from exc
    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    if born > today:
        raise ValueError("DOB cannot be in the future.")
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def save_nutrition_profile(
    profile: dict[str, Any],
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    dob = str(profile.get("dob") or "").strip() if isinstance(profile, dict) else ""
    age_raw = profile.get("age") if isinstance(profile, dict) else None
    gender = str(profile.get("gender") or "").strip() if isinstance(profile, dict) else ""
    height_raw = profile.get("height_cm") if isinstance(profile, dict) else None
    weight_raw = profile.get("weight_kg") if isinstance(profile, dict) else None
    history = _normalize_weight_history(profile.get("weight_history") if isinstance(profile, dict) else None)
    if history:
        weight_raw = history[-1]["weight_kg"]

    age = _age_from_dob(dob) if dob else (None if age_raw in (None, "") else int(age_raw))
    height_cm = None if height_raw in (None, "") else float(height_raw)
    weight_kg = None if weight_raw in (None, "") else float(weight_raw)
    if age is not None and age < 0:
        raise ValueError("年齡 must be zero or greater.")
    if gender and gender not in {"male", "female"}:
        raise ValueError("性別 must be male or female.")
    if height_cm is not None and height_cm <= 0:
        raise ValueError("身高 must be greater than zero.")
    if weight_kg is not None and weight_kg <= 0:
        raise ValueError("體重 must be greater than zero.")

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        existing = conn.execute(
            """
            SELECT dob, age, gender, height_cm, weight_kg, last_updated
            FROM nutrition_profile
            WHERE profile_key = 'current'
            """
        ).fetchone()
        weight_changed = _weight_changed(existing, weight_kg)
        last_updated = (
            history[-1]["recorded_at"]
            if history
            else (datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d %H:%M:%S") if weight_changed else (str(existing["last_updated"] or "") if existing is not None else ""))
        )
        conn.execute(
            """
            INSERT INTO nutrition_profile(profile_key, dob, age, gender, height_cm, weight_kg, last_updated)
            VALUES ('current', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_key) DO UPDATE SET
                dob = excluded.dob,
                age = excluded.age,
                gender = excluded.gender,
                height_cm = excluded.height_cm,
                weight_kg = excluded.weight_kg,
                last_updated = excluded.last_updated
            """,
            (dob, age, gender, height_cm, weight_kg, last_updated),
        )
        if history:
            conn.execute("DELETE FROM nutrition_weight_history")
            conn.executemany(
                """
                INSERT INTO nutrition_weight_history(recorded_at, weight_kg)
                VALUES (:recorded_at, :weight_kg)
                """,
                history,
            )
        elif weight_changed:
            conn.execute(
                """
                INSERT INTO nutrition_weight_history(recorded_at, weight_kg)
                VALUES (?, ?)
                """,
                (last_updated, weight_kg),
            )
        conn.commit()
    return load_nutrition_profile(settings)


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
