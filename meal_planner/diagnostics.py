"""SQLite-backed data integrity checks for daily meal planning."""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import datetime
from typing import Any

from meal_planner.maintenance_db import MAINTENANCE_SHEETS, MaintenanceDatabaseError, list_maintenance_sheets, load_sheet_rows
from meal_planner.meal_schedule import roster_matches_rule
from meal_planner.roster import is_work_day, parse_roster_line
from meal_planner.schedule_grid import grid_row_matches_roster
from meal_planner.settings import AppSettings, get_settings


def _rows(sheet_key: str, settings: AppSettings) -> list[list[Any]]:
    try:
        data = load_sheet_rows(sheet_key, settings)
    except MaintenanceDatabaseError:
        return []
    rows = data.get("rows", [])
    return rows if isinstance(rows, list) else []


def _cell(row: list[Any], idx: int) -> str:
    if not isinstance(row, list) or idx >= len(row):
        return ""
    return str(row[idx] or "").strip().replace("\u00a0", " ")


def _patterns_from_first_col(rows: list[list[Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows[1:]:
        code = _cell(row, 0)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _matching_pattern(patterns: list[str], code: str) -> str | None:
    for pattern in patterns:
        if roster_matches_rule(pattern, code):
            return pattern
    for pattern in patterns:
        if pattern == "其他":
            return pattern
    return None


def _payroll_pattern(patterns: list[str], code: str) -> str | None:
    for pattern in patterns:
        if pattern.endswith("*") and code.startswith(pattern[:-1]):
            return pattern
        if pattern == code:
            return pattern
    return None


def _schedule_hits(rows: list[list[Any]], code: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for row in rows[1:]:
        pattern = _cell(row, 0)
        if not pattern:
            continue
        matched = grid_row_matches_roster(pattern, code) or (
            pattern.endswith("*") and code.startswith(pattern[:-1])
        )
        if matched and pattern not in seen:
            seen.add(pattern)
            hits.append(pattern)
    return hits


def run_integrity_checks(settings: AppSettings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    meta_by_key = {row["sheet_key"]: row for row in list_maintenance_sheets(settings)}
    tables = [
        {
            "sheet_key": key,
            "display_name": display_name,
            "row_count": int(meta_by_key.get(key, {}).get("row_count", 0) or 0),
            "updated_at": meta_by_key.get(key, {}).get("updated_at"),
        }
        for key, display_name in MAINTENANCE_SHEETS
    ]

    roster_rows = _rows("roster", settings)
    meal_time_rows = _rows("meal_times", settings)
    payroll_rows = _rows("payroll_times", settings)
    schedule_rows = _rows("schedule_grid", settings)
    target_rows = _rows("public_holidays", settings)

    issues: list[dict[str, Any]] = []
    for table in tables:
        if table["row_count"] == 0:
            issues.append(
                {
                    "severity": "error",
                    "area": "table",
                    "message": f"{table['display_name']} has no SQLite rows.",
                    "details": {"sheet_key": table["sheet_key"]},
                }
            )

    months: list[dict[str, Any]] = []
    code_days: Counter[str] = Counter()
    malformed_roster_rows: list[int] = []
    for idx, row in enumerate(roster_rows, start=1):
        text = _cell(row, 0)
        if not text:
            continue
        rm = parse_roster_line(text)
        if rm is None:
            malformed_roster_rows.append(idx)
            continue
        days_in_month = calendar.monthrange(rm.year, rm.month)[1]
        missing_days = [d for d in range(1, days_in_month + 1) if d not in rm.day_to_code]
        for code in rm.day_to_code.values():
            if code:
                code_days[code] += 1
        months.append(
            {
                "year": rm.year,
                "month": rm.month,
                "label": f"{rm.year}-{rm.month:02d}",
                "days_found": len(rm.day_to_code),
                "days_expected": days_in_month,
                "missing_days": missing_days,
            }
        )

    if malformed_roster_rows:
        issues.append(
            {
                "severity": "error",
                "area": "roster",
                "message": "Some roster rows could not be parsed.",
                "details": {"rows": malformed_roster_rows},
            }
        )
    for month in months:
        if month["missing_days"]:
            issues.append(
                {
                    "severity": "warning",
                    "area": "roster",
                    "message": f"{month['label']} roster is missing {len(month['missing_days'])} day(s).",
                    "details": {"month": month["label"], "missing_days": month["missing_days"]},
                }
            )

    meal_patterns = _patterns_from_first_col(meal_time_rows)
    payroll_patterns = _patterns_from_first_col(payroll_rows)
    code_coverage: list[dict[str, Any]] = []
    for code in sorted(code_days.keys()):
        requires_shift_schedule = is_work_day(code)
        meal_pattern = _matching_pattern(meal_patterns, code)
        payroll_pattern = _payroll_pattern(payroll_patterns, code)
        schedule_hits = _schedule_hits(schedule_rows, code)
        row = {
            "code": code,
            "days": int(code_days[code]),
            "is_work_day": requires_shift_schedule,
            "requires_shift_schedule": requires_shift_schedule,
            "meal_time": meal_pattern is not None,
            "meal_time_pattern": meal_pattern,
            "payroll_time": payroll_pattern is not None,
            "payroll_time_pattern": payroll_pattern,
            "schedule_grid": bool(schedule_hits),
            "schedule_grid_patterns": schedule_hits,
            "schedule_grid_row_count": sum(1 for r in schedule_rows[1:] if _cell(r, 0) in schedule_hits),
        }
        code_coverage.append(row)
        if not row["meal_time"]:
            issues.append(
                {
                    "severity": "error",
                    "area": "meal_times",
                    "message": f"Roster code {code} has no meal-time rule.",
                    "details": {"code": code},
                }
            )
        if requires_shift_schedule and not row["payroll_time"]:
            issues.append(
                {
                    "severity": "warning",
                    "area": "payroll_times",
                    "message": f"Roster code {code} has no shift-time row.",
                    "details": {"code": code},
                }
            )
        if requires_shift_schedule and not row["schedule_grid"]:
            issues.append(
                {
                    "severity": "warning",
                    "area": "schedule_grid",
                    "message": f"Roster code {code} has no schedule-grid row.",
                    "details": {"code": code},
                }
            )

    severity_rank = {"error": 2, "warning": 1, "info": 0}
    status = "ok"
    if any(issue["severity"] == "error" for issue in issues):
        status = "error"
    elif any(issue["severity"] == "warning" for issue in issues):
        status = "warning"

    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "sqlite",
        "summary": {
            "status": status,
            "issues": len(issues),
            "errors": sum(1 for issue in issues if issue["severity"] == "error"),
            "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
            "roster_months": len(months),
            "roster_codes": len(code_days),
            "missing_payroll_time_codes": sum(
                1 for row in code_coverage if row["requires_shift_schedule"] and not row["payroll_time"]
            ),
            "missing_schedule_grid_codes": sum(
                1 for row in code_coverage if row["requires_shift_schedule"] and not row["schedule_grid"]
            ),
        },
        "tables": tables,
        "roster": {
            "months": months,
            "unique_codes": sorted(code_days.keys()),
            "total_roster_days": sum(code_days.values()),
        },
        "code_coverage": code_coverage,
        "issues": sorted(
            issues,
            key=lambda item: (-severity_rank.get(item["severity"], 0), item["area"], item["message"]),
        ),
        "notes": {
            "public_holiday_rows": len(target_rows),
            "excel": "Excel is only used by explicit import or empty-SQLite bootstrap paths.",
        },
    }
