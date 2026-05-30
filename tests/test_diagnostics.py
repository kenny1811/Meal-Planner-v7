import os
import tempfile
import unittest

from meal_planner.diagnostics import run_integrity_checks
from meal_planner.maintenance_db import save_sheet_rows
from meal_planner.settings import clear_settings_cache, get_settings


class DiagnosticsTests(unittest.TestCase):
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

    def test_reports_missing_shift_time_and_schedule_grid_for_roster_codes(self):
        settings = get_settings()
        save_sheet_rows("roster", [["2026年6月 1 A1 2 B2"]], settings)
        save_sheet_rows("meal_times", [["更碼", "早餐"], ["其他", "08:00"]], settings)
        save_sheet_rows("payroll_times", [["更碼", "開始時間", "結束時間"], ["A1", "09:00", "18:00"]], settings)
        save_sheet_rows("schedule_grid", [["更碼", "時間", "內容", "時長"], ["A1", "12:00", "飯", "45"]], settings)

        data = run_integrity_checks(settings)
        by_code = {row["code"]: row for row in data["code_coverage"]}

        self.assertTrue(by_code["A1"]["payroll_time"])
        self.assertTrue(by_code["A1"]["schedule_grid"])
        self.assertFalse(by_code["B2"]["payroll_time"])
        self.assertFalse(by_code["B2"]["schedule_grid"])
        self.assertGreaterEqual(data["summary"]["missing_payroll_time_codes"], 1)
        self.assertGreaterEqual(data["summary"]["missing_schedule_grid_codes"], 1)

    def test_non_work_codes_do_not_require_shift_time_or_schedule_grid(self):
        settings = get_settings()
        save_sheet_rows("roster", [["2026年6月 1 AL01 2 SB 3 WL01 4 A1"]], settings)
        save_sheet_rows("meal_times", [["更碼", "早餐"], ["AL*", "08:00"], ["SB", "08:00"], ["WL*", "08:00"], ["其他", "08:00"]], settings)
        save_sheet_rows("payroll_times", [["更碼", "開始時間", "結束時間"], ["A1", "09:00", "18:00"]], settings)
        save_sheet_rows("schedule_grid", [["更碼", "時間", "內容", "時長"], ["A1", "12:00", "飯", "45"]], settings)

        data = run_integrity_checks(settings)
        by_code = {row["code"]: row for row in data["code_coverage"]}

        self.assertFalse(by_code["AL01"]["requires_shift_schedule"])
        self.assertFalse(by_code["SB"]["requires_shift_schedule"])
        self.assertFalse(by_code["WL01"]["requires_shift_schedule"])
        self.assertEqual(data["summary"]["missing_payroll_time_codes"], 0)
        self.assertEqual(data["summary"]["missing_schedule_grid_codes"], 0)


if __name__ == "__main__":
    unittest.main()
