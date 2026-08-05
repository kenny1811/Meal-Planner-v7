"""Typhoon 模擬：開工時間點算、四段輸出啱唔啱、套用寫唔寫得落加班表。"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta

from meal_planner.maintenance_db import load_sheet_rows, save_roster_code_definitions, save_sheet_rows
from meal_planner.settings import clear_settings_cache, get_settings
from meal_planner import typhoon
from meal_planner.typhoon import apply_typhoon, build_typhoon_plan, typhoon_report_minutes

BIZ_DATE = date(2026, 7, 20)  # 星期一（過去日：唯讀模擬，套用唔得）
_TODAY = date.today()
FUTURE_DATE = date(_TODAY.year + 1, _TODAY.month, 15)  # 未來日：套用得

SCHEDULE_GRID = [
    ["更碼", "時間", "內容", "時長", "生效日期", "停用"],
    ["VOC", "09:15", "報開工, 報平安更", 240, "2026-01-01", ""],
    ["VOC", "13:15", "飯", 60, "2026-01-01", ""],
    ["VOC", "14:15", "行位", 180, "2026-01-01", ""],
    ["VOC", "17:15", "- 報平安更", None, "2026-01-01", ""],
    ["VOC", "18:00", "小食", 30, "2026-01-01", ""],
    ["VOC", "21:30", "報收工, 報平安更", None, "2026-01-01", ""],
    ["EleA", "09:15", "報開工, 報平安更", 240, "2026-01-01", ""],
    ["EleA", "13:15", "飯", 60, "2026-01-01", ""],
    ["EleA", "21:30", "報收工, 報平安更", None, "2026-01-01", ""],
    # PenBM 本身唔使報平安更——打風都唔應該生出報更。
    ["PenBM", "10:30", "報開工, M 75", 75, "2026-01-01", ""],
    ["PenBM", "13:15", "飯", 55, "2026-01-01", ""],
    ["PenBM", "20:30", "報收工", None, "2026-01-01", ""],
]

MEAL_TIMES = [
    ["更碼", "早餐", "午餐", "小食", "晚餐"],
    ["VOC", "開工前 2 小時", "跟行位表", "跟行位表", "收工後 1.5 小時"],
    ["EleA", "開工前 2 小時", "跟行位表", "—", "收工後 1.5 小時"],
]

ROSTER = [
    ["更表"],
    ["2026年7月 20 VOC 21 EleA"],
    [f"{FUTURE_DATE.year}年{FUTURE_DATE.month}月 {FUTURE_DATE.day} VOC"],
]

PAYROLL_TIMES = [
    ["更碼", "開始時間", "結束時間", "適用日"],
    ["VOC", "09:30", "21:00", "每日"],
    ["EleA", "09:30", "21:00", "每日"],
    ["PenBM", "10:30", "20:30", "每日"],
]


class TyphoonTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = os.environ.get("MENU_PROJECT_ROOT")
        os.environ["MENU_PROJECT_ROOT"] = self.tmp.name
        clear_settings_cache()
        self.settings = get_settings()
        save_sheet_rows("schedule_grid", SCHEDULE_GRID, self.settings)
        save_sheet_rows("meal_times", MEAL_TIMES, self.settings)
        save_sheet_rows("roster", ROSTER, self.settings)
        save_sheet_rows("payroll_times", PAYROLL_TIMES, self.settings)
        save_sheet_rows("public_holidays", [["日期"]], self.settings)
        save_sheet_rows("overtime", [["日期", "開工", "收工", "備註"]], self.settings)
        save_roster_code_definitions(
            [
                {"pattern": "WL*", "label": "週假"},
                {"pattern": "TP", "label": "颱風假"},
                {"pattern": "其他", "label": "返工日"},
            ],
            self.settings,
        )

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = self.old_root
        clear_settings_cache()
        self.tmp.cleanup()

    def plan(self, **kwargs):
        params = {"biz_date": BIZ_DATE, "signal_time": "11:40"}
        params.update(kwargs)
        return build_typhoon_plan(self.settings, **params)


class StartTimeTests(TyphoonTestBase):
    def test_vca_also_waits_an_hour_after_the_signal(self) -> None:
        plan = self.plan()
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["brand"], "VCA")
        self.assertEqual(plan["offset_minutes"], 60)
        self.assertEqual(plan["start"], "12:40")
        self.assertEqual(plan["planned_start"], "09:15")
        self.assertEqual(plan["delay_minutes"], 205)

    def test_other_brand_waits_an_hour(self) -> None:
        plan = self.plan(biz_date=date(2026, 7, 21))
        self.assertEqual(plan["roster_code"], "EleA")
        self.assertEqual(plan["brand"], "Other")
        self.assertEqual(plan["offset_minutes"], 60)
        self.assertEqual(plan["start"], "12:40")

    def test_signal_before_the_shift_keeps_the_planned_start(self) -> None:
        plan = self.plan(signal_time="06:00")
        self.assertEqual(plan["start"], "09:15")
        self.assertEqual(plan["delay_minutes"], 0)
        self.assertFalse(plan["start_shifted"])

    def test_finish_time_never_moves(self) -> None:
        self.assertEqual(self.plan()["end"], "21:30")
        self.assertEqual(self.plan(signal_time="20:00")["end"], "21:30")

    def test_compact_and_30h_signal_input(self) -> None:
        self.assertEqual(self.plan(signal_time="1140")["signal_time"], "11:40")
        self.assertEqual(self.plan(signal_time="2416")["signal_time"], "24:16")

    def test_signal_after_the_shift_moves_to_the_next_work_day(self) -> None:
        # 日期 + 落波時間係一 pair ＝ 個波幾時落。29:00 落波嗰陣當日嗰更（收工 21:30）
        # 已經收咗工 → 要睇嘅係下一個返工日，而個波喺嗰日開工之前就落咗 → 照原定開工。
        plan = self.plan(signal_time="29:00")

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["days_after_signal"], 1)
        self.assertEqual(plan["date_iso"], (BIZ_DATE + timedelta(days=1)).isoformat())
        self.assertEqual(plan["signal_date_iso"], BIZ_DATE.isoformat())
        self.assertEqual(plan["start"], plan["planned_start"])
        self.assertEqual(plan["delay_minutes"], 0)
        self.assertFalse(plan["start_shifted"])

    def test_after_midnight_signal_is_always_read_as_30h(self) -> None:
        # 落波唔收 00:00–05:59：打 02:56 即係 26:56，唔會有第二個讀法。
        plan = self.plan(signal_time="02:56")
        self.assertEqual(plan["signal_time"], "26:56")

    def test_overnight_shift_keeps_the_30h_reading(self) -> None:
        # 通宵更 22:00–06:00：02:56 落波係更入面嗰段，要用 30 小時制讀法。
        save_sheet_rows(
            "schedule_grid",
            SCHEDULE_GRID + [
                ["NiteA", "22:00", "報開工", 120, "2026-01-01", ""],
                ["NiteA", "06:00", "報收工", None, "2026-01-01", ""],
            ],
            self.settings,
        )
        # 用 00:30 落波：距離 06:00 收工仲有 5.5 個鐘，唔會觸發「全日唔使返」。
        plan = self.plan(roster_code="NiteA", signal_time="00:30")
        self.assertEqual(plan["signal_time"], "24:30")
        self.assertEqual(plan["start"], "25:30")  # NiteA 唔係 VCA → 落波後一個鐘
        self.assertTrue(plan["start_shifted"])
        self.assertFalse(plan["day_off"])

    def test_overnight_signal_close_to_the_finish_is_a_day_off(self) -> None:
        save_sheet_rows(
            "schedule_grid",
            SCHEDULE_GRID + [
                ["NiteA", "22:00", "報開工", 120, "2026-01-01", ""],
                ["NiteA", "06:00", "報收工", None, "2026-01-01", ""],
            ],
            self.settings,
        )
        # 02:56 落波、06:00 收工 = 3 個鐘零 4 分鐘 → 可能全日唔使返，但要舖頭宣佈先作實。
        plan = self.plan(roster_code="NiteA", signal_time="02:56")
        self.assertTrue(plan["day_off_possible"])
        self.assertFalse(plan["day_off"])
        self.assertTrue(plan["start_shifted"])  # 未宣佈 → 照返工計
        announced = self.plan(roster_code="NiteA", signal_time="02:56", day_off_announced=True)
        self.assertTrue(announced["day_off"])

    def test_manual_code_overrides_the_roster(self) -> None:
        plan = self.plan(roster_code="EleA")
        self.assertEqual(plan["roster_code"], "EleA")
        self.assertEqual(plan["code_source"], "manual")
        self.assertEqual(plan["start"], "12:40")


class NotOkTests(TyphoonTestBase):
    def test_missing_signal_time_is_not_ok(self) -> None:
        plan = self.plan(signal_time="")
        self.assertFalse(plan["ok"])
        self.assertIn("signal-down time", plan["note"])

    def test_unreadable_signal_time_says_so(self) -> None:
        plan = self.plan(signal_time="下午")
        self.assertFalse(plan["ok"])
        self.assertIn("11:40", plan["note"])

    def test_non_work_code_has_nothing_to_simulate(self) -> None:
        plan = self.plan(roster_code="WL1")
        self.assertFalse(plan["ok"])
        self.assertIn("not a work day", plan["note"])

    def test_day_without_a_roster_code(self) -> None:
        plan = self.plan(biz_date=date(2026, 7, 25))
        self.assertFalse(plan["ok"])
        self.assertIn("No roster code", plan["note"])


class SectionTests(TyphoonTestBase):
    def test_grid_inserts_the_real_start_and_dims_everything_before_it(self) -> None:
        rows = self.plan()["grid"]["rows"]
        self.assertEqual(
            [row["time"] for row in rows],
            ["09:15", "12:40", "13:15", "14:15", "16:40", "18:00", "20:40", "21:30"],
        )
        inserted = rows[1]
        self.assertTrue(inserted["inserted"])
        self.assertTrue(inserted["is_start"])
        self.assertEqual(inserted["duration_min"], 35)  # 12:40 → 13:15 個飯位
        # 原本嗰行報開工唔會改時間，佢就係你返唔到嗰個位。
        self.assertTrue(rows[0]["unreachable"])
        self.assertFalse(rows[0]["inserted"])
        self.assertFalse(rows[2]["unreachable"])

    def test_grid_swaps_the_old_safe_reports_for_the_4h_ones(self) -> None:
        rows = {row["time"]: row for row in self.plan()["grid"]["rows"]}
        # 原定 17:15 而家啱啱好唔喺 4 小時表入面？12:40 起計係 16:40 / 20:40，所以照剷。
        self.assertNotIn("17:15", rows)
        # 4 小時規則插入嘅兩個；`-` 開頭跟 marker 慣例，唔佔時長。
        for hhmm in ("16:40", "20:40"):
            self.assertTrue(rows[hhmm]["inserted"])
            self.assertIn("報平安更", rows[hhmm]["content"])
            self.assertIsNone(rows[hhmm]["duration_min"])
        # 收工嗰行本身就係最後一次報更（21:30 喺表入面）→ 留住、唔重覆插。
        self.assertIn("21:30", rows)
        self.assertFalse(rows["21:30"]["inserted"])

    def test_grid_leaves_safe_reports_alone_when_the_start_does_not_move(self) -> None:
        rows = [row["time"] for row in self.plan(signal_time="06:00")["grid"]["rows"]]
        self.assertEqual(rows, ["09:15", "13:15", "14:15", "17:15", "18:00", "21:30"])

    def test_grid_marks_the_lunch_slot_when_the_start_passes_it(self) -> None:
        rows = {row["time"]: row for row in self.plan(signal_time="14:00")["grid"]["rows"]}
        self.assertTrue(rows["13:15"]["unreachable"])
        self.assertFalse(rows["18:00"]["unreachable"])
        self.assertTrue(rows["15:00"]["inserted"])

    def test_grid_skips_markers_when_sizing_the_inserted_row(self) -> None:
        rows = {row["time"]: row for row in self.plan(signal_time="15:30")["grid"]["rows"]}
        # 16:30 開工，之後係 17:15 marker（`-` 開頭，唔佔時間），時長要跨去 18:00 小食。
        self.assertEqual(rows["16:30"]["duration_min"], 90)

    def test_grid_inserts_nothing_when_the_start_does_not_move(self) -> None:
        rows = self.plan(signal_time="06:00")["grid"]["rows"]
        self.assertFalse(any(row["inserted"] for row in rows))
        self.assertFalse(any(row["unreachable"] for row in rows))

    def test_meals_shift_with_the_start(self) -> None:
        rows = {row["meal"]: row for row in self.plan()["meals"]["rows"]}
        self.assertEqual(rows["早餐"]["before"], "07:15")
        self.assertEqual(rows["早餐"]["after"], "10:40")
        self.assertEqual(rows["晚餐"]["after"], "23:00")

    def test_meal_that_can_no_longer_be_eaten_says_why(self) -> None:
        rows = {row["meal"]: row for row in self.plan(signal_time="13:00")["meals"]["rows"]}
        self.assertEqual(rows["午餐"]["before"], "13:15")
        self.assertEqual(rows["午餐"]["after"], "")
        self.assertIn("食唔到", rows["午餐"]["skipped"])

    def test_report_normal_runs_every_four_hours_from_the_typhoon_start(self) -> None:
        section = self.plan()["report_normal"]
        self.assertEqual(section["mode"], "typhoon")
        # 12:40 開工 → 16:40 → 20:40 → 收工 21:30（距 20:40 得 50 分鐘，唔夠 4 個鐘）
        self.assertEqual([row["time"] for row in section["rows"]], ["12:40", "16:40", "20:40", "21:30"])
        self.assertIn("報開工", section["rows"][0]["content"])
        self.assertEqual(section["rows"][1]["content"], "報平安更")
        self.assertIn("報收工", section["rows"][-1]["content"])
        self.assertEqual(section["planned_times"], ["09:15", "17:15", "21:30"])

    def test_shift_without_safe_reports_gets_none_from_the_typhoon(self) -> None:
        plan = self.plan(roster_code="PenBM")
        section = plan["report_normal"]
        self.assertEqual(section["mode"], "grid")
        self.assertEqual(section["rows"], [])
        self.assertEqual(section["extra_times"], [])
        self.assertEqual(section["skip_slot_ids"], [])
        self.assertIn("no 報平安更", section["note"])
        # 行位表插入嗰行淨係「報開工」，唔會多咗個報平安更出嚟。
        inserted = next(row for row in plan["grid"]["rows"] if row["inserted"])
        self.assertEqual(inserted["content"], "報開工")
        self.assertFalse(any("報平安更" in row["content"] for row in plan["grid"]["rows"]))

    def test_report_normal_keeps_the_grid_when_the_start_does_not_move(self) -> None:
        section = self.plan(signal_time="06:00")["report_normal"]
        self.assertEqual(section["mode"], "grid")
        self.assertEqual([row["time"] for row in section["rows"]], ["09:15", "17:15", "21:30"])

    def test_signal_too_close_to_the_finish_only_flags_a_possible_day_off(self) -> None:
        # 落波 20:00、收工 21:30 —— 唔夠 4 個鐘，但未宣佈就照返工計。
        plan = self.plan(signal_time="20:00")
        self.assertTrue(plan["day_off_possible"])
        self.assertFalse(plan["day_off"])
        self.assertIn("等舖頭宣佈", plan["day_off_note"])
        self.assertTrue(plan["start_shifted"])
        self.assertNotEqual(plan["report_normal"]["rows"], [])

    def test_announced_day_off_clears_everything(self) -> None:
        plan = self.plan(signal_time="20:00", day_off_announced=True)
        self.assertTrue(plan["day_off"])
        self.assertEqual(plan["day_off_code"], "TP")
        self.assertIn("舖頭宣佈全日唔使返", plan["day_off_note"])
        self.assertFalse(plan["start_shifted"])
        self.assertEqual(plan["report_normal"]["rows"], [])
        self.assertEqual(plan["grid"]["rows"], [])

    def test_day_off_cannot_be_announced_when_the_gap_is_wide(self) -> None:
        # 落波 13:40、收工 21:30 —— 夠 4 個鐘，剔咗都唔算全日唔使返。
        plan = self.plan(signal_time="13:40", day_off_announced=True)
        self.assertFalse(plan["day_off_possible"])
        self.assertFalse(plan["day_off"])

    def test_signal_early_enough_is_still_a_work_day(self) -> None:
        plan = self.plan(signal_time="17:29")  # 收工 21:30，仲有 4 個鐘零 1 分鐘
        self.assertFalse(plan["day_off"])
        self.assertTrue(plan["start_shifted"])

    def test_typhoon_report_minutes_rule(self) -> None:
        start = 10 * 60
        self.assertEqual(typhoon_report_minutes(start, 22 * 60), [600, 840, 1080, 1320])
        # 收工啱啱好 4 個鐘之後：唔會多插一次，最後嗰次就係收工。
        self.assertEqual(typhoon_report_minutes(start, 14 * 60), [600, 840])
        # 冇收工時間 → 淨係報開工嗰次。
        self.assertEqual(typhoon_report_minutes(start, None), [600])

    def test_onoffduty_shows_the_shifted_start_and_untouched_end(self) -> None:
        section = self.plan()["onoffduty"]
        rows = {row["kind"]: row for row in section["rows"]}
        self.assertEqual(section["form"], "vca")
        self.assertEqual(rows["start"]["before"], "09:15")
        self.assertEqual(rows["start"]["after"], "12:40")
        self.assertEqual(rows["end"]["before"], rows["end"]["after"])


class ApplyTests(TyphoonTestBase):
    def test_apply_requires_the_confirmed_tick(self) -> None:
        self.assertFalse(self.plan(biz_date=FUTURE_DATE, confirmed=False)["can_apply"])
        self.assertIn("Confirmed", self.plan(biz_date=FUTURE_DATE, confirmed=False)["apply_blocked"])
        self.assertTrue(self.plan(biz_date=FUTURE_DATE, confirmed=True)["can_apply"])

    def test_past_days_cannot_be_applied(self) -> None:
        plan = self.plan(biz_date=BIZ_DATE, confirmed=True)
        self.assertFalse(plan["can_apply"])
        self.assertIn("Past days", plan["apply_blocked"])
        with self.assertRaises(ValueError):
            apply_typhoon(self.settings, biz_date=BIZ_DATE, signal_time="11:40")

    def test_apply_writes_the_start_into_the_overtime_sheet(self) -> None:
        result = apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40")

        self.assertEqual(result["apply_result"]["overtime_start"], "12:40")
        rows = load_sheet_rows("overtime", self.settings)["rows"]
        written = [row for row in rows[1:] if str(row[0]).startswith(FUTURE_DATE.isoformat())]
        self.assertEqual(len(written), 1)
        self.assertEqual(str(written[0][1]), "1240")
        self.assertEqual(str(written[0][3]), "颱風")  # 冇填名就淨係「颱風」
        self.assertTrue(result["applied"]["overtime_matches"])

    def test_applied_start_flows_into_the_other_three_sections(self) -> None:
        apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40")
        plan = self.plan(biz_date=FUTURE_DATE, confirmed=True)

        self.assertEqual(plan["overtime_start"], "12:40")
        self.assertEqual(plan["planned_start"], "12:40")  # 加班表已經係新開工，唔會再跳一次
        # 加班表已經係新開工 → 唔再算「遲咗」，報更照返行位表節奏。
        self.assertEqual(plan["report_normal"]["mode"], "grid")
        onoff = {row["kind"]: row for row in plan["onoffduty"]["rows"]}
        self.assertEqual(onoff["start"]["after"], "12:40")

    def test_apply_writes_the_typhoon_name_into_the_overtime_note(self) -> None:
        apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40", name="韋帕")
        rows = load_sheet_rows("overtime", self.settings)["rows"]
        written = next(row for row in rows[1:] if str(row[0]).startswith(FUTURE_DATE.isoformat()))
        self.assertEqual(str(written[3]), "颱風韋帕")

    def test_apply_reshapes_reportnormal_without_touching_the_grid(self) -> None:
        from meal_planner.duty_report import build_plan, load_overlay

        before_grid = load_sheet_rows("schedule_grid", self.settings)["rows"]
        result = apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40", name="韋帕")

        # 行位表一個字都冇郁。
        self.assertEqual(load_sheet_rows("schedule_grid", self.settings)["rows"], before_grid)

        overlay = load_overlay(self.settings, FUTURE_DATE)
        self.assertEqual([item["time"] for item in overlay["extra_slots"]], ["16:40", "20:40"])
        self.assertTrue(overlay["slots"]["VOC@17:15"]["hidden"])
        self.assertEqual(result["apply_result"]["reports_added"], ["16:40", "20:40"])

        # 真 ReportNormal 計劃：報開工跟加班表搬到 11:40，中途嗰個 skip 咗，加開兩個。
        plan = build_plan(self.settings, biz_date=FUTURE_DATE)
        # hidden 唔係 skip：舊時間喺 ReportNormal 度完全唔會出現。
        self.assertEqual([slot["time"] for slot in plan["slots"]], ["12:40", "16:40", "20:40", "21:30"])

    def test_phone_push_drops_the_replaced_reports_but_keeps_the_missed_rows(self) -> None:
        from meal_planner.typhoon import typhoon_grid_rows

        apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40", name="韋帕")
        rows = typhoon_grid_rows(self.settings, FUTURE_DATE, "VOC")
        times = [row["time"] for row in rows]

        # 俾 4 小時表取代咗嗰兩個原本報平安更：唔推落電話。
        self.assertNotIn("17:15", times)
        self.assertIn("16:40", times)
        self.assertIn("20:40", times)
        # 開工之前嘅位照推，但係 disabled——見到先知原本幾點開工。
        missed = next(row for row in rows if row["time"] == "09:15")
        self.assertTrue(missed["disabled"])
        self.assertFalse(any(row["disabled"] for row in rows if row["time"] >= "12:40"))

    def test_apply_on_a_day_off_switches_the_roster_code(self) -> None:
        from meal_planner.duty_form import roster_code_for

        # 先套用一次遲開工，再改成「全日唔使返」——舊嘅加班表同 overlay 都要清走。
        apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="11:40", name="韋帕")
        result = apply_typhoon(
            self.settings, biz_date=FUTURE_DATE, signal_time="20:00",
            day_off_announced=True, name="韋帕",
        )

        self.assertTrue(result["apply_result"]["day_off"])
        self.assertEqual(result["apply_result"]["roster_code"], "TP")
        self.assertEqual(roster_code_for(self.settings, FUTURE_DATE), "TP")
        overtime = load_sheet_rows("overtime", self.settings)["rows"]
        self.assertEqual([r for r in overtime[1:] if str(r[0]).startswith(FUTURE_DATE.isoformat())], [])
        # TP 唔使返工 → 之後再模擬會直接話你知冇嘢要模擬。
        self.assertFalse(result["ok"])
        self.assertIn("nothing to simulate", result["note"])

    def test_apply_rejects_an_unusable_scenario(self) -> None:
        with self.assertRaises(ValueError):
            apply_typhoon(self.settings, biz_date=FUTURE_DATE, signal_time="")


class CurrentTyphoonNameTests(unittest.TestCase):
    """天文台名單：唔會真係出街攞——urlopen 整個假嘅頂上。"""

    def setUp(self) -> None:
        typhoon._tc_cache = None

    def tearDown(self) -> None:
        typhoon._tc_cache = None

    @staticmethod
    def _fake_urlopen(payload: bytes):
        class _Response:
            def read(self) -> bytes:
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> bool:
                return False

        return lambda url, timeout=None: _Response()

    def _with_payload(self, payload: bytes) -> dict:
        import urllib.request

        original = urllib.request.urlopen
        urllib.request.urlopen = self._fake_urlopen(payload)
        try:
            return typhoon.current_typhoon_names(force=True)
        finally:
            urllib.request.urlopen = original

    def test_reads_the_chinese_and_english_names(self) -> None:
        payload = (
            "<TropicalCycloneList><TropicalCyclone>"
            "<TropicalCycloneID>2617</TropicalCycloneID>"
            "<TropicalCycloneChineseName>紅霞</TropicalCycloneChineseName>"
            "<TropicalCycloneEnglishName>NOUL</TropicalCycloneEnglishName>"
            "</TropicalCyclone></TropicalCycloneList>"
        ).encode()
        data = self._with_payload(payload)
        self.assertEqual(data["names"], [{"zh": "紅霞", "en": "NOUL"}])
        self.assertEqual(data["note"], "")

    def test_empty_list_says_so_instead_of_guessing(self) -> None:
        data = self._with_payload(b"<TropicalCycloneList></TropicalCycloneList>")
        self.assertEqual(data["names"], [])
        self.assertIn("No tropical cyclone", data["note"])

    def test_unreachable_observatory_is_reported_not_swallowed(self) -> None:
        import urllib.request

        original = urllib.request.urlopen

        def boom(url, timeout=None):
            raise OSError("no network")

        urllib.request.urlopen = boom
        try:
            data = typhoon.current_typhoon_names(force=True)
        finally:
            urllib.request.urlopen = original
        self.assertEqual(data["names"], [])
        self.assertIn("Could not reach the Observatory", data["note"])


if __name__ == "__main__":
    unittest.main()
