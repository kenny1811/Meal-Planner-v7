"""OnOffDuty hold / send now 嘅純邏輯：5 分鐘四捨五入 + 揀邊個報平安更 slot 齊發。"""

from __future__ import annotations

import unittest
from datetime import datetime

from meal_planner.duty_form import _round_to_5min, pick_report_slot


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
