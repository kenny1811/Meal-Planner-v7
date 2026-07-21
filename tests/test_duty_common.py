import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from meal_planner.duty_common import (
    GRACE_DETAIL,
    GRACE_MINUTES,
    POST_MAPPING,
    RETRY_SECONDS,
    retry_backoff_active,
)

HK = ZoneInfo("Asia/Hong_Kong")


class RetryBackoffTests(unittest.TestCase):
    def test_recent_failure_is_in_backoff(self):
        now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=HK)
        last = (now - timedelta(seconds=RETRY_SECONDS - 5)).isoformat()
        self.assertTrue(retry_backoff_active(last, now))

    def test_old_failure_is_out_of_backoff(self):
        now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=HK)
        last = (now - timedelta(seconds=RETRY_SECONDS + 5)).isoformat()
        self.assertFalse(retry_backoff_active(last, now))

    def test_invalid_or_missing_record_allows_retry(self):
        self.assertFalse(retry_backoff_active(""))
        self.assertFalse(retry_backoff_active(None))
        self.assertFalse(retry_backoff_active("not-a-date"))


class PolicyConstantsTests(unittest.TestCase):
    def test_grace_detail_reflects_grace_minutes(self):
        self.assertIn(str(GRACE_MINUTES), GRACE_DETAIL)

    def test_post_mapping_covers_known_brands(self):
        # VCA 更碼行 vca form，其餘行 other form（見 user-roster-code-brands 規則）。
        self.assertEqual(POST_MAPPING["VOC"][0], "vca")
        self.assertEqual(POST_MAPPING["Lecole"][0], "vca")
        self.assertEqual(POST_MAPPING["TSB"][0], "other")
        for code, (form_key, post) in POST_MAPPING.items():
            self.assertIn(form_key, ("vca", "other"), code)
            self.assertTrue(post, code)


if __name__ == "__main__":
    unittest.main()
