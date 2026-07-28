import unittest
from datetime import time

from meal_planner.timeparse import hhmm30, minutes_30h, normalize_hhmm, parse_time


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


if __name__ == "__main__":
    unittest.main()
