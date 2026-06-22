import unittest
from datetime import date
from unittest.mock import patch

from meal_planner.alarm_plan import build_daily_alarm_plan
from meal_planner.settings import get_settings


class AlarmPlanTests(unittest.TestCase):
    def test_builds_daily_alarms_and_cleanup_from_roster_and_schedule_grid(self):
        sheets = {
            "roster": {"rows": [["2026年6月 1 EleC1"]]},
            "schedule_grid": {
                "rows": [
                    ["更碼", "時間", "內容", "時長"],
                    ["EleC1", "09:00", "報開工", ""],
                    ["EleC1", "13:00", "飯", "45"],
                    ["EleC1", "18:00", "報收工", ""],
                ]
            },
            "overtime": {"rows": [["日期", "開工", "收工"]]},
        }

        with patch("meal_planner.alarm_plan.load_sheet_rows", side_effect=lambda key, settings: sheets[key]):
            plan = build_daily_alarm_plan(date(2026, 6, 1), get_settings())

        self.assertEqual(plan["roster_code"], "EleC1")
        self.assertEqual([x["label"] for x in plan["alarms"]], ["報開工", "飯", "報收工"])
        self.assertTrue(plan["alarms"][0]["trigger_at"].startswith("2026-06-01T09:00:00"))
        self.assertTrue(plan["cleanup_at"].startswith("2026-06-01T20:00:00"))

    def test_overnight_shift_rolls_after_midnight_times_to_next_day(self):
        sheets = {
            "roster": {"rows": [["2026年6月 1 Night"]]},
            "schedule_grid": {
                "rows": [
                    ["更碼", "時間", "內容", "時長"],
                    ["Night", "22:00", "報開工", ""],
                    ["Night", "01:00", "飯", "45"],
                    ["Night", "06:00", "報收工", ""],
                ]
            },
            "overtime": {"rows": [["日期", "開工", "收工"]]},
        }

        with patch("meal_planner.alarm_plan.load_sheet_rows", side_effect=lambda key, settings: sheets[key]):
            plan = build_daily_alarm_plan(date(2026, 6, 1), get_settings())

        self.assertTrue(plan["alarms"][1]["trigger_at"].startswith("2026-06-02T01:00:00"))
        self.assertTrue(plan["cleanup_at"].startswith("2026-06-02T08:00:00"))

    def test_non_workday_returns_no_alarms(self):
        sheets = {
            "roster": {"rows": [["2026年6月 1 SB"]]},
            "schedule_grid": {"rows": []},
            "overtime": {"rows": []},
        }

        with patch("meal_planner.alarm_plan.load_sheet_rows", side_effect=lambda key, settings: sheets[key]):
            plan = build_daily_alarm_plan(date(2026, 6, 1), get_settings())

        self.assertFalse(plan["is_work_day"])
        self.assertEqual(plan["alarms"], [])


if __name__ == "__main__":
    unittest.main()
