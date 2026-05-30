import unittest
from datetime import date

from meal_planner.roster import code_for_date, is_work_day, last_day_of_month, parse_roster_line, roster_for_month


class RosterTests(unittest.TestCase):
    def test_parse_roster_line_reads_month_header_and_day_code_pairs(self):
        rm = parse_roster_line("2026年5月 1 PenC 2 SB 3 WL 4 SHx trailing ignored")

        self.assertIsNotNone(rm)
        assert rm is not None
        self.assertEqual((rm.year, rm.month), (2026, 5))
        self.assertEqual(rm.day_to_code, {1: "PenC", 2: "SB", 3: "WL", 4: "SHx"})

    def test_parse_roster_line_ignores_empty_or_non_month_cells(self):
        self.assertIsNone(parse_roster_line(None))
        self.assertIsNone(parse_roster_line(""))
        self.assertIsNone(parse_roster_line("not a roster line"))

    def test_roster_for_month_keeps_latest_month_row_and_code_lookup_is_month_scoped(self):
        out = roster_for_month(
            iter(
                [
                    "2026年5月 1 A 2 B",
                    "noise",
                    "2026年6月 1 C",
                    "2026年5月 1 Z",
                ]
            )
        )

        self.assertEqual(out[(2026, 5)].day_to_code, {1: "Z"})
        self.assertEqual(code_for_date(out[(2026, 5)], date(2026, 5, 1)), "Z")
        self.assertIsNone(code_for_date(out[(2026, 5)], date(2026, 6, 1)))

    def test_is_work_day_matches_non_work_prefix_rules(self):
        for code in ("SB", "WL", "WLx", "SH", "AL123", "SL"):
            self.assertFalse(is_work_day(code))
        for code in ("PenC", "IFCM", "SBA", "XWL"):
            self.assertTrue(is_work_day(code))

    def test_last_day_of_month_handles_leap_year(self):
        self.assertEqual(last_day_of_month(2024, 2), 29)
        self.assertEqual(last_day_of_month(2026, 2), 28)


if __name__ == "__main__":
    unittest.main()
