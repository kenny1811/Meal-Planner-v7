import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from meal_planner.indicators import NUTRIENT_HEADERS as NUTRIENT_HEADER_BY_KEY
from meal_planner.nutrition_db import (
    NutritionDatabaseError,
    database_path,
    load_catalog_entries,
    load_nutrition_profile,
    load_target_settings,
    load_target_rows,
    save_catalog_entries,
    save_nutrition_profile,
    save_target_settings,
    save_target_rows,
)
from meal_planner.settings import clear_settings_cache, get_settings


def _seed_catalog(settings):
    """種一行「蘋果」入 SQLite——SQLite 係唯一來源，冇 workbook 呢回事。"""
    nutrients = {key: float(100 + idx) for idx, key in enumerate(NUTRIENT_HEADER_BY_KEY)}
    return save_catalog_entries(
        [
            {
                "paused": False,
                "category": "水果",
                "name": "蘋果",
                "min_g": "50",
                "max_g": "200",
                "daymax_g": "300",
                "nutrients": nutrients,
            }
        ],
        settings,
    )


def _seed_targets(settings):
    headers = list(NUTRIENT_HEADER_BY_KEY.values())
    workday = ["100-200", "10-20", "20-30", "< 5", "< 10", "< 100", "> 300", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"]
    nonworkday = ["90-180", "9-18", "18-28", "< 4", "< 9", "< 90", "> 280", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"]
    return save_target_rows(headers, workday, nonworkday, settings)


class NutritionDatabaseTests(unittest.TestCase):
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

    def test_empty_catalog_raises_instead_of_falling_back(self):
        settings = get_settings()

        with self.assertRaises(NutritionDatabaseError):
            load_catalog_entries(settings)

    def test_catalog_round_trips_through_sqlite(self):
        settings = get_settings()
        _seed_catalog(settings)

        entries = load_catalog_entries(settings)

        self.assertTrue(database_path(settings).is_file())
        self.assertEqual(entries[0].name, "蘋果")
        self.assertEqual(entries[0].nutrients["kcal"], 100.0)

    def test_save_catalog_replaces_rows_and_assigns_new_row_index(self):
        settings = get_settings()
        original = _seed_catalog(settings)[0]

        saved = save_catalog_entries(
            [
                {
                    "row_index": original.row_index,
                    "paused": True,
                    "category": "水果",
                    "name": "青蘋果",
                    "min_g": "40",
                    "max_g": "180",
                    "daymax_g": "",
                    "nutrients": {key: original.nutrients[key] for key in original.nutrients},
                },
                {
                    "category": "飲品",
                    "name": "豆奶",
                    "min_g": "",
                    "max_g": "",
                    "daymax_g": "300",
                    "nutrients": {"kcal": "50", "protein_g": "4"},
                },
            ],
            settings,
        )

        self.assertEqual([entry.name for entry in saved], ["青蘋果", "豆奶"])
        self.assertTrue(saved[0].paused)
        self.assertEqual(saved[0].min_g, 40.0)
        self.assertIsNone(saved[0].daymax_g)
        self.assertEqual(saved[1].row_index, 3)
        self.assertEqual(saved[1].nutrients["kcal"], 50.0)
        self.assertEqual(saved[1].nutrients["fat_trans_g"], 0.0)
        with self.assertRaises(ValueError):
            save_catalog_entries([{"category": "Missing name"}], settings)

    def test_empty_targets_raise_instead_of_falling_back(self):
        settings = get_settings()

        with self.assertRaises(NutritionDatabaseError):
            load_target_rows(settings)

    def test_targets_round_trip_through_sqlite(self):
        settings = get_settings()
        _seed_targets(settings)

        headers, workday, nonworkday = load_target_rows(settings)

        self.assertEqual(headers[0], NUTRIENT_HEADER_BY_KEY["kcal"])
        self.assertEqual(workday[0], "100-200")
        self.assertEqual(nonworkday[0], "90-180")

    def test_save_targets_replaces_sqlite_rows_and_validates_indicator_text(self):
        settings = get_settings()
        headers = list(NUTRIENT_HEADER_BY_KEY.values())
        workday = ["100-200", "10-20", "20-30", "< 5", "< 10", "< 100", "> 300", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"]
        nonworkday = ["90-180", "9-18", "18-28", "< 4", "< 9", "< 90", "> 280", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"]

        _, saved_workday, saved_nonworkday = save_target_rows(headers, workday, nonworkday, settings)

        self.assertEqual(saved_workday, workday)
        self.assertEqual(saved_nonworkday, nonworkday)
        with self.assertRaises(ValueError):
            save_target_rows(headers, [""] + workday[1:], nonworkday, settings)

    def test_target_settings_round_trips_through_sqlite(self):
        settings = get_settings()

        before = load_target_settings(settings)
        saved = save_target_settings(
            {
                "workday": {"activity_factor": 1.42, "calorie_range_band": 60, "sodium_mg": 1900},
                "nonworkday": {"activity_factor": 1.18, "sugar_g": 45, "fat_sat_pct": 8},
            },
            settings,
        )
        after = load_target_settings(settings)

        self.assertEqual(before["workday"]["activity_factor"], 1.35)
        self.assertEqual(saved["workday"]["activity_factor"], 1.42)
        self.assertEqual(saved["workday"]["calorie_range_band"], 60)
        self.assertEqual(saved["workday"]["sodium_mg"], 1900)
        self.assertEqual(saved["nonworkday"]["activity_factor"], 1.18)
        self.assertEqual(saved["nonworkday"]["sugar_g"], 45)
        self.assertEqual(saved["nonworkday"]["fat_sat_pct"], 8)
        self.assertEqual(after, saved)
        with self.assertRaises(ValueError):
            save_target_settings({"workday": {"activity_factor": -1}}, settings)

    def test_nutrition_profile_round_trips_through_sqlite(self):
        settings = get_settings()
        today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
        dob_42 = f"{today.year - 42:04d}-01-01"
        dob_43 = f"{today.year - 43:04d}-01-01"

        before = load_nutrition_profile(settings)
        saved = save_nutrition_profile(
            {
                "dob": dob_42,
                "gender": "female",
                "height_cm": 165.5,
                "monthly_weight_change_kg": -0.5,
                "weight_history": [{"weight_kg": 58.2, "recorded_at": "2026-06-20 10:00:00"}],
            },
            settings,
        )
        same_weight = save_nutrition_profile(
            {
                "dob": dob_42,
                "gender": "female",
                "height_cm": 165.5,
                "monthly_weight_change_kg": -0.5,
                "weight_history": [{"weight_kg": 58.2, "recorded_at": "2026-06-20 10:00:00"}],
            },
            settings,
        )
        age_changed = save_nutrition_profile(
            {
                "dob": dob_43,
                "gender": "female",
                "height_cm": 165.5,
                "monthly_weight_change_kg": -0.25,
                "weight_history": [{"weight_kg": 58.2, "recorded_at": "2026-06-20 10:00:00"}],
            },
            settings,
        )
        changed_weight = save_nutrition_profile(
            {
                "dob": dob_43,
                "gender": "female",
                "height_cm": 165.5,
                "monthly_weight_change_kg": -0.25,
                "weight_history": [
                    {"weight_kg": 58.2, "recorded_at": "2026-06-20 10:00:00"},
                    {"weight_kg": 59.1, "recorded_at": "2026-06-21 10:00:00"},
                ],
            },
            settings,
        )
        after = load_nutrition_profile(settings)

        self.assertEqual(
            before,
            {"age": None, "dob": "", "gender": "", "height_cm": None, "weight_kg": None, "monthly_weight_change_kg": 0.0, "last_updated": "", "weight_history": []},
        )
        self.assertEqual(saved["dob"], dob_42)
        self.assertEqual(saved["age"], 42)
        self.assertEqual(saved["gender"], "female")
        self.assertEqual(saved["height_cm"], 165.5)
        self.assertEqual(saved["weight_kg"], 58.2)
        self.assertEqual(saved["monthly_weight_change_kg"], -0.5)
        self.assertEqual(saved["last_updated"], "2026-06-20 10:00:00")
        self.assertEqual([item["weight_kg"] for item in saved["weight_history"]], [58.2])
        self.assertEqual([item["weight_kg"] for item in same_weight["weight_history"]], [58.2])
        self.assertEqual(age_changed["dob"], dob_43)
        self.assertEqual(age_changed["age"], 43)
        self.assertEqual(age_changed["monthly_weight_change_kg"], -0.25)
        self.assertEqual([item["weight_kg"] for item in age_changed["weight_history"]], [58.2])
        self.assertEqual(changed_weight["weight_kg"], 59.1)
        self.assertEqual(changed_weight["last_updated"], "2026-06-21 10:00:00")
        self.assertEqual([item["weight_kg"] for item in changed_weight["weight_history"]], [58.2, 59.1])
        self.assertEqual(after, changed_weight)
        with self.assertRaises(ValueError):
            save_nutrition_profile({"gender": "unknown"}, settings)


if __name__ == "__main__":
    unittest.main()
