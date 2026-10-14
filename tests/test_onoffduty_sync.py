"""OnOffDuty edit -> Form/report times -> daily phone export, using temporary SQLite and mocked HTTP."""

import os
import tempfile
import threading
import unittest
from datetime import date, datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from meal_planner import app as app_module, duty_form, duty_report, schedule_grid_sync
from meal_planner.maintenance_db import load_sheet_rows, save_sheet_rows, save_roster_code_definitions
from meal_planner.settings import clear_settings_cache, get_settings

HK = ZoneInfo("Asia/Hong_Kong")
DAY = date(2026, 10, 3)
GRID = [
    ["更碼", "時間", "內容", "時長", "生效日期"],
    ["VOC", "09:15", "報開工, 報平安更", "240", "2026-01-01"],
    ["VOC", "13:15", "- 報平安更", "", "2026-01-01"],
    ["VOC", "21:30", "報收工, 報平安更", "", "2026-01-01"],
    ["EleA", "08:00", "報開工, 報平安更", "", "2026-01-01"],
    ["EleA", "20:00", "報收工, 報平安更", "", "2026-01-01"],
]


class FixedDateTime(datetime):
    current = datetime(2026, 10, 3, 12, tzinfo=HK)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


class OnOffDutySyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"MENU_PROJECT_ROOT": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        clear_settings_cache()
        self.addCleanup(clear_settings_cache)
        self.settings = get_settings()
        FixedDateTime.current = datetime(2026, 10, 3, 12, tzinfo=HK)
        for module in (duty_form, duty_report, schedule_grid_sync, app_module):
            clock = patch.object(module, "datetime", FixedDateTime)
            clock.start()
            self.addCleanup(clock.stop)
        for key, rows in {
            "schedule_grid": GRID,
            "roster": [["更表"], ["2026年10月 3 VOC 4 VOC 5 VOC"]],
            "overtime": [["日期", "開工", "收工", "備註"]],
            "payroll_times": [["更碼", "開始時間", "結束時間", "適用日"], ["VOC", "09:30", "21:00", "每日"]],
            "public_holidays": [["日期"]],
        }.items():
            save_sheet_rows(key, rows, self.settings)
        save_roster_code_definitions([{"pattern": "其他", "label": "返工日"}], self.settings)
        duty_report.save_config(self.settings, {"auto_send": True, "mapping": {"VOC": "test", "EleA": "test"}})

    def edit(self, **values):
        body = app_module.OnOffDutyOverrideRequest(date_iso=DAY.isoformat(), **values)
        with patch("meal_planner.phone_push.push_schedule_grid", return_value={"status": "ok", "plan_date": DAY.isoformat()}) as push:
            plan = app_module.api_onoffduty_override(body)
        push.assert_called_once_with()
        return plan

    def test_both_edits_follow_onoff_and_leave_master_and_next_shift_unchanged(self):
        duty_report.save_overlay(self.settings, DAY, {"slots": {
            "VOC@09:15": {"time": "11:00", "group": "custom"},
            "VOC@21:30": {"time": "23:00"},
        }})
        self.edit(start="0945")
        plan = self.edit(end="2530")
        self.assertEqual([a["time"] for a in plan["actions"]], ["09:45", "25:30"])
        report = duty_report.build_plan(self.settings, biz_date=DAY)
        self.assertEqual([s["time"] for s in report["slots"]], ["09:45", "13:15", "25:30"])
        self.assertEqual(report["slots"][0]["group"], "custom")

        # After original off-duty time, keep this business day until its amended 25:30.
        FixedDateTime.current = datetime(2026, 10, 4, 0, 30, tzinfo=HK)
        exported = schedule_grid_sync.build_schedule_grid_all_variants_export()
        self.assertEqual(exported["target_date"], DAY.isoformat())
        current = next(v for v in exported["variants"] if v["is_current"])
        other = next(v for v in exported["variants"] if not v["is_current"])
        self.assertEqual([a["time"] for a in current["alarms"]], ["09:45", "13:15", "25:30"])
        self.assertEqual([a["time"] for a in other["alarms"]], ["08:00", "20:00"])
        self.assertEqual(load_sheet_rows("schedule_grid", self.settings)["rows"], GRID)

        FixedDateTime.current = datetime(2026, 10, 4, 8, tzinfo=HK)
        exported = schedule_grid_sync.build_schedule_grid_all_variants_export()
        current = next(v for v in exported["variants"] if v["is_current"])
        self.assertEqual(exported["target_date"], "2026-10-04")
        self.assertEqual([a["time"] for a in current["alarms"]], ["09:15", "13:15", "21:30"])

    def test_reset_follows_master_even_with_legacy_report_override(self):
        duty_report.save_overlay(self.settings, DAY, {"slots": {"VOC@21:30": {"time": "23:00"}}})
        self.edit(end="22:15")
        plan = self.edit(end="")
        self.assertEqual(plan["end"], "21:30")
        self.assertEqual(duty_report.build_plan(self.settings, biz_date=DAY)["slots"][-1]["time"], "21:30")

    def test_form_links_and_actual_post_fields_follow_both_edited_times(self):
        FixedDateTime.current = datetime(2026, 10, 3, 8, tzinfo=HK)
        original = duty_form.build_day_plan(self.settings, biz_date=DAY)
        self.edit(start="0945")
        plan = self.edit(end="2530")
        form = duty_form.FORMS[plan["form"]]
        cases = (
            ("start", "09:45", form.entry_start, form.entry_end, "9", "45"),
            ("end", "25:30", form.entry_end, form.entry_start, "1", "30"),
        )
        for before, action, (kind, display, entry, blank, hour, minute) in zip(
                original["actions"], plan["actions"], cases):
            with self.subTest(kind=kind):
                self.assertEqual(action["time"], display)
                self.assertNotEqual(action["url"], before["url"])
                query = parse_qs(urlsplit(action["url"]).query)
                self.assertEqual(query[f"{entry}_hour"], [hour])
                self.assertEqual(query[f"{entry}_minute"], [minute])
                self.assertNotIn(f"{blank}_hour", query)

        # Keep the real submit_form encoder: intercept only HTTP so the exact Form
        # payload is checked without submitting anything to Google.
        with patch("urllib.request.urlopen") as http:
            http.return_value.__enter__.return_value.status = 200
            FixedDateTime.current = datetime(2026, 10, 3, 9, 15, tzinfo=HK)
            self.assertEqual(duty_form.process_due_actions(self.settings), datetime(2026, 10, 3, 9, 45, tzinfo=HK))
            http.assert_not_called()
            FixedDateTime.current = datetime(2026, 10, 3, 9, 45, tzinfo=HK)
            duty_form.process_due_actions(self.settings)
            self.assertEqual(http.call_count, 1)
            FixedDateTime.current = datetime(2026, 10, 3, 21, 30, tzinfo=HK)
            self.assertEqual(duty_form.process_due_actions(self.settings), datetime(2026, 10, 4, 1, 30, tzinfo=HK))
            self.assertEqual(http.call_count, 1)
            FixedDateTime.current = datetime(2026, 10, 4, 1, 30, tzinfo=HK)
            duty_form.process_due_actions(self.settings)
            duty_form.process_due_actions(self.settings)
            self.assertEqual(http.call_count, 2)
            for call, (kind, display, entry, blank, hour, minute) in zip(http.call_args_list, cases):
                with self.subTest(submission=kind):
                    request = call.args[0]
                    self.assertEqual(request.get_method(), "POST")
                    self.assertTrue(request.full_url.endswith(f"/{form.form_id}/formResponse"))
                    fields = parse_qs(request.data.decode("utf-8"))
                    self.assertEqual(fields[f"{entry}_hour"], [hour])
                    self.assertEqual(fields[f"{entry}_minute"], [minute])
                    self.assertEqual(fields[f"{form.entry_date}_day"], ["3"])
                    self.assertNotIn(f"{blank}_hour", fields)
                    self.assertEqual(duty_form.load_onoff_log(self.settings, DAY)[kind]["time_text"], display)

    def test_other_weekday_finish_cannot_leave_an_old_alarm_enabled(self):
        grid = [list(row) for row in GRID]
        grid[3][2] = "報收工, 報平安更 (日-四)"
        grid.append(["VOC", "22:00", "報收工, 報平安更 (五六)", "", "2026-01-01"])
        save_sheet_rows("schedule_grid", grid, self.settings)
        self.edit(end="23:00")  # Saturday uses only the Fri/Sat finish row.
        exported = schedule_grid_sync.build_schedule_grid_all_variants_export()
        current = next(v for v in exported["variants"] if v["is_current"])
        ends = [a for a in current["alarms"] if "報收工" in a["label"]]
        self.assertEqual([(a["time"], a["disabled"]) for a in ends], [("21:30", True), ("23:00", False)])
        self.assertEqual(load_sheet_rows("schedule_grid", self.settings)["rows"], grid)

    def test_old_report_clients_cannot_edit_onoff_times(self):
        before = duty_report.load_overlay(self.settings, DAY)
        for slot_id in ("VOC@09:15", "VOC@21:30"):
            for value in ("22:00", ""):
                with self.subTest(slot=slot_id, time=value), self.assertRaisesRegex(ValueError, "OnOffDuty"):
                    duty_report.apply_override(self.settings, biz_date=DAY, slot_patch={"id": slot_id, "time": value})
        self.assertEqual(duty_report.load_overlay(self.settings, DAY), before)

    def test_report_sent_also_locks_corresponding_onoff_editor_and_api(self):
        duty_report.record_log(self.settings, DAY, "VOC@09:15", "sent")
        plan = duty_form.build_day_plan(self.settings, biz_date=DAY)
        self.assertFalse(plan["actions"][0]["time_editable"])
        self.assertTrue(plan["actions"][1]["time_editable"])
        with patch("meal_planner.duty_form.save_sheet_rows") as save:
            with self.assertRaisesRegex(ValueError, "已 sent"):
                duty_form.set_time_override(self.settings, DAY, start="10:00")
            save.assert_not_called()
        self.edit(end="22:15")

    def test_new_time_rearms_both_schedulers_and_each_sends_once(self):
        FixedDateTime.current = datetime(2026, 10, 3, 22, tzinfo=HK)
        duty_form.record_onoff_log(self.settings, DAY, "end", "missed", time_text="21:30")
        duty_report.record_log(self.settings, DAY, "VOC@21:30", "missed")
        self.edit(end="23:30")
        self.assertNotIn("end", duty_form.load_onoff_log(self.settings, DAY))
        self.assertNotIn("VOC@21:30", duty_report.load_log(self.settings, DAY))
        with patch("meal_planner.whatsapp_send.send_group_message") as whatsapp, patch("meal_planner.duty_form.submit_form") as form:
            self.assertEqual(duty_report.process_due_slots(self.settings), datetime(2026, 10, 3, 23, 30, tzinfo=HK))
            self.assertEqual(duty_form.process_due_actions(self.settings), datetime(2026, 10, 3, 23, 30, tzinfo=HK))
            whatsapp.assert_not_called()
            form.assert_not_called()
            FixedDateTime.current = datetime(2026, 10, 3, 23, 30, tzinfo=HK)
            for _ in range(2):
                duty_report.process_due_slots(self.settings)
                duty_form.process_due_actions(self.settings)
            whatsapp.assert_called_once()
            form.assert_called_once()
            self.assertEqual(form.call_args.kwargs["end"].strftime("%H:%M"), "23:30")

    def test_phone_failure_keeps_saved_time_and_reports_failure(self):
        with patch("meal_planner.phone_push.push_schedule_grid", return_value={"status": "error", "detail": "offline"}):
            plan = app_module.api_onoffduty_override(app_module.OnOffDutyOverrideRequest(date_iso=DAY.isoformat(), end="22:15"))
        self.assertEqual(plan["end"], "22:15")
        self.assertEqual(plan["phone_sync"]["status"], "error")

    def test_phone_importing_another_date_is_not_reported_as_synced(self):
        with patch("meal_planner.phone_push.push_schedule_grid", return_value={"status": "ok", "plan_date": "2026-10-04"}):
            plan = app_module.api_onoffduty_override(app_module.OnOffDutyOverrideRequest(date_iso=DAY.isoformat(), end="22:15"))
        self.assertEqual(plan["phone_sync"]["status"], "different_date")
        self.assertEqual(plan["phone_sync"]["plan_date"], "2026-10-04")

    def test_stale_overdue_snapshot_cannot_overwrite_a_rescheduled_slot(self):
        stale = {"date_iso": DAY.isoformat(), "auto_send": True, "mode": "auto", "slots": [
            {"id": "VOC@21:30", "time": "21:30", "status": "overdue", "message": "test", "group": "test"},
        ]}
        updated = {**stale, "slots": [{**stale["slots"][0], "time": "23:30", "status": "pending"}]}
        with patch.object(duty_report, "build_plan", side_effect=[stale, updated]), patch.object(duty_report, "record_log") as record:
            duty_report.process_due_slots(self.settings)
        record.assert_not_called()

    def test_form_scheduler_does_not_wait_for_a_manual_form_request(self):
        held = threading.Event()
        release = threading.Event()

        def manual_request():
            with duty_form._ACTION_LOCK:
                held.set()
                release.wait(5)

        worker = threading.Thread(target=manual_request)
        worker.start()
        try:
            self.assertTrue(held.wait(2))
            with patch.object(duty_form, "_process_due_actions") as send:
                next_at = duty_form.process_due_actions(self.settings)
            send.assert_not_called()
            self.assertLess((next_at - FixedDateTime.current).total_seconds(), 1)
        finally:
            release.set()
            worker.join(2)

    def test_phone_push_waits_outside_form_and_report_locks(self):
        locks_free = []

        def check_locks():
            for lock in (duty_form._ACTION_LOCK, duty_report._ACTION_LOCK):
                acquired = lock.acquire(blocking=False)
                locks_free.append(acquired)
                if acquired:
                    lock.release()

        def push():
            worker = threading.Thread(target=check_locks)
            worker.start()
            worker.join(2)
            return {"status": "ok", "plan_date": DAY.isoformat()}

        with patch("meal_planner.phone_push.push_schedule_grid", side_effect=push):
            app_module.api_onoffduty_override(app_module.OnOffDutyOverrideRequest(date_iso=DAY.isoformat(), start="10:00"))
        self.assertEqual(locks_free, [True, True])

    def test_response_is_locked_if_sent_while_waiting_for_phone_import(self):
        def push():
            duty_form.record_onoff_log(self.settings, DAY, "start", "sent", time_text="10:00")
            return {"status": "ok", "plan_date": DAY.isoformat()}

        with patch("meal_planner.phone_push.push_schedule_grid", side_effect=push):
            plan = app_module.api_onoffduty_override(app_module.OnOffDutyOverrideRequest(date_iso=DAY.isoformat(), start="10:00"))
        self.assertFalse(plan["actions"][0]["time_editable"])
        self.assertEqual(plan["actions"][0]["status"], "sent")
