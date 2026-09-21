import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from meal_planner.timeparse import (
    business_date,
    hhmm30,
    hhmm_from_minutes_30h,
    minutes_30h,
    normalize_hhmm,
    parse_time,
    slot_datetime,
)


class Clock30Tests(unittest.TestCase):
    def test_input_never_stays_in_the_early_morning_form(self):
        self.assertEqual(normalize_hhmm("00:16"), "24:16")
        self.assertEqual(normalize_hhmm("0016"), "24:16")
        self.assertEqual(normalize_hhmm("5:59"), "29:59")
        self.assertEqual(normalize_hhmm("06:00"), "06:00")
        self.assertEqual(normalize_hhmm("2756"), "27:56")

    def test_out_of_range_is_rejected(self):
        self.assertEqual(normalize_hhmm("30:00"), "")
        self.assertEqual(normalize_hhmm("12:75"), "")
        self.assertEqual(normalize_hhmm("abc"), "")

    def test_30h_text_parses_to_the_real_clock_time(self):
        self.assertEqual(parse_time("27:56"), time(3, 56))
        self.assertEqual(parse_time("2416"), time(0, 16))
        self.assertEqual(parse_time("29:59"), time(5, 59))
        self.assertIsNone(parse_time("30:00"))

    def test_display_always_shows_the_30h_form(self):
        self.assertEqual(hhmm30("03:56"), "27:56")
        self.assertEqual(hhmm30(time(3, 56)), "27:56")
        self.assertEqual(hhmm30("27:56"), "27:56")
        self.assertEqual(hhmm30("09:15"), "09:15")
        self.assertEqual(hhmm30("bad"), "")

    def test_minutes_are_unchanged_by_the_written_form(self):
        self.assertEqual(minutes_30h("27:56"), minutes_30h("03:56"))
        self.assertEqual(minutes_30h("27:56"), 27 * 60 + 56)

    def test_minutes_accepts_time_and_datetime(self):
        self.assertEqual(minutes_30h(time(1, 30)), 25 * 60 + 30)
        self.assertEqual(minutes_30h(time(23, 30)), 23 * 60 + 30)
        self.assertEqual(minutes_30h(datetime(2026, 7, 5, 0, 16)), 24 * 60 + 16)
        self.assertEqual(minutes_30h(datetime(2026, 7, 5, 6, 0)), 6 * 60)

    def test_hhmm_from_minutes_keeps_30h_form_and_wraps_beyond_it(self):
        self.assertEqual(hhmm_from_minutes_30h(9 * 60 + 15), "09:15")
        self.assertEqual(hhmm_from_minutes_30h(25 * 60 + 30), "25:30")
        self.assertEqual(hhmm_from_minutes_30h(29 * 60 + 59), "29:59")
        self.assertEqual(hhmm_from_minutes_30h(30 * 60), "06:00")
        self.assertEqual(hhmm_from_minutes_30h(31 * 60 + 20), "07:20")
        self.assertEqual(hhmm_from_minutes_30h(-80), "22:40")
        for m in range(0, 1800, 7):
            self.assertEqual(minutes_30h(hhmm_from_minutes_30h(m)), m if m >= 360 else m + 1440)

    def test_parse_time_is_the_30h_text_to_clock_helper(self):
        # 自動交 form／build_day_plan 用嚟將 "25:30" 變返 time(1, 30)
        self.assertEqual(parse_time("25:30"), time(1, 30))
        self.assertEqual(parse_time("21:50"), time(21, 50))
        self.assertIsNone(parse_time("bad"))
        self.assertIsNone(parse_time(""))

    def test_business_date_and_slot_datetime_round_trip(self):
        tz = ZoneInfo("Asia/Hong_Kong")
        night = datetime(2026, 7, 5, 0, 16, tzinfo=tz)
        self.assertEqual(business_date(night), date(2026, 7, 4))
        self.assertEqual(slot_datetime(date(2026, 7, 4), "24:16", tz), night)
        self.assertEqual(slot_datetime(date(2026, 7, 4), time(0, 16), tz), night)
        self.assertEqual(slot_datetime(date(2026, 7, 4), time(21, 50), tz), datetime(2026, 7, 4, 21, 50, tzinfo=tz))


if __name__ == "__main__":
    unittest.main()
