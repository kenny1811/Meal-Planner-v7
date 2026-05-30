"""SQLite bootstrap and reads for workbook-backed planning reference tables."""

from __future__ import annotations

from contextlib import closing
from datetime import time
import sqlite3
from typing import Any

from openpyxl.workbook.workbook import Workbook

from meal_planner.indicators import NUTRIENT_KEYS
from meal_planner.settings import AppSettings, get_settings


class ReferenceDatabaseError(RuntimeError):
    """Planning reference data is unavailable and cannot be bootstrapped."""


def _connect(settings: AppSettings) -> sqlite3.Connection:
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reference_meal_time_rules (
            row_index INTEGER PRIMARY KEY,
            code_pattern TEXT NOT NULL,
            breakfast TEXT,
            lunch TEXT,
            snack TEXT,
            dinner TEXT
        );

        CREATE TABLE IF NOT EXISTS reference_meal_patterns (
            meal TEXT PRIMARY KEY,
            pattern TEXT
        );

        CREATE TABLE IF NOT EXISTS reference_restaurant_rows (
            row_index INTEGER PRIMARY KEY,
            keyword TEXT NOT NULL,
            store TEXT,
            hours TEXT,
            choice TEXT,
            address TEXT,
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

        CREATE TABLE IF NOT EXISTS reference_schedule_rows (
            row_index INTEGER PRIMARY KEY,
            code TEXT NOT NULL,
            time_text TEXT,
            content TEXT NOT NULL,
            duration_min INTEGER
        );
        """
    )
    conn.commit()


def _has_rows(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None


def _time_text(value: time | None) -> str | None:
    return value.isoformat() if value is not None else None


def _read_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def _seed_reference_tables(conn: sqlite3.Connection, settings: AppSettings, wb: Workbook) -> None:
    from meal_planner.excel_io import get_sheet
    from meal_planner.meal_schedule import (
        load_meal_patterns_table,
        load_meal_time_rules,
        load_restaurant_rows,
    )
    from meal_planner.schedule_grid import load_schedule_rows

    rules = load_meal_time_rules(get_sheet(wb, settings.sheets.meal_times))
    patterns = load_meal_patterns_table(get_sheet(wb, settings.sheets.meal_times))
    restaurants = load_restaurant_rows(get_sheet(wb, settings.sheets.restaurant))
    schedule_rows = load_schedule_rows(get_sheet(wb, settings.sheets.schedule_grid))

    conn.executemany(
        """
        INSERT INTO reference_meal_time_rules(
            row_index, code_pattern, breakfast, lunch, snack, dinner
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                rule.row_index,
                rule.code_pattern,
                rule.breakfast,
                rule.lunch,
                rule.snack,
                rule.dinner,
            )
            for rule in rules
        ],
    )
    conn.executemany(
        "INSERT INTO reference_meal_patterns(meal, pattern) VALUES (?, ?)",
        [(meal, pattern) for meal, pattern in patterns.items()],
    )
    conn.executemany(
        """
        INSERT INTO reference_restaurant_rows(
            row_index, keyword, store, hours, choice, address,
            kcal, protein_g, carb_g, sugar_g, cholesterol_mg,
            sodium_mg, calcium_mg, fat_total_g, fat_sat_g, fat_trans_g
        ) VALUES (
            :row, :keyword, :store, :hours, :choice, :address,
            :kcal, :protein_g, :carb_g, :sugar_g, :cholesterol_mg,
            :sodium_mg, :calcium_mg, :fat_total_g, :fat_sat_g, :fat_trans_g
        )
        """,
        [
            {
                **{key: float(row["nutrients"].get(key, 0.0) or 0.0) for key in NUTRIENT_KEYS},
                **{key: row.get(key) for key in ("row", "keyword", "store", "hours", "choice", "address")},
            }
            for row in restaurants
        ],
    )
    conn.executemany(
        """
        INSERT INTO reference_schedule_rows(
            row_index, code, time_text, content, duration_min
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (idx, row.code, _time_text(row.t), row.content, row.duration_min)
            for idx, row in enumerate(schedule_rows, start=1)
        ],
    )


def bootstrap_from_workbook(settings: AppSettings, wb: Workbook) -> None:
    """Seed all planning reference tables once from the legacy workbook."""
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        table_names = (
            "reference_meal_time_rules",
            "reference_meal_patterns",
            "reference_restaurant_rows",
            "reference_schedule_rows",
        )
        if all(_has_rows(conn, table) for table in table_names):
            return

        try:
            for table in table_names:
                conn.execute(f"DELETE FROM {table}")
            _seed_reference_tables(conn, settings, wb)
        except Exception as exc:
            conn.rollback()
            raise ReferenceDatabaseError(
                "SQLite planning reference data is empty and Excel bootstrap failed."
            ) from exc
        conn.commit()


def load_planning_references(
    settings: AppSettings | None = None,
    wb: Workbook | None = None,
) -> tuple[list[Any], dict[str, str | None], list[dict[str, Any]], list[Any]]:
    """Load meal-time, meal-pattern, restaurant, and schedule reference rows."""
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        has_all_tables = all(
            _has_rows(conn, table)
            for table in (
                "reference_meal_time_rules",
                "reference_meal_patterns",
                "reference_restaurant_rows",
                "reference_schedule_rows",
            )
        )
    if not has_all_tables:
        if wb is None:
            raise ReferenceDatabaseError(
                "SQLite planning reference data is empty and no workbook was provided."
            )
        bootstrap_from_workbook(settings, wb)

    from meal_planner.meal_schedule import MEAL_LABELS, MealTimeRule
    from meal_planner.schedule_grid import ScheduleRow

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        rules = [
            MealTimeRule(
                row_index=int(row["row_index"]),
                code_pattern=str(row["code_pattern"]),
                breakfast=row["breakfast"],
                lunch=row["lunch"],
                snack=row["snack"],
                dinner=row["dinner"],
            )
            for row in conn.execute(
                "SELECT * FROM reference_meal_time_rules ORDER BY row_index"
            ).fetchall()
        ]
        pattern_rows = conn.execute(
            "SELECT meal, pattern FROM reference_meal_patterns"
        ).fetchall()
        restaurant_rows = conn.execute(
            "SELECT * FROM reference_restaurant_rows ORDER BY row_index"
        ).fetchall()
        schedule_rows = conn.execute(
            "SELECT * FROM reference_schedule_rows ORDER BY row_index"
        ).fetchall()

    patterns = {meal: None for meal in MEAL_LABELS}
    patterns.update({str(row["meal"]): row["pattern"] for row in pattern_rows})
    restaurants = [
        {
            "row": int(row["row_index"]),
            "keyword": str(row["keyword"]),
            "store": row["store"],
            "hours": row["hours"],
            "choice": row["choice"],
            "address": row["address"],
            "nutrients": {key: float(row[key] or 0.0) for key in NUTRIENT_KEYS},
        }
        for row in restaurant_rows
    ]
    schedule = [
        ScheduleRow(
            code=str(row["code"]),
            t=_read_time(row["time_text"]),
            content=str(row["content"]),
            duration_min=int(row["duration_min"]) if row["duration_min"] is not None else None,
        )
        for row in schedule_rows
    ]
    return rules, patterns, restaurants, schedule
