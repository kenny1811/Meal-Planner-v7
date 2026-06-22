import os
import sqlite3
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

    @property
    def db_path(self) -> Path:
        return Path(self.tmp.name) / "meal_planner.sqlite3"

    def test_save_plan_versions_caps_versions_and_writes_schema(self):
        for idx in range(storage.MAX_VERSIONS_PER_DATE + 3):
            storage.save_plan_versions([{"date": "2026-05-20", "meal_plan": {"idx": idx}}])

        result = storage.load_latest_versions(["2026-05-20"])

        self.assertEqual(len(result["versions"]["2026-05-20"]), storage.MAX_VERSIONS_PER_DATE)
        self.assertEqual(result["days"][0]["meal_plan"]["idx"], storage.MAX_VERSIONS_PER_DATE + 2)

    def test_ui_state_round_trips_through_sqlite_without_json_store(self):
        storage.save_column_widths({"date": 120})
        storage.save_sidebar_width(333)

        self.assertEqual(storage.load_column_widths(), {"date": 120.0})
        self.assertEqual(storage.load_sidebar_width(), 333.0)
        self.assertFalse(self.store_path.exists())

        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT value_json FROM ui_state WHERE state_key = 'current'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

    def test_existing_json_file_is_ignored_for_ui_state(self):
        self.store_path.write_text('{"ui":{"column_widths":{"date":999}}}', encoding="utf-8")

        result = storage.load_column_widths()

        self.assertEqual(result, {})

    def test_memory_payload_round_trips_through_sqlite(self):
        storage.save_memory_payload({"headers": ["A"], "days": [{"date": "2026-05-20", "meal_plan": {"idx": 2}}]})

        result = storage.load_memory_payload()

        self.assertEqual(result["headers"], ["A"])
        self.assertEqual(result["days"], [{"date": "2026-05-20", "meal_plan": {"idx": 2}}])

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
