import os
import tempfile
import unittest

from meal_planner.maintenance_db import (
    MaintenanceDatabaseError,
    load_roster_code_definitions,
    load_sheet_rows,
    save_roster_code_definitions,
    save_sheet_rows,
)
from meal_planner.roster import load_roster_map
from meal_planner.settings import clear_settings_cache, get_settings


class MaintenanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = os.environ.get("MENU_PROJECT_ROOT")
        os.environ["MENU_PROJECT_ROOT"] = self.tmp.name
        clear_settings_cache()

    def tearDown(self):
        if self.old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = self.old_root
        clear_settings_cache()
        self.tmp.cleanup()

    def test_save_replaces_sheet_rows(self):
        settings = get_settings()

        result = save_sheet_rows("overtime", [["日期", "開工"], ["2026-05-23", "09:00"]], settings)
        loaded = load_sheet_rows("overtime", settings)

        self.assertEqual(result["row_count"], 2)
        self.assertEqual(loaded["display_name"], "加班表")
        self.assertEqual(loaded["rows"], [["日期", "開工"], ["2026-05-23", "09:00"]])

    def test_empty_sheet_raises_instead_of_returning_nothing(self):
        settings = get_settings()

        with self.assertRaises(MaintenanceDatabaseError):
            load_sheet_rows("public_holidays", settings)

    def test_defaulted_sheets_seed_themselves(self):
        settings = get_settings()

        wake = load_sheet_rows("wake_alarms", settings)
        doors = load_sheet_rows("mtr_doors", settings)

        self.assertEqual(wake["rows"][0], ["日期", "起身時間", "備註"])
        self.assertEqual(doors["rows"][0][0], "更碼")

    def test_roster_map_reads_maintenance_copy(self):
        settings = get_settings()
        save_sheet_rows(
            "roster",
            [
                ["2026年5月 1 SB"],
                ["2026年6月 1 VPP 2 WL21"],
            ],
            settings,
        )

        roster = load_roster_map(settings)

        self.assertEqual(roster[(2026, 6)].day_to_code, {1: "VPP", 2: "WL21"})

    def test_roster_map_raises_when_roster_sheet_is_empty(self):
        settings = get_settings()

        with self.assertRaises(MaintenanceDatabaseError):
            load_roster_map(settings)

    def test_save_roster_code_definitions_replaces_rows(self):
        settings = get_settings()

        saved = save_roster_code_definitions(
            [{"pattern": "AL*", "label": "Annual leave"}],
            settings,
        )

        self.assertEqual(saved, [{"pattern": "AL*", "label": "Annual leave", "sort_order": 1}])
        self.assertEqual(load_roster_code_definitions(settings), saved)


if __name__ == "__main__":
    unittest.main()
