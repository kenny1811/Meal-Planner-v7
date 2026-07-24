"""維護表（更表／飯時／行位表…）嘅 SQLite 儲存——SQLite 係唯一 source of truth。"""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, time
import json
import sqlite3
from typing import Any

from meal_planner.duty_scheduler import notify_change
from meal_planner.settings import AppSettings, get_settings


MAINTENANCE_SHEETS: tuple[tuple[str, str], ...] = (
    ("roster", "更表"),
    ("wake_alarms", "起身表"),
    ("overtime", "加班表"),
    ("payroll_times", "更時表"),
    ("public_holidays", "公眾假期"),
    ("medical_appointments", "醫療行程"),
    ("meal_times", "飯時表"),
    ("meal_patterns", "Pattern"),
    ("restaurant", "餐廳選擇"),
    ("schedule_grid", "行位表"),
    ("mtr_doors", "地鐵車門"),
)


# 地鐵車門：更碼對應由荃灣站上車嘅車卡/車門同轉車資料（門位留空待填）。
MTR_DOORS_DEFAULT_ROWS: list[list[str]] = [
    ["更碼", "目的地", "上車卡門", "轉車", "轉車卡門", "落車出口"],
    ["Ele*", "圓方（九龍站）", "", "荔景轉東涌綫（往香港）", "", "九龍站 圓方連接"],
    ["IFC*", "IFC（香港站）", "", "荔景轉東涌綫（往香港）", "", "香港站 IFC 連接"],
    ["Lecole", "", "", "直達", "", ""],
    ["Lecole Event", "", "", "直達", "", ""],
    ["Pen*", "半島酒店（尖沙咀）", "", "直達", "", "尖沙咀 E"],
    ["VLG", "利園（銅鑼灣）", "", "金鐘轉港島綫（往柴灣）", "", "銅鑼灣 F"],
    ["VOC", "海港城／海洋中心（尖沙咀）", "", "直達", "", "尖沙咀 A1"],
    ["VPP", "太古廣場（金鐘）", "", "直達", "", "金鐘 F"],
    ["TS*", "時代廣場（銅鑼灣）", "", "金鐘轉港島綫（往柴灣）", "", "銅鑼灣 A"],
]

class MaintenanceDatabaseError(RuntimeError):
    """Maintenance data is unavailable and cannot be bootstrapped."""


def _connect(settings: AppSettings) -> sqlite3.Connection:
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# Schema DDL 每個 process 每個 db 檔跑一次就夠——以前每次讀寫都重跑。
_SCHEMA_READY: set[str] = set()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    db_key = str(conn.execute("PRAGMA database_list").fetchone()["file"])
    if db_key in _SCHEMA_READY:
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS maintenance_sheets (
            sheet_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            source_sheet TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS maintenance_sheet_rows (
            sheet_key TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            cells_json TEXT NOT NULL,
            PRIMARY KEY (sheet_key, row_index),
            FOREIGN KEY (sheet_key) REFERENCES maintenance_sheets(sheet_key)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS roster_code_definitions (
            pattern TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            sort_order INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    _SCHEMA_READY.add(db_key)


def _sheet_name_for_key(settings: AppSettings, sheet_key: str) -> str:
    mapping = {
        "roster": settings.sheets.roster,
        "wake_alarms": "起身表",
        "overtime": settings.sheets.overtime,
        "payroll_times": settings.sheets.payroll_times,
        "public_holidays": settings.sheets.public_holidays,
        "medical_appointments": "醫療行程",
        "meal_times": settings.sheets.meal_times,
        "meal_patterns": settings.sheets.meal_times,
        "restaurant": settings.sheets.restaurant,
        "schedule_grid": settings.sheets.schedule_grid,
        "mtr_doors": "地鐵車門",
    }
    if sheet_key not in mapping:
        raise KeyError(sheet_key)
    return mapping[sheet_key]


def _display_name_for_key(sheet_key: str) -> str:
    for key, label in MAINTENANCE_SHEETS:
        if key == sheet_key:
            return label
    raise KeyError(sheet_key)


def _cell_to_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.time() == time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value


def _has_sheet_rows(conn: sqlite3.Connection, sheet_key: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM maintenance_sheet_rows WHERE sheet_key = ? LIMIT 1",
            (sheet_key,),
        ).fetchone()
        is not None
    )


def save_sheet_rows(
    sheet_key: str,
    rows: list[list[Any]],
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    display_name = _display_name_for_key(sheet_key)
    source_sheet = _sheet_name_for_key(settings, sheet_key)
    clean_rows = [list(row) if isinstance(row, list) else [] for row in rows]
    while clean_rows and not any(cell not in (None, "") for cell in clean_rows[-1]):
        clean_rows.pop()

    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO maintenance_sheets(
                sheet_key, display_name, source_sheet, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (sheet_key, display_name, source_sheet, now),
        )
        conn.execute("DELETE FROM maintenance_sheet_rows WHERE sheet_key = ?", (sheet_key,))
        conn.executemany(
            """
            INSERT INTO maintenance_sheet_rows(sheet_key, row_index, cells_json)
            VALUES (?, ?, ?)
            """,
            [
                (sheet_key, idx, json.dumps(row, ensure_ascii=False))
                for idx, row in enumerate(clean_rows, start=1)
            ],
        )
        conn.commit()
    # 更表/加班表/行位表等一改 → 即刻叫醒 duty scheduler 重新計劃。
    notify_change()
    return {"sheet_key": sheet_key, "updated_at": now, "row_count": len(clean_rows)}


def _has_roster_code_definitions(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM roster_code_definitions LIMIT 1").fetchone() is not None


def load_roster_code_definitions(settings: AppSettings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT pattern, label, sort_order
            FROM roster_code_definitions
            ORDER BY sort_order, pattern
            """
        ).fetchall()
    return [
        {
            "pattern": str(row["pattern"]),
            "label": str(row["label"]),
            "sort_order": int(row["sort_order"]),
        }
        for row in rows
    ]


def save_roster_code_definitions(
    rows: list[dict[str, Any]],
    settings: AppSettings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    clean_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            continue
        pattern = str(raw.get("pattern") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not pattern and not label:
            continue
        if not pattern or not label:
            raise ValueError(f"Roster code definition row {idx} requires Pattern and Definition.")
        if pattern in seen:
            raise ValueError(f"Roster code definition pattern is duplicated: {pattern}")
        seen.add(pattern)
        clean_rows.append({"pattern": pattern, "label": label, "sort_order": len(clean_rows) + 1})

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM roster_code_definitions")
        conn.executemany(
            """
            INSERT INTO roster_code_definitions(pattern, label, sort_order)
            VALUES (:pattern, :label, :sort_order)
            """,
            clean_rows,
        )
        conn.commit()
    return load_roster_code_definitions(settings)


def list_maintenance_sheets(settings: AppSettings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        meta = {
            str(row["sheet_key"]): row
            for row in conn.execute("SELECT * FROM maintenance_sheets").fetchall()
        }
        counts = {
            str(row["sheet_key"]): int(row["row_count"])
            for row in conn.execute(
                """
                SELECT sheet_key, COUNT(*) AS row_count
                FROM maintenance_sheet_rows
                GROUP BY sheet_key
                """
            ).fetchall()
        }
    out: list[dict[str, Any]] = []
    for sheet_key, display_name in MAINTENANCE_SHEETS:
        row = meta.get(sheet_key)
        out.append(
            {
                "sheet_key": sheet_key,
                "display_name": display_name,
                "source_sheet": _sheet_name_for_key(settings, sheet_key),
                "updated_at": row["updated_at"] if row else None,
                "row_count": counts.get(sheet_key, 0),
            }
        )
    return out


def load_sheet_rows(
    sheet_key: str,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()

    def _read(conn: sqlite3.Connection) -> tuple[Any, list[Any]]:
        meta = conn.execute(
            "SELECT * FROM maintenance_sheets WHERE sheet_key = ?",
            (sheet_key,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT row_index, cells_json
            FROM maintenance_sheet_rows
            WHERE sheet_key = ?
            ORDER BY row_index
            """,
            (sheet_key,),
        ).fetchall()
        return meta, rows

    with closing(_connect(settings)) as conn:
        _ensure_schema(conn)
        has_rows = _has_sheet_rows(conn, sheet_key)
        meta, rows = _read(conn) if has_rows else (None, [])
    if not has_rows:
        # 得呢兩張表有預設內容（純本地資料，唔會有其他來源）；其餘空表就係空表，要報出嚟。
        if sheet_key == "wake_alarms":
            save_sheet_rows(sheet_key, [["日期", "起身時間", "備註"]], settings)
        elif sheet_key == "mtr_doors":
            save_sheet_rows(sheet_key, [list(row) for row in MTR_DOORS_DEFAULT_ROWS], settings)
        else:
            raise MaintenanceDatabaseError(
                f"Maintenance sheet {_display_name_for_key(sheet_key)} is empty."
            )
        with closing(_connect(settings)) as conn:
            meta, rows = _read(conn)

    return {
        "sheet_key": sheet_key,
        "display_name": _display_name_for_key(sheet_key),
        "source_sheet": _sheet_name_for_key(settings, sheet_key),
        "updated_at": meta["updated_at"] if meta else None,
        "rows": [json.loads(row["cells_json"]) for row in rows],
    }
