import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from meal_planner.duty_common import (
    GRACE_DETAIL,
    GRACE_MINUTES,
    POST_MAPPING_SEED,
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

    def test_post_mapping_seed_has_a_post_for_every_work_code(self):
        self.assertEqual(POST_MAPPING_SEED["VOC"], "V-OC 海港")
        self.assertEqual(POST_MAPPING_SEED["PenBM"], "PENB - 半島時裝")
        for code, post in POST_MAPPING_SEED.items():
            self.assertTrue(post, code)



if __name__ == "__main__":
    unittest.main()
