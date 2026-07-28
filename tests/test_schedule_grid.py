import unittest
import os
import tempfile
from datetime import date, time, timedelta

from meal_planner.schedule_grid_sync import (
    ScheduleGridNotFound,
    build_schedule_grid_all_variants_export,
    merge_schedule_grid_rows_for_import,
    parse_schedule_grid_push_payload,
    rows_for_dates,
    split_content_duration,
)
from meal_planner.maintenance_db import save_sheet_rows
from meal_planner.schedule_grid import (
    ScheduleRow,
    first_food_time,
    grid_row_matches_roster,
    load_schedule_rows_from_rows,
    report_start_end,
    resolve_meal_times_display,
    rows_for_roster,
)
from meal_planner.settings import clear_settings_cache, get_settings


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

    def test_grid_row_matches_roster_ignores_case_for_multi_word_codes(self):
        self.assertTrue(grid_row_matches_roster("Lecole Event", "Lecole event"))

    def test_grid_row_matches_roster_rejects_bracket_and_prefix_variants(self):
        # 括號唔係版本後綴：PenB(頂位) / FBPA(單人) 各自係獨立更碼，版本靠生效日期分。
        self.assertFalse(grid_row_matches_roster("PenB(頂位)", "PenB"))
        self.assertFalse(grid_row_matches_roster("FBPA(單人)", "FBPA"))
        self.assertFalse(grid_row_matches_roster("PenC頂位", "PenC"))
        self.assertFalse(grid_row_matches_roster("PenBM", "PenB"))

    def test_all_variants_requires_exact_current_roster_code(self):
        # 更表寫 PenB，行位表淨係有 PenB(頂位)：括號係另一個更碼，要報錯而唔係當佢係 PenB。
        target_day = date.today() + timedelta(days=30)
        roster_cell = f"{target_day.year}年{target_day.month}月 {target_day.day} PenB"
        with tempfile.TemporaryDirectory() as tmp:
            old_root = os.environ.get("MENU_PROJECT_ROOT")
            os.environ["MENU_PROJECT_ROOT"] = tmp
            clear_settings_cache()
            try:
                settings = get_settings()
                save_sheet_rows(
                    "roster",
                    [[roster_cell]],
                    settings,
                )
                save_sheet_rows(
                    "schedule_grid",
                    [
                        ["更碼", "時間", "內容", "時長", "生效日期"],
                        ["EleA", "09:00", "報開工", "60", "2026-06-01"],
                        ["PenB(頂位)", "09:50", "報開工", "10", "2026-06-17"],
                    ],
                    settings,
                )

                with self.assertRaises(ScheduleGridNotFound) as ctx:
                    build_schedule_grid_all_variants_export()
            finally:
                if old_root is None:
                    os.environ.pop("MENU_PROJECT_ROOT", None)
                else:
                    os.environ["MENU_PROJECT_ROOT"] = old_root
                clear_settings_cache()

        self.assertEqual(str(ctx.exception), "搵唔到 PenB 行位表")

    def test_phone_import_replaces_only_imported_code_for_effective_date(self):
        existing = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["Lecole", "09:00", "報開工", "60", "2026-06-17"],
            ["Lecole event", "12:00", "活動", "45", "2026-06-17"],
            ["PenBM", "10:00", "報開工", "75", "2026-06-17"],
        ]
        imported = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["PenBM", "10:20", "現場改", "10", "2026-06-17"],
        ]

        merged = merge_schedule_grid_rows_for_import(
            existing,
            imported,
            {"2026-06-17"},
            {"PenBM"},
        )

        self.assertIn(existing[1], merged)
        self.assertIn(existing[2], merged)
        self.assertNotIn(existing[3], merged)
        self.assertIn(imported[1], merged)
        self.assertEqual(len(rows_for_dates(existing, {"2026-06-17"}, {"PenBM"})), 1)

    def test_phone_import_without_codes_does_not_replace_entire_effective_date(self):
        existing = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["Lecole event", "12:00", "活動", "45", "2026-06-17"],
            ["PenBM", "10:00", "報開工", "75", "2026-06-17"],
        ]
        imported = [
            ["更碼", "時間", "內容", "時長", "生效日期"],
            ["", "10:20", "現場改", "10", "2026-06-17"],
        ]

        merged = merge_schedule_grid_rows_for_import(
            existing,
            imported,
            {"2026-06-17"},
            set(),
        )

        self.assertIn(existing[1], merged)
        self.assertIn(existing[2], merged)
        self.assertIn(imported[1], merged)
        self.assertEqual(rows_for_dates(existing, {"2026-06-17"}, set()), [])

    def test_phone_push_payload_splits_duration_and_stamps_code_and_version(self):
        rows, dates = parse_schedule_grid_push_payload(
            {
                "effective_date": "2026-06-17",
                "roster_code": "PenBM",
                "alarms": [
                    {"time": "10:20", "label": "報開工 10"},
                    {"time": "10:30", "label": "M 75"},
                    {"time": "20:30", "label": "報收工"},
                ],
            }
        )

        self.assertEqual(rows[0], ["更碼", "時間", "內容", "時長", "生效日期", "停用"])
        self.assertEqual(rows[1], ["PenBM", "10:20", "報開工", "10", "2026-06-17", ""])
        self.assertEqual(rows[2], ["PenBM", "10:30", "M", "75", "2026-06-17", ""])
        self.assertEqual(rows[3], ["PenBM", "20:30", "報收工", "", "2026-06-17", ""])
        self.assertEqual(dates, {"2026-06-17"})

    def test_phone_push_payload_skips_bad_rows_and_needs_alarms(self):
        rows, _ = parse_schedule_grid_push_payload(
            {
                "effective_date": "2026-06-17",
                "roster_code": "PenBM",
                "alarms": [
                    {"time": "咩時間", "label": "亂嘢"},
                    {"time": "10:20", "label": ""},
                    {"time": "10:30", "label": "M 75"},
                ],
            }
        )
        self.assertEqual(len(rows), 2)

        with self.assertRaises(Exception):
            parse_schedule_grid_push_payload({"alarms": []})

    def test_split_content_duration_keeps_marker_and_numberless_rows(self):
        self.assertEqual(split_content_duration("飯 (交人流計) 54"), ("飯 (交人流計)", "54"))
        self.assertEqual(split_content_duration("- 簽簿"), ("- 簽簿", ""))
        self.assertEqual(split_content_duration("報收工"), ("報收工", ""))
        self.assertEqual(split_content_duration("105"), ("105", ""))


class ReportStartEndWeekdayTests(unittest.TestCase):
    """唔同星期收唔同時間（FBPB 咁）靠 (日-四)/(五六) 標記分做兩行。"""

    ROWS = [
        ScheduleRow(code="FBPB", t=time(11, 0), content="報開工, 開舖 60", duration_min=60),
        ScheduleRow(code="FBPB", t=time(21, 30), content="報平安更, 報收工 (日-四) 30", duration_min=30),
        ScheduleRow(code="FBPB", t=time(22, 0), content="報平安更, 報收工 (五六)", duration_min=None),
    ]

    def test_weekday_marker_picks_the_matching_off_duty_row(self):
        # 2026-07-27 一 … 2026-08-02 日
        expected = ["21:30", "21:30", "21:30", "21:30", "22:00", "22:00", "21:30"]
        for i, want in enumerate(expected):
            day = date(2026, 7, 27) + timedelta(days=i)
            start, end = report_start_end(self.ROWS, day)
            self.assertEqual(start, time(11, 0), day)
            self.assertEqual(end.strftime("%H:%M"), want, day)

    def test_without_a_day_the_last_off_duty_row_wins(self):
        self.assertEqual(report_start_end(self.ROWS)[1], time(22, 0))

    def test_unmarked_rows_are_always_usable(self):
        rows = [
            ScheduleRow(code="VOC", t=time(9, 15), content="報平安更, 報開工", duration_min=None),
            ScheduleRow(code="VOC", t=time(21, 30), content="報收工, 報平安更", duration_min=None),
        ]
        self.assertEqual(report_start_end(rows, date(2026, 7, 31)), (time(9, 15), time(21, 30)))


class FoodTimeAfterStartTests(unittest.TestCase):
    """遲開工（打風／加班表 override）→ 開工前嘅行位表食位食唔到，要跳過兼講明。"""

    ROWS = [
        ScheduleRow(code="PenBM", t=time(10, 20), content="報開工, M 75", duration_min=75),
        ScheduleRow(code="PenBM", t=time(13, 15), content="飯 (交人流計) 55", duration_min=55),
        ScheduleRow(code="PenBM", t=time(16, 15), content="Tea (小食) 25", duration_min=25),
        ScheduleRow(code="PenBM", t=time(20, 30), content="報收工", duration_min=None),
    ]
    RULE = {"早餐": "開工前2小時", "午餐": "跟行位表", "小食": "跟行位表", "晚餐": "收工後1.5小時"}

    def _resolve(self, overrides):
        return resolve_meal_times_display(
            None,
            day=date(2026, 7, 26),
            roster_code="PenBM",
            primary_rule=self.RULE,
            is_work_day=True,
            restaurant=None,
            schedule_rows=self.ROWS,
            overtime_overrides=overrides,
        )

    def test_not_before_skips_food_rows_earlier_than_the_start(self):
        self.assertEqual(first_food_time(self.ROWS, keyword="飯")[0], time(13, 15))
        self.assertIsNone(first_food_time(self.ROWS, keyword="飯", not_before=time(13, 40))[0])
        self.assertEqual(
            first_food_time(self.ROWS, keyword="小食", not_before=time(13, 40))[0], time(16, 15)
        )

    def test_normal_start_keeps_every_meal(self):
        out = self._resolve({})
        self.assertEqual((out["早餐"], out["午餐"], out["小食"], out["晚餐"]),
                         ("08:20", "13:15", "16:15", "22:00"))
        self.assertEqual(out["_skipped"], {})

    def test_late_start_drops_the_passed_meal_and_says_why(self):
        out = self._resolve({date(2026, 7, 26): (time(13, 40), None)})
        self.assertEqual(out["早餐"], "11:40")     # 跟住開工郁
        self.assertIsNone(out["午餐"])              # 13:15 飯位已經過咗
        self.assertEqual(out["小食"], "16:15")      # 開工之後，仲食得到
        self.assertEqual(out["晚餐"], "22:00")
        self.assertIn("午餐", out["_skipped"])
        self.assertIn("13:15", out["_skipped"]["午餐"])


if __name__ == "__main__":
    unittest.main()
