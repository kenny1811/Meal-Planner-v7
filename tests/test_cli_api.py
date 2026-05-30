import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from fastapi.testclient import TestClient
from openpyxl import Workbook

from meal_planner import cli
from meal_planner.app import app
from meal_planner.settings import clear_settings_cache, get_settings


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

    def test_api_runtime_inputs_import_does_not_require_full_workbook_structure(self):
        old_root = os.environ.get("MENU_PROJECT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            settings = get_settings()
            wb = Workbook()
            wb.active.title = settings.sheets.roster
            wb[settings.sheets.roster].cell(1, 1).value = "2026年5月 1 SB"
            ot = wb.create_sheet(settings.sheets.overtime)
            ot.append(["日期", "開工", "收工"])
            ot.append(["2026-05-23", "09:00", "18:00"])
            wb.save(settings.workbook_path)

            client = TestClient(app)
            response = client.post("/api/runtime-inputs/import")
            payload = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["runtime_input_keys"], ["roster", "overtime"])
            self.assertEqual([sheet["row_count"] for sheet in payload["sheets"]], [1, 2])

        if old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = old_root
        clear_settings_cache()


if __name__ == "__main__":
    unittest.main()
