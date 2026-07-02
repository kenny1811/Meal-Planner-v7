"""Planning input reads from editable SQLite maintenance sheets."""

from __future__ import annotations

from typing import Any

from meal_planner.settings import AppSettings, get_settings


class ReferenceDatabaseError(RuntimeError):
    """Planning maintenance data is unavailable or invalid."""


def load_planning_references(
    settings: AppSettings | None = None,
    wb: Any | None = None,
) -> tuple[list[Any], dict[str, str | None], list[dict[str, Any]], list[Any]]:
    """Load planning inputs from SQLite maintenance sheets only."""
    del wb
    settings = settings or get_settings()
    from meal_planner.maintenance_db import MaintenanceDatabaseError, load_sheet_rows
    from meal_planner.meal_schedule import (
        MEAL_LABELS,
        load_meal_patterns_table_from_rows,
        load_meal_time_rules_from_rows,
        load_restaurant_rows_from_rows,
    )
    from meal_planner.schedule_grid import load_schedule_rows_from_rows

    try:
        meal_times_sheet = load_sheet_rows("meal_times", settings)
        meal_patterns_sheet = load_sheet_rows("meal_patterns", settings)
        restaurant_sheet = load_sheet_rows("restaurant", settings)
        schedule_sheet = load_sheet_rows("schedule_grid", settings)
    except MaintenanceDatabaseError as exc:
        raise ReferenceDatabaseError(
            "Generate requires SQLite maintenance rows for 飯時表, Pattern, 餐廳選擇, and 行位表; Excel/reference fallback is disabled."
        ) from exc

    rules = load_meal_time_rules_from_rows(meal_times_sheet.get("rows", []))
    patterns = load_meal_patterns_table_from_rows(meal_patterns_sheet.get("rows", []))
    restaurants = load_restaurant_rows_from_rows(restaurant_sheet.get("rows", []))
    schedule = load_schedule_rows_from_rows(schedule_sheet.get("rows", []))

    missing: list[str] = []
    if not rules:
        missing.append("飯時表")
    if not any(patterns.get(meal) for meal in MEAL_LABELS):
        missing.append("Pattern")
    if not restaurants:
        missing.append("餐廳選擇")
    if not schedule:
        missing.append("行位表")
    if missing:
        raise ReferenceDatabaseError(
            "Generate requires current SQLite maintenance data; missing/invalid: " + ", ".join(missing)
        )
    return rules, patterns, restaurants, schedule
