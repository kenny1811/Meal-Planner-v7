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

    def test_saving_memory_payload_mirrors_days_into_plan_versions(self):
        # 直接讀 sqlite（plan_versions，一行一日）都要見到最新資料，唔止困喺 snapshot blob。
        storage.save_memory_payload({
            "headers": ["A"],
            "days": [
                {"date": "2026-07-10", "meal_plan": {"idx": 10}},
                {"date": "2026-07-11", "meal_plan": {"idx": 11}},
            ],
        })

        latest = storage.load_latest_versions(["2026-07-10", "2026-07-11"])
        got = {d["date"]: d["meal_plan"]["idx"] for d in latest["days"]}
        self.assertEqual(got, {"2026-07-10": 10, "2026-07-11": 11})

    def test_merge_memory_payload_keeps_days_missing_from_incoming_payload(self):
        existing = {
            "headers": ["old"],
            "indicator_rows": {"workday": ["old"]},
            "nutrient_keys": ["kcal"],
            "days": [
                {"date": "2026-06-23", "meal_plan": {"idx": 23}},
                {"date": "2026-06-24", "meal_plan": {"idx": 24}},
            ],
        }
        incoming = {
            "headers": ["new"],
            "indicator_rows": {"workday": ["new"]},
            "nutrient_keys": ["protein_g"],
            "days": [{"date": "2026-06-27", "meal_plan": {"idx": 27}}],
        }

        result = storage.merge_memory_payload(existing, incoming)

        self.assertEqual(result["headers"], ["new"])
        self.assertEqual(result["indicator_rows"], {"workday": ["new"]})
        self.assertEqual(result["nutrient_keys"], ["protein_g"])
        self.assertEqual([d["date"] for d in result["days"]], ["2026-06-23", "2026-06-24", "2026-06-27"])

    def test_merge_memory_payload_overwrites_matching_date_only(self):
        result = storage.merge_memory_payload(
            {"days": [{"date": "2026-06-23", "meal_plan": {"idx": "old"}}]},
            {"days": [{"date": "2026-06-23", "meal_plan": {"idx": "new"}}]},
        )

        self.assertEqual(result["days"], [{"date": "2026-06-23", "meal_plan": {"idx": "new"}}])

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

    def test_google_calendar_sync_settings_round_trip(self):
        storage.save_google_calendar_sync_settings({
            "enabled": True,
            "write": True,
            "client_secret_file": "C:/secrets/client.json",
            "token_file": "C:/secrets/token.json",
            "nonwork_calendar_id": "nonwork-calendar",
            "work_calendar_id": "work-calendar",
            "alarm_calendar_id": "alarm-calendar",
            "wake_offset_hours": 2.5,
        })

        self.assertEqual(
            storage.load_google_calendar_sync_settings(),
            {
                "enabled": True,
                "write": True,
                "client_secret_file": "C:/secrets/client.json",
                "token_file": "C:/secrets/token.json",
                "service_account_file": "",
                "nonwork_calendar_id": "nonwork-calendar",
                "work_calendar_id": "work-calendar",
                "alarm_calendar_id": "alarm-calendar",
                "wake_offset_hours": 2.5,
            },
        )

    def test_google_calendar_sync_settings_defaults_wake_offset(self):
        from meal_planner.google_calendar_sync import ALARM_CALENDAR_ID, WORK_CALENDAR_ID

        storage.save_google_calendar_sync_settings({"enabled": True})
        loaded = storage.load_google_calendar_sync_settings()
        self.assertEqual(loaded["wake_offset_hours"], 3.0)
        # 留空時回落內建預設 Calendar ID，而唔係空字串
        self.assertEqual(loaded["work_calendar_id"], WORK_CALENDAR_ID)
        self.assertEqual(loaded["alarm_calendar_id"], ALARM_CALENDAR_ID)


if __name__ == "__main__":
    unittest.main()
