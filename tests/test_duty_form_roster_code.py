"""_replace_code_in_cell：更表單格 token 手術（現場轉更）。"""

from __future__ import annotations

import unittest

from meal_planner.duty_form import _replace_code_in_cell


class ReplaceCodeInCellTest(unittest.TestCase):
    CELL = "2026年7月 1 SB 2 TSB 3 Lecole Event 4 SB 15 IFCA1 31 WL30"

    def test_replace_simple_code(self):
        out = _replace_code_in_cell(self.CELL, 2, "IFCM2")
        self.assertEqual(out, "2026年7月 1 SB 2 IFCM2 3 Lecole Event 4 SB 15 IFCA1 31 WL30")

    def test_replace_multiword_code(self):
        out = _replace_code_in_cell(self.CELL, 3, "SB")
        self.assertEqual(out, "2026年7月 1 SB 2 TSB 3 SB 4 SB 15 IFCA1 31 WL30")

    def test_replace_with_multiword_code(self):
        out = _replace_code_in_cell(self.CELL, 4, "Lecole Event")
        self.assertEqual(out, "2026年7月 1 SB 2 TSB 3 Lecole Event 4 Lecole Event 15 IFCA1 31 WL30")

    def test_replace_last_day(self):
        out = _replace_code_in_cell(self.CELL, 31, "SB")
        self.assertEqual(out, "2026年7月 1 SB 2 TSB 3 Lecole Event 4 SB 15 IFCA1 31 SB")

    def test_day_not_in_cell_returns_none(self):
        self.assertIsNone(_replace_code_in_cell(self.CELL, 20, "SB"))

    def test_not_a_roster_cell_returns_none(self):
        self.assertIsNone(_replace_code_in_cell("隨便啲字", 2, "SB"))
        self.assertIsNone(_replace_code_in_cell("", 2, "SB"))

    def test_preserves_nbsp_and_spacing(self):
        # 真實資料有 code 後跟住 \xa0（例：「SB\xa0」）——手術只換 code token，\xa0 保留。
        cell = "2026年2月 6 WL05 7 SB\xa0 8 FBPA"
        out = _replace_code_in_cell(cell, 7, "VPP")
        self.assertEqual(out, "2026年2月 6 WL05 7 VPP\xa0 8 FBPA")
        # 冇改嘅日子 byte-for-byte 不變。
        out2 = _replace_code_in_cell(cell, 8, "TSA")
        self.assertEqual(out2, "2026年2月 6 WL05 7 SB\xa0 8 TSA")

    def test_double_spaces_elsewhere_untouched(self):
        cell = "2026年7月  1 SB   2 TSB"
        out = _replace_code_in_cell(cell, 1, "VOC")
        self.assertEqual(out, "2026年7月  1 VOC   2 TSB")


if __name__ == "__main__":
    unittest.main()
