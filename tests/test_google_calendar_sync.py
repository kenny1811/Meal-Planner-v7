import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from meal_planner.app import app
from meal_planner.google_calendar_sync import (
    CalendarEventPlan,
    GoogleCalendarSyncConfig,
    OLD_LEAVE_CALENDAR_ID,
    build_roster_calendar_plan,
    check_nonwork_calendar_consistency,
    config_from_env,
    event_body,
    google_calendar_auth_status,
    sync_roster_to_google_calendar,
    _upsert_events,
)
from meal_planner.settings import clear_settings_cache, get_settings
from meal_planner.storage import save_google_calendar_sync_settings


class GoogleCalendarSyncPlanTests(unittest.TestCase):
    def test_builds_shift_and_alarm_events_for_workday_roster_codes(self):
        roster_rows = [["2026年6月 16 SH08 17 Lecole Event 18 SB"]]
        payroll_rows = [
            ["更碼", "開工", "收工", "適用", "優先"],
            ["Lecole event", "0900", "19:00", "", 10],
            ["SH*", "08:00", "16:00", "", 1],
        ]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows)

        self.assertEqual([event.roster_code for event in plan.work_events], ["Lecole Event"])
        self.assertEqual(plan.work_events[0].summary, "Lecole Event")
        self.assertEqual(plan.work_events[0].start_at.isoformat(), "2026-06-17T09:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].summary, "起身")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-06-17T06:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].end_at.isoformat(), "2026-06-17T07:45:00+08:00")
        self.assertEqual([event.roster_code for event in plan.leave_events], ["SH08", "SB"])
        self.assertTrue(plan.leave_events[0].all_day)
        self.assertEqual(plan.leave_events[0].summary, "SH08")

    def test_mtr_door_rows_set_work_event_location(self):
        roster_rows = [["2026年6月 1 TSB 2 Pen 3 Zzz"]]
        payroll_rows = [
            ["更碼", "開工", "收工"],
            ["TS*", "09:00", "18:00"],
            ["Pen*", "10:00", "19:00"],
            ["Zzz", "08:00", "17:00"],
        ]
        mtr_door_rows = [
            ["更碼", "目的地", "上車卡門", "轉車", "轉車卡門", "落車出口"],
            ["Pen*", "半島", "2-3", "直達", "", "尖沙咀 E"],
            ["TS*", "時代廣場", "2-3", "金鐘轉港島綫", "8-4", "銅鑼灣 A"],
        ]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, None, None, mtr_door_rows)

        by_code = {event.roster_code: event for event in plan.work_events}
        self.assertEqual(by_code["TSB"].location, "2-3 8-4")
        self.assertEqual(by_code["Pen"].location, "2-3")
        self.assertEqual(by_code["Zzz"].location, "")
        self.assertEqual(event_body(by_code["TSB"], "Asia/Hong_Kong")["location"], "2-3 8-4")

    def test_non_workday_events_are_all_day_leave_calendar_events(self):
        plan = build_roster_calendar_plan(
            [["2026年6月 1 WL21 2 SB"]],
            [["更碼", "開工", "收工"]],
            leave_calendar_id="leave-calendar",
        )

        self.assertEqual(plan.work_events, [])
        self.assertEqual(plan.alarm_events, [])
        self.assertEqual([event.calendar_id for event in plan.leave_events], ["leave-calendar", "leave-calendar"])
        body = event_body(plan.leave_events[0], "Asia/Hong_Kong")
        self.assertEqual(body["start"], {"date": "2026-06-01"})
        self.assertEqual(body["end"], {"date": "2026-06-02"})
        self.assertNotIn("dateTime", body["start"])

    def test_non_workday_with_wake_row_can_have_wake_alarm(self):
        roster_rows = [["2026年6月 1 SB 2 WL21"]]
        payroll_rows = [["更碼", "開工", "收工"]]
        wake_rows = [["日期", "起身時間", "備註"], ["2026-06-01", "08:15", "appointment"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, None, wake_rows)

        self.assertEqual([event.roster_code for event in plan.leave_events], ["SB", "WL21"])
        self.assertEqual(len(plan.alarm_events), 1)
        self.assertEqual(plan.alarm_events[0].roster_code, "SB")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-06-01T08:15:00+08:00")
        self.assertEqual(plan.alarm_events[0].end_at.isoformat(), "2026-06-01T10:00:00+08:00")

    def test_non_workday_without_wake_row_has_no_wake_alarm(self):
        roster_rows = [["2026年6月 1 SB"]]
        payroll_rows = [["更碼", "開工", "收工"]]
        wake_rows = [["日期", "起身時間", "備註"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, None, wake_rows)

        self.assertEqual([event.roster_code for event in plan.leave_events], ["SB"])
        self.assertEqual(plan.alarm_events, [])

    def test_alarm_three_hours_before_start_can_land_on_previous_date(self):
        roster_rows = [["2026年7月 2 Night"]]
        payroll_rows = [["更碼", "開工", "收工"], ["Night", "01:00", "09:00"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows)

        self.assertEqual(plan.work_events[0].start_at.isoformat(), "2026-07-02T01:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-07-01T22:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].roster_date, date(2026, 7, 2))

    def test_overtime_rows_override_payroll_times_for_work_and_alarm_events(self):
        roster_rows = [["2026年7月 1 Lecole Event"]]
        payroll_rows = [["更碼", "開工", "收工"], ["Lecole Event", "1000", "19:00"]]
        overtime_rows = [["日期", "開工", "收工", "備註"], ["2026-07-01", "11:30", "20:15", "特別更"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, overtime_rows)

        self.assertEqual(plan.work_events[0].start_at.isoformat(), "2026-07-01T11:30:00+08:00")
        self.assertEqual(plan.work_events[0].end_at.isoformat(), "2026-07-01T20:15:00+08:00")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-07-01T08:30:00+08:00")

    def test_overtime_override_uses_header_names_and_report_date_time_formats(self):
        roster_rows = [["2026年7月 1 Lecole Event"]]
        payroll_rows = [["更碼", "開工", "收工"], ["Lecole Event", "1000", "19:00"]]
        overtime_rows = [["備註", "收工", "日期", "開工"], ["特別更", "2015", "01/07/2026 Wed", "1130"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, overtime_rows)

        self.assertEqual(plan.work_events[0].start_at.isoformat(), "2026-07-01T11:30:00+08:00")
        self.assertEqual(plan.work_events[0].end_at.isoformat(), "2026-07-01T20:15:00+08:00")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-07-01T08:30:00+08:00")

    def test_wake_alarm_rows_override_default_alarm_time_only(self):
        roster_rows = [["2026年7月 1 Lecole Event"]]
        payroll_rows = [["更碼", "開工", "收工"], ["Lecole Event", "1000", "19:00"]]
        wake_rows = [["日期", "起身時間", "備註"], ["2026-07-01", "08:15", "早少少"]]

        plan = build_roster_calendar_plan(roster_rows, payroll_rows, None, wake_rows)

        self.assertEqual(plan.work_events[0].start_at.isoformat(), "2026-07-01T10:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].start_at.isoformat(), "2026-07-01T08:15:00+08:00")
        self.assertEqual(plan.alarm_events[0].end_at.isoformat(), "2026-07-01T10:00:00+08:00")
        self.assertEqual(plan.alarm_events[0].description, "起身")

    def test_missing_payroll_time_is_skipped_without_event(self):
        plan = build_roster_calendar_plan([["2026年6月 1 EleB"]], [["更碼", "開工", "收工"]])

        self.assertEqual(plan.work_events, [])
        self.assertEqual(plan.alarm_events, [])
        self.assertEqual(plan.skipped, [{"date": "2026-06-01", "code": "EleB", "reason": "missing_shift_time"}])


class GoogleCalendarSyncRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = os.environ.get("MENU_PROJECT_ROOT")
        os.environ["MENU_PROJECT_ROOT"] = self.tmp.name
        clear_settings_cache()

    def tearDown(self):
        if self.old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = self.old_root
        clear_settings_cache()
        self.tmp.cleanup()

    def test_sync_is_disabled_by_default_and_does_not_build_google_service(self):
        settings = get_settings()

        with patch("meal_planner.google_calendar_sync.load_sheet_rows") as load_rows:
            result = sync_roster_to_google_calendar([["2099年6月 1 EleB"]], settings)

        self.assertEqual(result["status"], "disabled")
        self.assertTrue(result["dry_run"])
        load_rows.assert_not_called()

    def test_enabled_without_write_is_still_dry_run(self):
        settings = get_settings()
        config = GoogleCalendarSyncConfig(
            enabled=True,
            dry_run=True,
            time_zone="Asia/Hong_Kong",
            account_email="kenny1811@gmail.com",
            work_calendar_id="work-calendar",
            alarm_calendar_id="alarm-calendar",
            leave_calendar_id="leave-calendar",
            backup_dir=settings.data_folder / "backup",
            service_account_file=None,
            oauth_client_file=None,
            oauth_token_file=None,
        )
        sheets = {
            "payroll_times": {"rows": [["更碼", "開工", "收工"], ["EleB", "10:45", "21:00"]]},
            "overtime": {"rows": [["日期", "開工", "收工", "備註"]]},
            "wake_alarms": {"rows": [["日期", "起身時間", "備註"]]},
            "mtr_doors": {"rows": [["更碼", "目的地", "上車卡門", "轉車", "轉車卡門", "落車出口"]]},
        }

        with patch("meal_planner.google_calendar_sync.load_sheet_rows", side_effect=lambda key, settings: sheets[key]):
            result = sync_roster_to_google_calendar([["2099年6月 1 EleB"]], settings, config=config)

        self.assertEqual(result["status"], "dry_run")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["work_calendar_id"], "work-calendar")
        self.assertEqual(result["leave_calendar_id"], "leave-calendar")

    def test_enabled_write_without_login_does_not_read_sheets_or_write_google(self):
        settings = get_settings()
        config = GoogleCalendarSyncConfig(
            enabled=True,
            dry_run=False,
            time_zone="Asia/Hong_Kong",
            account_email="kenny1811@gmail.com",
            work_calendar_id="work-calendar",
            alarm_calendar_id="alarm-calendar",
            leave_calendar_id="leave-calendar",
            backup_dir=settings.data_folder / "backup",
            service_account_file=None,
            oauth_client_file=settings.data_folder / "client.json",
            oauth_token_file=settings.data_folder / "token.json",
        )

        with patch("meal_planner.google_calendar_sync.load_sheet_rows") as load_rows:
            result = sync_roster_to_google_calendar([["2099年6月 1 EleB"]], settings, config=config)

        self.assertEqual(result["status"], "not_authenticated")
        self.assertTrue(result["dry_run"])
        load_rows.assert_not_called()

    def test_saved_toggle_enables_runtime_sync_config(self):
        settings = get_settings()
        save_google_calendar_sync_settings({
            "enabled": True,
            "write": True,
            "client_secret_file": "C:/secrets/client.json",
            "token_file": "C:/secrets/token.json",
        })
        config = config_from_env(settings)

        self.assertTrue(config.enabled)
        self.assertFalse(config.dry_run)
        self.assertEqual(str(config.oauth_client_file), "C:\\secrets\\client.json")
        self.assertEqual(str(config.oauth_token_file), "C:\\secrets\\token.json")

    def test_saved_nonwork_calendar_id_is_used_but_old_leave_calendar_is_blocked(self):
        settings = get_settings()
        save_google_calendar_sync_settings({
            "enabled": True,
            "write": True,
            "client_secret_file": "C:/secrets/client.json",
            "token_file": "C:/secrets/token.json",
            "nonwork_calendar_id": "new-nonwork-calendar",
        })
        config = config_from_env(settings)
        self.assertEqual(config.leave_calendar_id, "new-nonwork-calendar")

        save_google_calendar_sync_settings({"nonwork_calendar_id": OLD_LEAVE_CALENDAR_ID})
        config = config_from_env(settings)
        self.assertEqual(config.leave_calendar_id, "")

    def test_env_flags_do_not_override_saved_toggle(self):
        settings = get_settings()
        old_enabled = os.environ.get("MENU_GOOGLE_CALENDAR_SYNC_ENABLED")
        old_write = os.environ.get("MENU_GOOGLE_CALENDAR_SYNC_WRITE")
        try:
            os.environ["MENU_GOOGLE_CALENDAR_SYNC_ENABLED"] = "1"
            os.environ["MENU_GOOGLE_CALENDAR_SYNC_WRITE"] = "1"
            save_google_calendar_sync_settings({"enabled": False, "write": False})

            config = config_from_env(settings)

            self.assertFalse(config.enabled)
            self.assertTrue(config.dry_run)
        finally:
            if old_enabled is None:
                os.environ.pop("MENU_GOOGLE_CALENDAR_SYNC_ENABLED", None)
            else:
                os.environ["MENU_GOOGLE_CALENDAR_SYNC_ENABLED"] = old_enabled
            if old_write is None:
                os.environ.pop("MENU_GOOGLE_CALENDAR_SYNC_WRITE", None)
            else:
                os.environ["MENU_GOOGLE_CALENDAR_SYNC_WRITE"] = old_write

    def test_nonwork_consistency_check_does_not_read_google_for_incomplete_month(self):
        settings = get_settings()
        config = GoogleCalendarSyncConfig(
            enabled=True,
            dry_run=False,
            time_zone="Asia/Hong_Kong",
            account_email="kenny1811@gmail.com",
            work_calendar_id="work-calendar",
            alarm_calendar_id="alarm-calendar",
            leave_calendar_id="nonwork-calendar",
            backup_dir=settings.data_folder / "backup",
            service_account_file=None,
            oauth_client_file=settings.data_folder / "client.json",
            oauth_token_file=settings.data_folder / "token.json",
        )

        with patch("meal_planner.google_calendar_sync._list_events") as list_events:
            result = check_nonwork_calendar_consistency("2099年6月 1 WL01 2 SH01", settings, config=config)

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["complete"])
        list_events.assert_not_called()

    def test_nonwork_consistency_check_reports_last_sh_wl_mismatch(self):
        settings = get_settings()
        config = GoogleCalendarSyncConfig(
            enabled=True,
            dry_run=False,
            time_zone="Asia/Hong_Kong",
            account_email="kenny1811@gmail.com",
            work_calendar_id="work-calendar",
            alarm_calendar_id="alarm-calendar",
            leave_calendar_id="nonwork-calendar",
            backup_dir=settings.data_folder / "backup",
            service_account_file=None,
            oauth_client_file=settings.data_folder / "client.json",
            oauth_token_file=settings.data_folder / "token.json",
        )
        roster_text = "2099年6月 " + " ".join(
            f"{day} {'SH01' if day == 28 else ('WL30' if day == 30 else 'EleB')}"
            for day in range(1, 31)
        )

        def fake_list_events(service, calendar_id, time_min, time_max):
            if calendar_id == OLD_LEAVE_CALENDAR_ID:
                return [
                    {"summary": "SH01", "start": {"date": "2099-06-28"}, "end": {"date": "2099-06-29"}},
                    {"summary": "WL29", "start": {"date": "2099-06-29"}, "end": {"date": "2099-06-30"}},
                ]
            if calendar_id == "nonwork-calendar":
                return [
                    {"summary": "SH01", "start": {"date": "2099-06-28"}, "end": {"date": "2099-06-29"}},
                    {"summary": "WL30", "start": {"date": "2099-06-30"}, "end": {"date": "2099-07-01"}},
                ]
            return []

        with patch("meal_planner.google_calendar_sync.google_calendar_auth_status", return_value={"authenticated": True}), \
             patch("meal_planner.google_calendar_sync.build_google_calendar_service", return_value=object()), \
             patch("meal_planner.google_calendar_sync._list_events", side_effect=fake_list_events):
            result = check_nonwork_calendar_consistency(roster_text, settings, config=config)

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["complete"])
        self.assertTrue(result["items"]["SH"]["consistent"])
        self.assertFalse(result["items"]["WL"]["consistent"])
        self.assertIn("最後WL不一致", result["warnings"][0])
        self.assertNotIn("更表", result["warnings"][0])

    def test_roster_save_endpoint_returns_calendar_sync_status(self):
        client = TestClient(app)

        response = client.post("/api/maint/sheets/roster", json={"rows": [["2026年6月 1 EleB"]]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["google_calendar_sync"]["status"], "disabled")

    def test_roster_save_endpoint_runs_calendar_sync(self):
        client = TestClient(app)

        with patch("meal_planner.app.sync_roster_to_google_calendar", return_value={"status": "synced", "work": {"updated": 1}}) as sync:
            response = client.post("/api/maint/sheets/roster", json={"rows": [["2026年6月 1 EleB"]]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["google_calendar_sync"]["status"], "synced")
        sync.assert_called_once()

    def test_roster_sync_endpoint_runs_calendar_sync_on_demand(self):
        client = TestClient(app)
        client.post("/api/maint/sheets/roster", json={"rows": [["2026年6月 1 EleB"]]})

        with patch("meal_planner.app.sync_roster_to_google_calendar", return_value={"status": "synced", "work": {"updated": 0}}) as sync:
            response = client.post("/api/google-calendar/roster-sync")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "synced")
        sync.assert_called_once()

    def test_upsert_skips_existing_event_when_summary_and_time_match(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                body = kwargs["body"]
                return Execute(self.calls, ("update", kwargs["eventId"], body["summary"], body["start"], body["end"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        event = CalendarEventPlan(
            kind="work",
            calendar_id="work-calendar",
            roster_date=date(2099, 6, 1),
            roster_code="EleB",
            start_at=datetime(2099, 6, 1, 10, 45),
            end_at=datetime(2099, 6, 1, 21, 0),
            summary="EleB",
            description="",
        )
        existing = [
            {
                "id": "existing-id",
                "summary": "EleB",
                "description": "",
                "start": {"dateTime": "2099-06-01T10:45:00"},
                "end": {"dateTime": "2099-06-01T21:00:00"},
                "extendedProperties": {
                    "private": {
                        "source": "meal_planner_roster",
                        "kind": "work",
                        "roster_date": "2099-06-01",
                        "roster_code": "EleB",
                    }
                },
            }
        ]

        counts = _upsert_events(service, "work-calendar", "work", [event], existing, "Asia/Hong_Kong")

        self.assertEqual(counts["updated"], 0)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(service.events_obj.calls, [])

    def test_upsert_updates_existing_event_to_planned_time_when_time_differs(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                body = kwargs["body"]
                return Execute(self.calls, ("update", kwargs["eventId"], body["summary"], body["start"], body["end"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        event = CalendarEventPlan(
            kind="work",
            calendar_id="work-calendar",
            roster_date=date(2099, 6, 1),
            roster_code="EleB",
            start_at=datetime(2099, 6, 1, 10, 45),
            end_at=datetime(2099, 6, 1, 21, 0),
            summary="EleB",
            description="",
        )
        existing = [
            {
                "id": "existing-id",
                "summary": "EleB",
                "start": {"dateTime": "2099-06-01T09:45:00"},
                "end": {"dateTime": "2099-06-01T21:00:00"},
                "extendedProperties": {
                    "private": {
                        "source": "meal_planner_roster",
                        "kind": "work",
                        "roster_date": "2099-06-01",
                        "roster_code": "EleB",
                    }
                },
            }
        ]

        counts = _upsert_events(service, "work-calendar", "work", [event], existing, "Asia/Hong_Kong")

        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(service.events_obj.calls[0][0], "update")
        self.assertEqual(service.events_obj.calls[0][2], "EleB")
        self.assertEqual(service.events_obj.calls[0][3], {"dateTime": "2099-06-01T10:45:00", "timeZone": "Asia/Hong_Kong"})
        self.assertEqual(service.events_obj.calls[0][4], {"dateTime": "2099-06-01T21:00:00", "timeZone": "Asia/Hong_Kong"})

    def test_upsert_does_not_overwrite_manual_same_day_event(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                return Execute(self.calls, ("update", kwargs["eventId"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        event = CalendarEventPlan(
            kind="leave",
            calendar_id="leave-calendar",
            roster_date=date(2099, 6, 1),
            roster_code="WL01",
            start_at=datetime(2099, 6, 1),
            end_at=datetime(2099, 6, 2),
            summary="WL01",
            description="",
            all_day=True,
        )
        existing = [
            {
                "id": "manual-id",
                "summary": "WL company draft",
                "start": {"date": "2099-06-01"},
                "end": {"date": "2099-06-02"},
            }
        ]

        counts = _upsert_events(service, "leave-calendar", "leave", [event], existing, "Asia/Hong_Kong")

        self.assertEqual(counts["updated"], 0)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(counts["skipped_unmanaged"], 1)
        self.assertEqual(service.events_obj.calls, [])

    def test_work_calendar_authoritative_mode_updates_single_manual_same_day_event(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                body = kwargs["body"]
                return Execute(self.calls, ("update", kwargs["eventId"], body["summary"], body["start"], body["end"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        event = CalendarEventPlan(
            kind="work",
            calendar_id="work-calendar",
            roster_date=date(2099, 6, 1),
            roster_code="EleB",
            start_at=datetime(2099, 6, 1, 10, 45),
            end_at=datetime(2099, 6, 1, 21, 0),
            summary="EleB",
            description="",
        )
        existing = [
            {
                "id": "manual-id",
                "summary": "old shift",
                "start": {"dateTime": "2099-06-01T09:45:00"},
                "end": {"dateTime": "2099-06-01T20:00:00"},
            }
        ]

        counts = _upsert_events(
            service,
            "work-calendar",
            "work",
            [event],
            existing,
            "Asia/Hong_Kong",
            authoritative_dates={"2099-06-01"},
            adopt_unmanaged=True,
        )

        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(service.events_obj.calls[0][0], "update")
        self.assertEqual(service.events_obj.calls[0][1], "manual-id")

    def test_work_calendar_authoritative_mode_deletes_manual_event_when_not_planned(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                return Execute(self.calls, ("update", kwargs["eventId"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        existing = [
            {
                "id": "manual-id",
                "summary": "old shift",
                "start": {"dateTime": "2099-06-01T09:45:00"},
                "end": {"dateTime": "2099-06-01T20:00:00"},
            }
        ]

        counts = _upsert_events(
            service,
            "work-calendar",
            "work",
            [],
            existing,
            "Asia/Hong_Kong",
            authoritative_dates={"2099-06-01"},
            adopt_unmanaged=True,
        )

        self.assertEqual(counts["deleted"], 1)
        self.assertEqual(service.events_obj.calls, [("delete", "manual-id")])

    def test_alarm_calendar_authoritative_mode_deletes_old_alarm_when_not_planned(self):
        class Execute:
            def __init__(self, calls, name):
                self.calls = calls
                self.name = name

            def execute(self):
                self.calls.append(self.name)
                return {}

        class Events:
            def __init__(self):
                self.calls = []

            def update(self, **kwargs):
                return Execute(self.calls, ("update", kwargs["eventId"]))

            def insert(self, **kwargs):
                return Execute(self.calls, ("insert", kwargs["body"]["summary"]))

            def delete(self, **kwargs):
                return Execute(self.calls, ("delete", kwargs["eventId"]))

        class Service:
            def __init__(self):
                self.events_obj = Events()

            def events(self):
                return self.events_obj

        service = Service()
        existing = [
            {
                "id": "old-alarm-id",
                "summary": "起身",
                "start": {"dateTime": "2099-06-01T07:45:00"},
                "end": {"dateTime": "2099-06-01T09:30:00"},
                "extendedProperties": {
                    "private": {
                        "source": "meal_planner_roster",
                        "kind": "alarm",
                        "roster_date": "2099-06-01",
                        "roster_code": "EleB",
                    }
                },
            }
        ]

        counts = _upsert_events(
            service,
            "alarm-calendar",
            "alarm",
            [],
            existing,
            "Asia/Hong_Kong",
            authoritative_dates={"2099-06-01"},
            adopt_unmanaged=True,
        )

        self.assertEqual(counts["deleted"], 1)
        self.assertEqual(service.events_obj.calls, [("delete", "old-alarm-id")])


class GoogleCalendarAuthStatusTests(unittest.TestCase):
    def _oauth_config(self, tmp: str) -> GoogleCalendarSyncConfig:
        client = Path(tmp) / "client.json"
        client.write_text("{}", encoding="utf-8")
        token = Path(tmp) / "token.json"
        token.write_text("{}", encoding="utf-8")
        return GoogleCalendarSyncConfig(
            enabled=True,
            dry_run=False,
            time_zone="Asia/Hong_Kong",
            account_email="",
            work_calendar_id="",
            alarm_calendar_id="",
            leave_calendar_id="",
            backup_dir=Path(tmp),
            service_account_file=None,
            oauth_client_file=client,
            oauth_token_file=token,
        )

    def test_auth_status_reports_revoked_when_refresh_fails(self):
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp:
            config = self._oauth_config(tmp)
            fake = MagicMock()
            fake.valid = False
            fake.expired = True
            fake.refresh_token = "x"
            fake.refresh.side_effect = Exception("invalid_grant: Token has been expired or revoked.")
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=fake,
            ):
                res = google_calendar_auth_status(settings, config)
        self.assertFalse(res["authenticated"])
        self.assertEqual(res["status"], "revoked")

    def test_auth_status_connected_when_creds_valid(self):
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp:
            config = self._oauth_config(tmp)
            fake = MagicMock()
            fake.valid = True
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=fake,
            ):
                res = google_calendar_auth_status(settings, config)
        self.assertTrue(res["authenticated"])
        self.assertEqual(res["status"], "connected")

    def test_auth_status_missing_token_file(self):
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp:
            config = self._oauth_config(tmp)
            config.oauth_token_file.unlink()  # 冇 token 檔
            res = google_calendar_auth_status(settings, config)
        self.assertFalse(res["authenticated"])
        self.assertEqual(res["status"], "missing_token")


if __name__ == "__main__":
    unittest.main()
