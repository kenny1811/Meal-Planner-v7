"""OnOffDuty hold / send now 嘅純邏輯：5 分鐘四捨五入 + 揀邊個報平安更 slot 齊發。"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime

from meal_planner.duty_form import (
    _logged,
    _round_to_5min,
    load_onoff_history,
    load_onoff_log,
    pick_report_slot,
    record_onoff_log,
    record_onoff_open,
)
from meal_planner.settings import clear_settings_cache, get_settings


def _slot(hhmm: str, content: str) -> dict[str, str]:
    return {"id": f"VOC@{hhmm}", "time": hhmm, "content": content}


SLOTS = [
    _slot("09:15", "報平安更, 報開工"),
    _slot("13:15", "- 報平安更"),
    _slot("17:15", "- 報平安更 30"),
    _slot("21:30", "報收工, 報平安更"),
]


class RoundTo5MinTest(unittest.TestCase):
    def test_rounds_to_nearest_5(self) -> None:
        cases = {
            "11:30": "11:30",
            "11:32": "11:30",
            "11:33": "11:35",
            "11:37": "11:35",
            "11:38": "11:40",
        }
        for raw, expect in cases.items():
            hour, minute = (int(x) for x in raw.split(":"))
            got = _round_to_5min(datetime(2026, 7, 26, hour, minute, 41))
            self.assertEqual(got.strftime("%H:%M"), expect, raw)

    def test_rounds_up_across_the_hour(self) -> None:
        self.assertEqual(_round_to_5min(datetime(2026, 7, 26, 11, 58)).strftime("%H:%M"), "12:00")
        self.assertEqual(_round_to_5min(datetime(2026, 7, 26, 23, 58)).strftime("%H:%M"), "00:00")


class PickReportSlotTest(unittest.TestCase):
    def test_start_takes_the_first_report_on_duty_slot(self) -> None:
        slot = pick_report_slot(SLOTS, "start")
        self.assertIsNotNone(slot)
        self.assertEqual(slot["time"], "09:15")

    def test_end_takes_the_last_report_off_duty_slot(self) -> None:
        slot = pick_report_slot(SLOTS, "end")
        self.assertIsNotNone(slot)
        self.assertEqual(slot["time"], "21:30")

    def test_missing_keyword_returns_none(self) -> None:
        self.assertIsNone(pick_report_slot([_slot("13:15", "- 報平安更")], "start"))
        self.assertIsNone(pick_report_slot(None, "end"))


if __name__ == "__main__":
    unittest.main()


class LoggedTests(unittest.TestCase):
    """「做咗未」問 history，唔問最新個 status。"""

    HISTORY = [
        {"status": "sent", "time_text": "10:45", "source": "scheduler"},
        {"status": "opened", "time_text": "10:45", "source": "web"},
    ]

    def test_sent_survives_a_later_open(self) -> None:
        # 交完之後再開張 form：個 status 變咗 opened，但交過就係交過，唔會再交多次。
        self.assertTrue(_logged(self.HISTORY, "sent", "10:45"))

    def test_other_status_is_not_invented(self) -> None:
        self.assertFalse(_logged(self.HISTORY, "missed", "10:45"))

    def test_a_new_time_starts_clean(self) -> None:
        # 改咗開工時間（rearm）＝另一件事，舊時間交過唔算數。
        self.assertFalse(_logged(self.HISTORY, "sent", "11:15"))

    def test_empty_history(self) -> None:
        self.assertFalse(_logged([], "sent", "10:45"))


class RecordOpenTests(unittest.TestCase):
    """開過預填連結：淨係留 history 記錄，唔會覆蓋狀態（＝唔會阻到夠鐘自動交）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = os.environ.get("MENU_PROJECT_ROOT")
        os.environ["MENU_PROJECT_ROOT"] = self.tmp.name
        clear_settings_cache()
        self.day = date(2026, 8, 11)

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = self.old_root
        clear_settings_cache()
        self.tmp.cleanup()

    def test_open_leaves_the_status_empty(self) -> None:
        settings = get_settings()
        record_onoff_open(settings, self.day, "start", time_text="10:45")

        self.assertEqual(load_onoff_log(settings, self.day), {})
        rows = load_onoff_history(settings, self.day)["start"]
        self.assertEqual([r["status"] for r in rows], ["opened"])

    def test_open_after_sent_keeps_sent(self) -> None:
        settings = get_settings()
        record_onoff_log(settings, self.day, "start", "sent", time_text="10:45", source="scheduler")
        record_onoff_open(settings, self.day, "start", time_text="10:45")

        self.assertEqual(load_onoff_log(settings, self.day)["start"]["status"], "sent")
        rows = load_onoff_history(settings, self.day)["start"]
        self.assertEqual([r["status"] for r in rows], ["sent", "opened"])
