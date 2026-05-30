import unittest
from datetime import date, time

from meal_planner.schedule_grid import ScheduleRow, load_schedule_rows_from_rows, rows_for_roster


class ScheduleGridTests(unittest.TestCase):
    def test_rows_for_roster_uses_latest_effective_version_for_day(self):
        rows = [
            ScheduleRow("EleC1", time(12, 0), "飯", 45),
            ScheduleRow("EleC1", time(13, 0), "飯", 45, effective_from=date(2026, 6, 1)),
            ScheduleRow("EleC1", time(14, 0), "飯", 45, effective_from=date(2026, 7, 1)),
        ]

        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 5, 31))[0].t, time(12, 0))
        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 6, 1))[0].t, time(13, 0))
        self.assertEqual(rows_for_roster(rows, "EleC1", date(2026, 7, 2))[0].t, time(14, 0))

    def test_load_schedule_rows_from_rows_reads_optional_effective_date(self):
        rows = load_schedule_rows_from_rows(
            [
                ["更碼", "時間", "內容", "時長", "生效日期"],
                ["EleC1", "13:00", "飯", "45", "2026-06-01"],
            ]
        )

        self.assertEqual(rows[0].code, "EleC1")
        self.assertEqual(rows[0].t, time(13, 0))
        self.assertEqual(rows[0].duration_min, 45)
        self.assertEqual(rows[0].effective_from, date(2026, 6, 1))


if __name__ == "__main__":
    unittest.main()
