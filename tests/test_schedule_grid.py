import unittest
import os
import tempfile
from datetime import date, time

from fastapi import HTTPException

from meal_planner.app import (
    _apply_schedule_grid_xml_metadata,
    _build_schedule_grid_all_variants_export,
    _extract_xml_texts,
    _merge_schedule_grid_rows_for_import,
    _parse_schedule_grid_texts,
    _rows_for_dates,
    _schedule_grid_xml_metadata,
)
from meal_planner.maintenance_db import save_sheet_rows
from meal_planner.schedule_grid import ScheduleRow, grid_row_matches_roster, load_schedule_rows_from_rows, rows_for_roster
from meal_planner.settings import clear_settings_cache, get_settings


class ScheduleGridTests(unittest.TestCase):
    def test_rows_for_roster_uses_latest_effective_version_for_day(self):
        rows = [
            ScheduleRow("EleC1", time(12, 0), "飯", 45),
            ScheduleRow("EleC1", time(13, 0), "飯", 45, effective_from=date(2026, 6, 1)),
            ScheduleRow("EleC1", time(14, 0), "飯", 45, effective_from=date(2026, 7, 1)),
        ]

        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 5, 31))[0].t, time(12, 0))
        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 6, 1))[0].t, time(13, 0))
        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 7, 2))[0].t, time(14, 0))

    def test_load_schedule_rows_from_rows_reads_optional_effective_date(self):
        rows = load_schedule_rows_from_rows(
            [
                ["更碼", "時間", "內容", "時長", "生效日期"],
                ["EleC1", "13:00", "飯", "45", "2026-06-01"],
            ]
        )

        self.assertEqual(rows[0].code, "EleC1")
        self.assertEqual(rows[0].t, time(13, 0))
        self.assertEqual(rows[0].duration_min, 45)
        self.assertEqual(rows[0].effective_from, date(2026, 6, 1))

    def test_grid_row_matches_roster_ignores_case_for_multi_word_codes(self):
        self.assertTrue(grid_row_matches_roster("Lecole Event", "Lecole event"))

    def test_all_variants_requires_exact_current_roster_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_root = os.environ.get("MENU_PROJECT_ROOT")
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            try:
                settings = get_settings()
                save_sheet_rows(
                    "roster",
                    [["2026年6月 18 Lecole Event"]],
                    settings,
                )
                save_sheet_rows(
                    "schedule_grid",
                    [
                        ["更碼", "時間", "內容", "時長", "生效日期"],
                        ["EleA", "09:00", "報開工", "60", "2026-06-01"],
                        ["Lecole event", "09:50", "報開工", "10", "2026-06-17"],
                    ],
                    settings,
                )

                with self.assertRaises(HTTPException) as ctx:
                    _build_schedule_grid_all_variants_export()
            finally:
                if old_root is None:
                    os.environ.pop("MENU_PROJECT_ROOT", None)
                else:
                    os.environ["MENU_PROJECT_ROOT"] = old_root
                clear_settings_cache()

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "搵唔到 Lecole Event 行位表")

    def test_phone_import_replaces_only_imported_code_for_effective_date(self):
        existing = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["Lecole", "09:00", "報開工", "60", "2026-06-17"],
            ["Lecole event", "12:00", "活動", "45", "2026-06-17"],
            ["PenBM", "10:00", "報開工", "75", "2026-06-17"],
        ]
        imported = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["PenBM", "10:20", "現場改", "10", "2026-06-17"],
        ]

        merged = _merge_schedule_grid_rows_for_import(
            existing,
            imported,
            {"2026-06-17"},
            {"PenBM"},
        )

        self.assertIn(existing[1], merged)
        self.assertIn(existing[2], merged)
        self.assertNotIn(existing[3], merged)
        self.assertIn(imported[1], merged)
        self.assertEqual(len(_rows_for_dates(existing, {"2026-06-17"}, {"PenBM"})), 1)

    def test_phone_import_without_codes_does_not_replace_entire_effective_date(self):
        existing = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["Lecole event", "12:00", "活動", "45", "2026-06-17"],
            ["PenBM", "10:00", "報開工", "75", "2026-06-17"],
        ]
        imported = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["", "10:20", "現場改", "10", "2026-06-17"],
        ]

        merged = _merge_schedule_grid_rows_for_import(
            existing,
            imported,
            {"2026-06-17"},
            set(),
        )

        self.assertIn(existing[1], merged)
        self.assertIn(existing[2], merged)
        self.assertIn(imported[1], merged)
        self.assertEqual(_rows_for_dates(existing, {"2026-06-17"}, set()), [])

    def test_phone_xml_root_roster_code_overrides_display_weekday_header(self):
        xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<schedule_grid effective_date="2026-06-17" roster_code="PenBM">
  <section>17/06/2026 Wed PenBM</section>
  <alarm>
    <time>10:20</time>
    <content>報開工 10</content>
  </alarm>
</schedule_grid>
""".encode("utf-8")

        effective_version, roster_code = _schedule_grid_xml_metadata(xml)
        rows = _parse_schedule_grid_texts(_extract_xml_texts(xml))[0]
        rows = _apply_schedule_grid_xml_metadata(
            rows,
            effective_version=effective_version,
            roster_code=roster_code,
        )

        self.assertEqual(rows[1][0], "PenBM")
        self.assertEqual(rows[1][4], "2026-06-17")


if __name__ == "__main__":
    unittest.main()
