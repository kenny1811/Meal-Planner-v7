import unittest
from datetime import date, time

from meal_planner.shift_time import (
    holiday_dates_from_rows,
    parse_time,
    payroll_coverage_issues,
    resolve_shift_time,
)

# 2026-07-06 一 / 07-07 二 / 07-10 五 / 07-12 日
MON = date(2026, 7, 6)
TUE = date(2026, 7, 7)
FRI = date(2026, 7, 10)
SUN = date(2026, 7, 12)

FJA_ROWS = [
    ["更碼", "開始時間", "結束時間", "適用日", "優先序"],
    ["FJA", "09:00", "18:30", "公眾假期", 1],
    ["FJA", "09:00", "19:30", "一二三四", 2],
    ["FJA", "09:00", "20:30", "五六", 2],
    ["FJA", "09:00", "18:30", "日", 2],
]


class ParseTimeTests(unittest.TestCase):
    def test_accepts_colon_compact_and_seconds_formats(self):
        self.assertEqual(parse_time("10:45"), time(10, 45))
        self.assertEqual(parse_time("1045"), time(10, 45))
        self.assertEqual(parse_time("10:45:30"), time(10, 45))
        self.assertIsNone(parse_time("2560"))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time(None))


class ResolveShiftTimeTests(unittest.TestCase):
    def test_weekday_rows_pick_matching_day(self):
        self.assertEqual(resolve_shift_time(FJA_ROWS, "FJA", MON, set()), (time(9, 0), time(19, 30)))
        self.assertEqual(resolve_shift_time(FJA_ROWS, "FJA", FRI, set()), (time(9, 0), time(20, 30)))
        self.assertEqual(resolve_shift_time(FJA_ROWS, "FJA", SUN, set()), (time(9, 0), time(18, 30)))

    def test_holiday_row_wins_over_weekday_row(self):
        self.assertEqual(
            resolve_shift_time(FJA_ROWS, "FJA", MON, {MON}), (time(9, 0), time(18, 30))
        )

    def test_holiday_without_holiday_row_falls_back_to_weekday_then_daily(self):
        rows = [
            ["更碼", "開始", "結束", "適用日"],
            ["IFCS1", "09:30", "19:15", "日一二三四"],
        ]
        # 假期但冇「公眾假期」行 → 照用星期行。
        self.assertEqual(resolve_shift_time(rows, "IFCS1", MON, {MON}), (time(9, 30), time(19, 15)))
        daily = [["更碼", "開始", "結束", "適用日"], ["A1", "08:15", "18:15", "每日"]]
        self.assertEqual(resolve_shift_time(daily, "A1", MON, {MON}), (time(8, 15), time(18, 15)))

    def test_daily_and_blank_rows_cover_every_day(self):
        rows = [["更碼", "開始", "結束"], ["TSB", "10:30", "21:30"]]
        self.assertEqual(resolve_shift_time(rows, "TSB", SUN, set()), (time(10, 30), time(21, 30)))

    def test_uncovered_day_returns_none_instead_of_guessing(self):
        rows = [
            ["更碼", "開始", "結束", "適用日"],
            ["IFCS2", "09:30", "20:15", "公眾假期"],
            ["IFCS2", "09:30", "20:15", "五六"],
        ]
        # 公司編更出錯先會咁：星期一唔係假期 → 冇行啱用，唔靜靜哋亂揀。
        self.assertEqual(resolve_shift_time(rows, "IFCS2", MON, set()), (None, None))
        self.assertEqual(resolve_shift_time(rows, "IFCS2", FRI, set()), (time(9, 30), time(20, 15)))

    def test_priority_column_is_ignored(self):
        rows = [
            ["更碼", "開始", "結束", "適用日", "優先序"],
            ["X", "09:00", "18:00", "一", 99],
            ["X", "10:00", "19:00", "二", 1],
        ]
        self.assertEqual(resolve_shift_time(rows, "X", MON, set()), (time(9, 0), time(18, 0)))

    def test_exact_code_match_only_and_case_insensitive(self):
        rows = [["更碼", "開始", "結束"], ["Lecole", "09:00", "19:00"]]
        self.assertEqual(resolve_shift_time(rows, "lecole", MON, set()), (time(9, 0), time(19, 0)))
        # 「Lecole Event」係獨立更碼，唔當「Lecole」變體。
        self.assertEqual(resolve_shift_time(rows, "Lecole Event", MON, set()), (None, None))

    def test_overtime_override_applies_after_resolution(self):
        overtime = {MON: (time(11, 30), time(20, 15))}
        self.assertEqual(
            resolve_shift_time(FJA_ROWS, "FJA", MON, set(), overtime), (time(11, 30), time(20, 15))
        )
        end_only = {MON: (None, time(22, 0))}
        self.assertEqual(
            resolve_shift_time(FJA_ROWS, "FJA", MON, set(), end_only), (time(9, 0), time(22, 0))
        )


class PayrollCoverageTests(unittest.TestCase):
    def test_fully_covered_codes_produce_no_issues(self):
        rows = FJA_ROWS + [["A1", "08:15", "18:15", "每日", 3]]
        self.assertEqual(payroll_coverage_issues(rows), [])

    def test_partially_covered_codes_report_uncovered_days(self):
        rows = [
            ["更碼", "開始", "結束", "適用日"],
            ["IFCS1", "09:30", "19:15", "日一二三四"],
            ["IFCS2", "09:30", "20:15", "公眾假期"],
            ["IFCS2", "09:30", "20:15", "五六"],
        ]
        self.assertEqual(
            payroll_coverage_issues(rows),
            [
                {"code": "IFCS1", "uncovered_days": "五六"},
                {"code": "IFCS2", "uncovered_days": "日一二三四"},
            ],
        )

    def test_rows_with_invalid_times_do_not_count_as_coverage(self):
        rows = [["更碼", "開始", "結束", "適用日"], ["Bad", "", "18:00", "每日"]]
        self.assertEqual(
            payroll_coverage_issues(rows), [{"code": "Bad", "uncovered_days": "日一二三四五六"}]
        )


class HolidayRowsTests(unittest.TestCase):
    def test_holiday_dates_from_rows_skips_header_and_blanks(self):
        rows = [["日期", "備註"], ["2026-07-01", "香港特別行政區成立紀念日"], [None], ["nonsense"]]
        self.assertEqual(holiday_dates_from_rows(rows), {date(2026, 7, 1)})


if __name__ == "__main__":
    unittest.main()
