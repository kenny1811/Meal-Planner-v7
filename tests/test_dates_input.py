import unittest
from datetime import date

from meal_planner.dates_input import parse_date_expression


class DatesInputTests(unittest.TestCase):
    def test_parse_space_and_same_month_ranges_deduped_sorted(self):
        self.assertEqual(
            parse_date_expression("3 5 5 7-9 12", year=2026, month=5),
            [
                date(2026, 5, 3),
                date(2026, 5, 5),
                date(2026, 5, 7),
                date(2026, 5, 8),
                date(2026, 5, 9),
                date(2026, 5, 12),
            ],
        )

    def test_parse_comma_segments_and_reject_spaces_inside_comma_segments(self):
        self.assertEqual(
            parse_date_expression("3,5,7-9,12", year=2026, month=5),
            [
                date(2026, 5, 3),
                date(2026, 5, 5),
                date(2026, 5, 7),
                date(2026, 5, 8),
                date(2026, 5, 9),
                date(2026, 5, 12),
            ],
        )
        with self.assertRaisesRegex(ValueError, "逗號分段內唔可含空格"):
            parse_date_expression("3 5,7-9", year=2026, month=5)

    def test_parse_cross_month_and_year_boundary_ranges(self):
        self.assertEqual(
            parse_date_expression("30-2", year=2026, month=5),
            [date(2026, 5, 30), date(2026, 5, 31), date(2026, 6, 1), date(2026, 6, 2)],
        )
        self.assertEqual(
            parse_date_expression("31-2", year=2026, month=12),
            [date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2)],
        )

    def test_rejects_invalid_tokens_and_out_of_month_days(self):
        with self.assertRaisesRegex(ValueError, "無法解析日期"):
            parse_date_expression("12/a", year=2026, month=5)
        with self.assertRaisesRegex(ValueError, "超出"):
            parse_date_expression("31", year=2026, month=4)


if __name__ == "__main__":
    unittest.main()
