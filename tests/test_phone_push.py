import os
import tempfile
import unittest
from unittest import mock

from meal_planner import phone_push
from meal_planner.settings import clear_settings_cache


class PhonePushTests(unittest.TestCase):
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

    def test_remember_phone_host_records_and_builds_push_url(self):
        phone_push.remember_phone_host("192.168.15.102")

        endpoint = phone_push.phone_endpoint()

        self.assertEqual(endpoint["host"], "192.168.15.102")
        self.assertEqual(endpoint["url"], "http://192.168.15.102:8765/push/schedule-grid")
        self.assertTrue(endpoint["seen_at"])

    def test_localhost_is_not_the_phone(self):
        # 網頁自己（同一部電腦）打上嚟唔應該被當成電話，否則會 push 返自己。
        phone_push.remember_phone_host("127.0.0.1")
        phone_push.remember_phone_host("")

        self.assertEqual(phone_push.phone_endpoint()["host"], "")

    def test_push_without_known_phone_says_so(self):
        result = phone_push.push_schedule_grid()

        self.assertEqual(result["status"], "unknown_phone")
        self.assertIn("電話", result["detail"])

    def test_push_reports_phone_import_result(self):
        phone_push.remember_phone_host("100.78.27.188")
        body = b'{"ok":true,"alarm_count":7,"plan_date":"2026-07-29","roster_code":"TSB","message":"ok"}'
        opened = mock.MagicMock()
        opened.__enter__.return_value.read.return_value = body
        with mock.patch("urllib.request.urlopen", return_value=opened) as urlopen:
            result = phone_push.push_schedule_grid()

        self.assertEqual(urlopen.call_args[0][0].full_url, "http://100.78.27.188:8765/push/schedule-grid")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["alarm_count"], 7)
        self.assertEqual(result["roster_code"], "TSB")

    def test_push_failure_surfaces_the_reason(self):
        phone_push.remember_phone_host("100.78.27.188")
        with mock.patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            result = phone_push.push_schedule_grid()

        self.assertEqual(result["status"], "error")
        self.assertIn("network unreachable", result["detail"])


if __name__ == "__main__":
    unittest.main()
