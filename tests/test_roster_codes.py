"""更碼定義：列咗＝唔使返工；品牌（form／落波後開工）由更碼推，唔入表。"""

from __future__ import annotations

import unittest

from meal_planner.roster_codes import (
    defs_from_rows,
    form_key_for_code,
    is_work_day,
    match_roster_code,
    typhoon_offset_minutes,
)

# 同用戶張表一樣：淨係列非返工 pattern，加一行「其他」做包尾。
DEFS = defs_from_rows([
    {"pattern": "WL*", "label": "週假"},
    {"pattern": "SH*", "label": "勞工假"},
    {"pattern": "AL*", "label": "年假"},
    {"pattern": "SL*", "label": "病假"},
    {"pattern": "SB", "label": "Stand by"},
    {"pattern": "TP", "label": "颱風假"},
    {"pattern": "其他", "label": "返工日"},
])


class WorkDayTests(unittest.TestCase):
    def test_listed_patterns_are_not_work_days(self):
        for code in ("SB", "TP", "WL21", "SH08", "AL3", "SL1"):
            self.assertFalse(is_work_day(DEFS, code), code)

    def test_anything_not_listed_is_a_work_day(self):
        for code in ("PenBM", "VOC", "EleC2", "TSB", "SBA", "XWL", "冇見過"):
            self.assertTrue(is_work_day(DEFS, code), code)

    def test_catch_all_row_never_counts_as_a_match(self):
        self.assertIsNone(match_roster_code(DEFS, "其他更碼"))

    def test_longest_wildcard_wins(self):
        defs = defs_from_rows([{"pattern": "P*", "label": "短"}, {"pattern": "Pen*", "label": "長"}])
        self.assertEqual(match_roster_code(defs, "PenC").label, "長")


class BrandTests(unittest.TestCase):
    def test_v_and_lecole_codes_use_the_vca_form(self):
        for code in ("VOC", "VPP", "VCRA", "VLG", "Lecole", "Lecole Event"):
            self.assertEqual(form_key_for_code(code), "vca", code)

    def test_everything_else_uses_the_other_form(self):
        for code in ("PenBM", "EleC2", "TSB", "IFCS1", "OES2"):
            self.assertEqual(form_key_for_code(code), "other", code)

    def test_typhoon_offset_follows_the_brand(self):
        self.assertEqual(typhoon_offset_minutes("VOC"), 60)
        self.assertEqual(typhoon_offset_minutes("Lecole"), 60)
        self.assertEqual(typhoon_offset_minutes("PenBM"), 60)


if __name__ == "__main__":
    unittest.main()
