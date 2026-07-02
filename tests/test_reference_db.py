import os
import tempfile
import unittest
from datetime import time

from meal_planner.nutrition_catalog import NUTRIENT_HEADER_BY_KEY
from meal_planner.reference_db import ReferenceDatabaseError, load_planning_references
from meal_planner.maintenance_db import save_sheet_rows
from meal_planner.settings import clear_settings_cache, get_settings


def _save_planning_maintenance(settings, *, meal_choice="餐", store="店", schedule_time="12:30", breakfast="開工前 2 小時"):
    nutrients = list(NUTRIENT_HEADER_BY_KEY.values())
    save_sheet_rows(
        "meal_times",
        [
            ["更碼", "早餐", "午餐", "小食", "晚餐"],
            ["EleM", breakfast, "跟行位表", "跟行位表", "收工後 1.5 小時"],
            ["其他", "08:00", "12:00", None, None],
        ],
        settings,
    )
    save_sheet_rows(
        "meal_patterns",
        [
            ["餐名", "Pattern"],
            ["早餐", "水果"],
            ["午餐", "菜+米"],
        ],
        settings,
    )
    save_sheet_rows(
        "restaurant",
        [
            ["更碼關鍵字", "舖頭 (Store)", "營業時間", "餐廳選擇", "地址", *nutrients],
            ["Ele*", store, "09:00-18:00", meal_choice, "地址", *range(10, 20)],
        ],
        settings,
    )
    save_sheet_rows(
        "schedule_grid",
        [
            ["更碼", "時間", "內容", "時長"],
            ["EleM", schedule_time, "飯", 45],
        ],
        settings,
    )


class ReferenceDatabaseTests(unittest.TestCase):
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

    def test_planning_references_load_from_maintenance_without_workbook(self):
        settings = get_settings()
        _save_planning_maintenance(settings)

        rules, patterns, restaurants, schedule = load_planning_references(settings)

        self.assertEqual(rules[0].code_pattern, "EleM")
        self.assertEqual(patterns["早餐"], "水果")
        self.assertEqual(restaurants[0]["store"], "店")
        self.assertEqual(restaurants[0]["nutrients"]["kcal"], 10.0)
        self.assertEqual(schedule[0].t, time(12, 30))

    def test_planning_references_reject_missing_maintenance_data(self):
        with self.assertRaisesRegex(ReferenceDatabaseError, "Excel/reference fallback is disabled"):
            load_planning_references(get_settings())

    def test_schedule_grid_maintenance_rows_are_current_source(self):
        settings = get_settings()
        _save_planning_maintenance(settings)
        save_sheet_rows(
            "schedule_grid",
            [
                ["更碼", "時間", "內容", "時長", "生效日期"],
                ["EleM", "13:10", "飯", "45", "2026-06-01"],
            ],
            settings,
        )

        _, _, _, schedule = load_planning_references(settings)

        self.assertEqual(schedule[0].t, time(13, 10))
        self.assertEqual(schedule[0].effective_from.isoformat(), "2026-06-01")

    def test_meal_times_maintenance_rows_are_current_source(self):
        settings = get_settings()
        _save_planning_maintenance(settings)
        save_sheet_rows(
            "meal_times",
            [
                ["更碼", "早餐", "午餐", "小食", "晚餐"],
                ["EleM", "07:00", "13:00", "", "20:00"],
                ["其他", "08:30", "12:30", "", ""],
            ],
            settings,
        )
        save_sheet_rows(
            "meal_patterns",
            [
                ["餐名", "Pattern"],
                ["早餐", "燕麥"],
                ["午餐", "米+魚"],
            ],
            settings,
        )

        rules, patterns, _, _ = load_planning_references(settings)

        self.assertEqual(rules[0].breakfast, "07:00")
        self.assertEqual(rules[0].lunch, "13:00")
        self.assertEqual(patterns["早餐"], "燕麥")
        self.assertEqual(patterns["午餐"], "米+魚")

    def test_restaurant_maintenance_rows_are_current_source(self):
        settings = get_settings()
        _save_planning_maintenance(settings)
        save_sheet_rows(
            "restaurant",
            [
                ["更碼關鍵字", "舖頭 (Store)", "營業時間", "餐廳選擇", "地址", *NUTRIENT_HEADER_BY_KEY.values()],
                ["Ele*", "新店", "10:00-19:00", "新餐", "新地址", *range(20, 30)],
            ],
            settings,
        )

        _, _, restaurants, _ = load_planning_references(settings)

        self.assertEqual(restaurants[0]["store"], "新店")
        self.assertEqual(restaurants[0]["choice"], "新餐")
        self.assertEqual(restaurants[0]["nutrients"]["kcal"], 20.0)


if __name__ == "__main__":
    unittest.main()
