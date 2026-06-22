import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from openpyxl import Workbook

import meal_planner.app as app_module
from meal_planner import cli
from meal_planner.app import app
from meal_planner.settings import clear_settings_cache, get_settings
from meal_planner.storage import save_memory_payload


class CliApiTests(unittest.TestCase):
    def test_cli_missing_preview_args_uses_error_envelope(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            code = cli.main(["--compact"])

        payload = json.loads(stderr.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("--year", payload["error"]["details"]["missing"])

    def test_cli_health_uses_success_envelope(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = cli.main(["--health", "--compact"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertIn("workbook_exists", payload["data"])

    def test_api_validation_error_uses_error_envelope(self):
        client = TestClient(app)

        response = client.post("/api/preview", json={})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("errors", payload["error"]["details"])

    def test_preview_regeneration_allows_existing_today_before_first_meal(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            today = datetime(2026, 6, 23).date()
            save_memory_payload(
                {
                    "days": [
                        {
                            "date": today.isoformat(),
                            "meal_plan": {"meal_times_resolved": {"早餐": "07:30"}},
                        }
                    ]
                }
            )

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 6, 23, 6, 0, tzinfo=tz)

            with patch("meal_planner.app.datetime", FixedDateTime):
                blocked = app_module._preview_regeneration_blocked_dates([today])

            self.assertEqual(blocked, [])

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()

    def test_api_preview_rejects_regenerating_existing_today_after_first_meal(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            today = datetime(2026, 6, 23).date()
            save_memory_payload(
                {
                    "days": [
                        {
                            "date": today.isoformat(),
                            "meal_plan": {"meal_times_resolved": {"早餐": "07:30"}},
                        }
                    ]
                }
            )
            client = TestClient(app)

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 6, 23, 8, 0, tzinfo=tz)

            with patch("meal_planner.app.datetime", FixedDateTime):
                response = client.post(
                    "/api/preview",
                    json={
                        "year": today.year,
                        "month": today.month,
                        "dates_expr": str(today.day),
                    },
                )

            self.assertEqual(response.status_code, 400)
            payload = response.json()
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["details"]["rejected"], [today.isoformat()])
            self.assertIn("第一餐後", payload["error"]["message"])

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()

    def test_api_health_and_debug_stats(self):
        client = TestClient(app)

        health = client.get("/api/health").json()
        stats = client.get("/api/debug/stats").json()

        self.assertEqual(health["status"], "ok")
        self.assertIn("workbook_exists", health)
        self.assertTrue(stats["ok"])
        self.assertIn("requests_total", stats["stats"])
        self.assertIn("/api/health", stats["stats"]["by_path"])

    def test_api_detail_settings_reads_and_updates_rice_ratios(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            with open(os.path.join(tmp, "config.yaml"), "w", encoding="utf-8") as f:
                f.write(
                    "rice:\n"
                    "  cooked_to_raw_brown: 2.623\n"
                    "  cooked_to_raw_other: 2.67\n"
                    "  water_multiplier: 2\n"
                    "  rice_category_exact: \"米\"\n"
                    "  note_name_contains: [\"米\"]\n"
                    "  brown_name_contains: \"糙米\"\n"
                )
            clear_settings_cache()
            client = TestClient(app)

            before = client.get("/api/detail-settings").json()
            response = client.post(
                "/api/detail-settings",
                json={"cooked_to_raw_brown": 2.5, "cooked_to_raw_other": 2.8},
            )
            after = response.json()

            self.assertEqual(before["rice"]["cooked_to_raw_brown"], 2.623)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(after["ok"])
            self.assertEqual(after["rice"]["cooked_to_raw_brown"], 2.5)
            self.assertEqual(after["rice"]["cooked_to_raw_other"], 2.8)
            with open(os.path.join(tmp, "config.yaml"), encoding="utf-8") as f:
                saved = f.read()
            self.assertIn("cooked_to_raw_brown: 2.5", saved)
            self.assertIn("cooked_to_raw_other: 2.8", saved)

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()

    def test_api_targets_reads_and_updates_profile(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            with open(os.path.join(tmp, "config.yaml"), "w", encoding="utf-8") as f:
                f.write(
                    "rice:\n"
                    "  cooked_to_raw_brown: 2.623\n"
                    "  cooked_to_raw_other: 2.67\n"
                    "  water_multiplier: 2\n"
                    "  rice_category_exact: \"米\"\n"
                    "  note_name_contains: [\"米\"]\n"
                    "  brown_name_contains: \"糙米\"\n"
                )
            clear_settings_cache()
            client = TestClient(app)
            today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
            dob = f"{today.year - 42:04d}-01-01"

            response = client.post(
                "/api/targets",
                json={
                    "headers": ["卡路里", "蛋白質", "碳水", "天然糖", "膽固醇", "鈉", "鈣", "總脂肪", "飽和脂肪", "反式脂肪"],
                    "workday": ["100-200", "10-20", "20-30", "< 5", "< 10", "< 100", "> 300", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"],
                    "nonworkday": ["90-180", "9-18", "18-28", "< 4", "< 9", "< 90", "> 280", "< 27.5% kcal", "< 7% kcal", "< 1% kcal"],
                    "profile": {
                        "dob": dob,
                        "gender": "male",
                        "height_cm": 173.5,
                        "weight_history": [{"weight_kg": 68.2, "recorded_at": "2026-06-21 12:34:56"}],
                    },
                    "target_settings": {
                        "workday": {"activity_factor": 1.4, "calorie_range_band": 60},
                        "nonworkday": {"activity_factor": 1.15, "sodium_mg": 1650},
                    },
                },
            )
            payload = response.json()
            loaded = client.get("/api/targets").json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["profile"]["dob"], dob)
            self.assertEqual(payload["profile"]["age"], 42)
            self.assertEqual(payload["profile"]["gender"], "male")
            self.assertEqual(payload["profile"]["height_cm"], 173.5)
            self.assertEqual(payload["profile"]["weight_kg"], 68.2)
            self.assertEqual(payload["profile"]["last_updated"], "2026-06-21 12:34:56")
            self.assertEqual([item["weight_kg"] for item in payload["profile"]["weight_history"]], [68.2])
            self.assertEqual(payload["target_settings"]["workday"]["activity_factor"], 1.4)
            self.assertEqual(payload["target_settings"]["workday"]["calorie_range_band"], 60)
            self.assertEqual(payload["target_settings"]["nonworkday"]["activity_factor"], 1.15)
            self.assertEqual(payload["target_settings"]["nonworkday"]["sodium_mg"], 1650)
            self.assertEqual(loaded["profile"], payload["profile"])
            self.assertEqual(loaded["target_settings"], payload["target_settings"])
            with open(os.path.join(tmp, "config.yaml"), encoding="utf-8") as f:
                saved = f.read()
            self.assertNotIn("profile:", saved)

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()

    def test_api_single_maintenance_import_only_requires_target_sheet(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            settings = get_settings()
            wb = Workbook()
            wb.active.title = settings.sheets.public_holidays
            wb[settings.sheets.public_holidays].append(["日期", "假期名稱"])
            wb[settings.sheets.public_holidays].append(["2026-01-01", "元旦"])
            wb.save(settings.workbook_path)

            client = TestClient(app)
            response = client.post("/api/maint/sheets/public_holidays/import")
            payload = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["rows"][1], ["2026-01-01", "元旦"])

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()


if __name__ == "__main__":
    unittest.main()
