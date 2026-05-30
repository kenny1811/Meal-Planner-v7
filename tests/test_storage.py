import json
import os
import tempfile
import unittest
from pathlib import Path

from meal_planner import storage
from meal_planner.settings import clear_settings_cache


class StorageTests(unittest.TestCase):
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

    @property
    def store_path(self) -> Path:
        return Path(self.tmp.name) / "plans_store.json"

    def test_save_plan_versions_caps_versions_and_writes_schema(self):
        for idx in range(storage.MAX_VERSIONS_PER_DATE + 3):
            storage.save_plan_versions([{"date": "2026-05-20", "meal_plan": {"idx": idx}}])

        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        versions = data["versions_by_date"]["2026-05-20"]

        self.assertEqual(data["schema_version"], storage.STORE_SCHEMA_VERSION)
        self.assertEqual(len(versions), storage.MAX_VERSIONS_PER_DATE)
        self.assertEqual(versions[-1]["day"]["meal_plan"]["idx"], storage.MAX_VERSIONS_PER_DATE + 2)

    def test_save_creates_limited_backups(self):
        for idx in range(storage.MAX_STORE_BACKUPS + 3):
            storage.save_memory_payload({"headers": [idx]})

        backups = sorted((Path(self.tmp.name) / ".plans_store_backups").glob("plans_store.*.json"))

        self.assertEqual(len(backups), storage.MAX_STORE_BACKUPS)

    def test_load_recovers_from_latest_valid_backup_when_main_file_is_corrupt(self):
        storage.save_plan_versions([{"date": "2026-05-20", "meal_plan": {"idx": 1}}])
        storage.save_plan_versions([{"date": "2026-05-21", "meal_plan": {"idx": 2}}])
        self.store_path.write_text("{bad json", encoding="utf-8")

        result = storage.load_latest_versions(["2026-05-20"])

        self.assertEqual(result["days"], [{"date": "2026-05-20", "meal_plan": {"idx": 1}}])

    def test_load_normalises_legacy_direct_day_versions(self):
        self.store_path.write_text(
            json.dumps(
                {
                    "versions_by_date": {
                        "2026-05-20": [
                            {"date": "2026-05-20", "meal_plan": {"idx": 1}},
                            {"timestamp": "kept", "day": {"date": "2026-05-20", "meal_plan": {"idx": 2}}},
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = storage.load_latest_versions(["2026-05-20"])

        self.assertEqual(result["days"], [{"date": "2026-05-20", "meal_plan": {"idx": 2}}])
        self.assertEqual(result["versions"]["2026-05-20"], ["kept"])

    def test_target_editor_layout_round_trips_with_ui_state(self):
        storage.save_target_editor_layout(840, {"kcal": 120, "protein_g": 96}, {"name": 240})

        width, columns, catalog_columns = storage.load_target_editor_layout()

        self.assertEqual(width, 840.0)
        self.assertEqual(columns, {"kcal": 120.0, "protein_g": 96.0})
        self.assertEqual(catalog_columns, {"name": 240.0})

    def test_form_column_widths_round_trip(self):
        storage.save_form_column_widths({"detail_code_pattern": 140, "maint_roster_text": 760})

        self.assertEqual(
            storage.load_form_column_widths(),
            {"detail_code_pattern": 140.0, "maint_roster_text": 760.0},
        )


if __name__ == "__main__":
    unittest.main()
