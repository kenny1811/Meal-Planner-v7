"""報更純邏輯測試：30 小時制、星期標記、slot 推導、segments／overlay。"""

from __future__ import annotations

import unittest
import os
import tempfile
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from meal_planner.duty_report import (
    GRACE_MINUTES,
    apply_override,
    load_log,
    record_log,
    _slot_runtime_status,
    business_date,
    compute_slots,
    normalize_hhmm,
    normalize_segments,
    safe_slots_for_code,
    weekday_allows,
)
from meal_planner.schedule_grid import ScheduleRow
from meal_planner.settings import clear_settings_cache, get_settings

HK = ZoneInfo("Asia/Hong_Kong")


def _row(code: str, hhmm: str, content: str, effective: date | None = None) -> ScheduleRow:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return ScheduleRow(code=code, t=time(hour, minute), content=content, duration_min=None, effective_from=effective)


VOC_ROWS = [
    _row("VOC", "09:15", "報平安更, 報開工"),
    _row("VOC", "13:15", "- 報平安更"),
    _row("VOC", "17:15", "- 報平安更 30"),
    _row("VOC", "21:30", "報收工, 報平安更"),
    _row("VOC", "12:30", "食飯 60"),
]
PENA_ROWS = [
    _row("PenA", "09:30", "報開工, B/F 60, 等IC開門, 報平安更 20"),
    _row("PenA", "13:30", "報平安更 75"),
    _row("PenA", "17:30", "報平安更 / G/F 60"),
]
FBPB_ROWS = [
    _row("FBPB", "21:30", "報平安更, 報收工 (日-四) 30"),
    _row("FBPB", "22:00", "報平安更, 報收工 (五六)"),
]
ALL_ROWS = VOC_ROWS + PENA_ROWS + FBPB_ROWS

MAPPING = {"VOC": "VCA共同體", "PenA": "半島報更群組"}
TEMPLATE = "{code} SAPP1801 報平安更正常"


class TestSentTimeOverride(unittest.TestCase):
    def test_failed_resend_cannot_unlock_a_sent_time(self):
        day = date(2026, 10, 3)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MENU_PROJECT_ROOT": tmp}):
            clear_settings_cache()
            try:
                settings = get_settings()
                record_log(settings, day, "VOC@21:30", "sent", message="original")
                for status in ("failed", "missed"):
                    record_log(settings, day, "VOC@21:30", status, message="retry")
                    self.assertEqual(load_log(settings, day)["VOC@21:30"]["status"], "sent")
                    with self.assertRaisesRegex(ValueError, "已 sent"):
                        apply_override(settings, biz_date=day, slot_patch={"id": "VOC@21:30", "time": "22:00"})
                self.assertEqual(load_log(settings, day)["VOC@21:30"]["message"], "original")
            finally:
                clear_settings_cache()

    def test_sent_start_and_end_reject_changes_and_reset_before_any_write(self):
        day = date(2026, 10, 3)
        with patch("meal_planner.duty_report._now", return_value=datetime(2026, 10, 3, 12, tzinfo=HK)), \
             patch("meal_planner.duty_report.load_log", return_value={"VOC@09:15": {"status": "sent"}, "VOC@21:30": {"status": "sent"}}), \
             patch("meal_planner.duty_report.save_overlay") as save, \
             patch("meal_planner.duty_report.record_event") as event:
            for slot_id in ("VOC@09:15", "VOC@21:30"):
                for value in ("22:00", ""):
                    with self.subTest(slot=slot_id, time=value), self.assertRaisesRegex(ValueError, "已 sent"):
                        apply_override(None, biz_date=day, slot_patch={"id": slot_id, "time": value})
            save.assert_not_called()
            event.assert_not_called()

    def test_unsent_midshift_time_still_saves(self):
        day = date(2026, 10, 3)
        with patch("meal_planner.duty_report._now", return_value=datetime(2026, 10, 3, 12, tzinfo=HK)), \
             patch("meal_planner.duty_report.load_log", return_value={}), \
             patch("meal_planner.duty_report.load_overlay", return_value={}), \
             patch("meal_planner.duty_report.save_overlay") as save, \
             patch("meal_planner.duty_report.record_event"), \
             patch("meal_planner.duty_report.build_plan", return_value={}):
            apply_override(None, biz_date=day, slot_patch={"id": "VOC@13:15", "time": "1400"})
            self.assertEqual(save.call_args.args[2]["slots"]["VOC@13:15"]["time"], "14:00")


class TestBusinessDate(unittest.TestCase):
    def test_after_6am_is_same_day(self):
        self.assertEqual(business_date(datetime(2026, 7, 12, 9, 0, tzinfo=HK)), date(2026, 7, 12))

    def test_before_6am_is_previous_day(self):
        self.assertEqual(business_date(datetime(2026, 7, 13, 0, 21, tzinfo=HK)), date(2026, 7, 12))
        self.assertEqual(business_date(datetime(2026, 7, 13, 5, 59, tzinfo=HK)), date(2026, 7, 12))
        self.assertEqual(business_date(datetime(2026, 7, 13, 6, 0, tzinfo=HK)), date(2026, 7, 13))


class TestWeekdayMarkers(unittest.TestCase):
    def test_sun_to_thu_marker(self):
        sunday = date(2026, 7, 12)
        friday = date(2026, 7, 17)
        self.assertTrue(weekday_allows("報平安更, 報收工 (日-四) 30", sunday))
        self.assertFalse(weekday_allows("報平安更, 報收工 (日-四) 30", friday))

    def test_fri_sat_marker(self):
        saturday = date(2026, 7, 18)
        monday = date(2026, 7, 13)
        self.assertTrue(weekday_allows("報平安更, 報收工 (五六)", saturday))
        self.assertFalse(weekday_allows("報平安更, 報收工 (五六)", monday))

    def test_no_marker_always_allows(self):
        self.assertTrue(weekday_allows("報平安更", date(2026, 7, 12)))


class TestSafeSlots(unittest.TestCase):
    def test_voc_four_slots_sorted(self):
        slots = safe_slots_for_code(ALL_ROWS, "VOC", date(2026, 7, 12))
        self.assertEqual([t for t, _ in slots], ["09:15", "13:15", "17:15", "21:30"])

    def test_non_safe_rows_excluded(self):
        slots = safe_slots_for_code(ALL_ROWS, "VOC", date(2026, 7, 12))
        self.assertTrue(all("報平安更" in content for _, content in slots))

    def test_fbpb_weekday_split(self):
        sunday = date(2026, 7, 12)
        saturday = date(2026, 7, 18)
        self.assertEqual([t for t, _ in safe_slots_for_code(ALL_ROWS, "FBPB", sunday)], ["21:30"])
        self.assertEqual([t for t, _ in safe_slots_for_code(ALL_ROWS, "FBPB", saturday)], ["22:00"])

    def test_unknown_code_empty(self):
        self.assertEqual(safe_slots_for_code(ALL_ROWS, "SB", date(2026, 7, 12)), [])


class TestNormalizeHhmm(unittest.TestCase):
    def test_accepts_flexible_formats(self):
        self.assertEqual(normalize_hhmm("09:16"), "09:16")
        self.assertEqual(normalize_hhmm("9:16"), "09:16")
        self.assertEqual(normalize_hhmm("0916"), "09:16")
        self.assertEqual(normalize_hhmm("916"), "09:16")

    def test_early_morning_normalises_to_the_30_hour_form(self):
        self.assertEqual(normalize_hhmm("2416"), "24:16")
        self.assertEqual(normalize_hhmm("29:59"), "29:59")
        self.assertEqual(normalize_hhmm("0016"), "24:16")
        self.assertEqual(normalize_hhmm("05:59"), "29:59")

    def test_invalid_rejected(self):
        self.assertEqual(normalize_hhmm("abc"), "")
        self.assertEqual(normalize_hhmm("30:00"), "")
        self.assertEqual(normalize_hhmm("12:75"), "")
        self.assertEqual(normalize_hhmm(""), "")


class TestSegments(unittest.TestCase):
    def test_normalize_sorts_and_drops_invalid(self):
        segs = normalize_segments([
            {"from": "14:00", "code": "PenA"},
            {"from": "00:00", "code": "VOC"},
            {"from": "bad", "code": "X"},
            {"code": ""},
        ])
        # 舊資料寫 "00:00" ＝ 全日，30 小時制之下即係由 06:00 起。
        self.assertEqual(segs, [{"from": "06:00", "code": "VOC"}, {"from": "14:00", "code": "PenA"}])

    def test_whole_day_single_code(self):
        slots = compute_slots(ALL_ROWS, [{"from": "00:00", "code": "VOC"}], date(2026, 7, 12), MAPPING, TEMPLATE, {})
        self.assertEqual(len(slots), 4)
        self.assertEqual(slots[0]["message"], "VOC SAPP1801 報平安更正常")
        self.assertEqual(slots[0]["group"], "VCA共同體")

    def test_mid_day_code_change(self):
        segments = [{"from": "00:00", "code": "VOC"}, {"from": "13:00", "code": "PenA"}]
        slots = compute_slots(ALL_ROWS, segments, date(2026, 7, 12), MAPPING, TEMPLATE, {})
        self.assertEqual(
            [(s["code"], s["time"]) for s in slots],
            [("VOC", "09:15"), ("PenA", "13:30"), ("PenA", "17:30")],
        )
        self.assertEqual(slots[1]["group"], "半島報更群組")

    def test_after_midnight_slot_survives_the_30_hour_window(self):
        # 30 小時制：凌晨 01:30 嘅報平安更係 25:30，要留喺由 06:00 起計嘅全日 segment 入面。
        rows = [_row("TSB", "10:45", "報平安更"), _row("TSB", "01:30", "報收工, 報平安更")]
        slots = compute_slots(rows, [{"from": "00:00", "code": "TSB"}], date(2026, 7, 12), {"TSB": "時代廣場"}, TEMPLATE, {})
        self.assertEqual([s["time"] for s in slots], ["10:45", "25:30"])

    def test_overtime_overrides_on_off_slots_only(self):
        """加班表：開工 override 套「報開工」slot、收工 override 套「報收工」slot，中間 slot 唔郁。"""
        slots = compute_slots(
            ALL_ROWS, [{"from": "00:00", "code": "VOC"}], date(2026, 7, 12), MAPPING, TEMPLATE, {},
            overtime=(time(9, 0), time(22, 15)),
        )
        by_id = {s["id"]: s for s in slots}
        self.assertEqual(by_id["VOC@09:15"]["time"], "09:00")
        self.assertTrue(by_id["VOC@09:15"]["ot_override"])
        self.assertEqual(by_id["VOC@13:15"]["time"], "13:15")
        self.assertFalse(by_id["VOC@13:15"]["ot_override"])
        self.assertEqual(by_id["VOC@21:30"]["time"], "22:15")
        # slot id 保持行位表原時間，overlay 對應唔會甩
        self.assertIn("VOC@21:30", by_id)

    def test_legacy_onoff_panel_time_cannot_override_onoff_duty(self):
        overrides = {"VOC@09:15": {"time": "10:00"}, "VOC@21:30": {"time": "23:00"}}
        slots = compute_slots(
            ALL_ROWS, [{"from": "00:00", "code": "VOC"}], date(2026, 7, 12), MAPPING, TEMPLATE, overrides,
            overtime=(None, time(22, 15)),
        )
        by_id = {s["id"]: s for s in slots}
        self.assertEqual(by_id["VOC@09:15"]["time"], "09:15")
        self.assertEqual(by_id["VOC@21:30"]["time"], "22:15")
        self.assertFalse(by_id["VOC@09:15"]["time_editable"])
        self.assertFalse(by_id["VOC@21:30"]["time_editable"])

    def test_slot_overrides_skip_time_group(self):
        overrides = {
            "VOC@09:15": {"skip": True},
            "VOC@13:15": {"time": "13:45"},
            "VOC@17:15": {"group": "Testing Group"},
        }
        slots = compute_slots(ALL_ROWS, [{"from": "00:00", "code": "VOC"}], date(2026, 7, 12), MAPPING, TEMPLATE, overrides)
        by_id = {s["id"]: s for s in slots}
        self.assertTrue(by_id["VOC@09:15"]["skipped"])
        self.assertEqual(by_id["VOC@13:15"]["time"], "13:45")
        self.assertEqual(by_id["VOC@13:15"]["original_time"], "13:15")
        self.assertEqual(by_id["VOC@17:15"]["group"], "Testing Group")


class TestRuntimeStatus(unittest.TestCase):
    def _slot(self, hhmm: str, skipped: bool = False) -> dict:
        return {"id": f"VOC@{hhmm}", "time": hhmm, "skipped": skipped}

    def test_pending_due_overdue(self):
        biz = date(2026, 7, 12)
        base = datetime(2026, 7, 12, 13, 15, tzinfo=HK)
        self.assertEqual(_slot_runtime_status(self._slot("13:15"), None, "auto", biz, base - timedelta(minutes=1), HK), "pending")
        self.assertEqual(_slot_runtime_status(self._slot("13:15"), None, "auto", biz, base + timedelta(minutes=1), HK), "due")
        self.assertEqual(
            _slot_runtime_status(self._slot("13:15"), None, "auto", biz, base + timedelta(minutes=GRACE_MINUTES + 1), HK),
            "overdue",
        )

    def test_sent_and_skip_and_stop_precedence(self):
        biz = date(2026, 7, 12)
        now = datetime(2026, 7, 12, 14, 0, tzinfo=HK)
        self.assertEqual(_slot_runtime_status(self._slot("13:15"), {"status": "sent"}, "auto", biz, now, HK), "sent")
        self.assertEqual(_slot_runtime_status(self._slot("13:15", skipped=True), None, "auto", biz, now, HK), "skipped")
        self.assertEqual(_slot_runtime_status(self._slot("13:15"), None, "stop", biz, now, HK), "stopped")

    def test_failed_within_grace_retries_as_due(self):
        biz = date(2026, 7, 12)
        now = datetime(2026, 7, 12, 13, 20, tzinfo=HK)
        self.assertEqual(_slot_runtime_status(self._slot("13:15"), {"status": "failed"}, "auto", biz, now, HK), "due")

    def test_early_morning_slot_belongs_to_next_calendar_day(self):
        biz = date(2026, 7, 12)
        now = datetime(2026, 7, 13, 0, 30, tzinfo=HK)
        # 01:00 slot（30 小時制 25:00）真實時刻係 13/7 01:00，00:30 仲係 pending。
        self.assertEqual(_slot_runtime_status(self._slot("01:00"), None, "auto", biz, now, HK), "pending")


if __name__ == "__main__":
    unittest.main()
