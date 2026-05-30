import unittest

from meal_planner.indicators import (
    DayIndicatorProfile,
    IndicatorKind,
    NUTRIENT_KEYS,
    indicator_from_json,
    indicator_to_json,
    parse_indicator_cell,
    profile_from_json_map,
)


class IndicatorTests(unittest.TestCase):
    def test_parse_range_upper_lower_fat_pct_and_single_value(self):
        self.assertEqual(parse_indicator_cell("1800-1700").kind, IndicatorKind.RANGE)
        self.assertEqual((parse_indicator_cell("1800-1700").lo, parse_indicator_cell("1800-1700").hi), (1700.0, 1800.0))

        upper = parse_indicator_cell("< 40g")
        assert upper is not None
        self.assertEqual((upper.kind, upper.hi), (IndicatorKind.UPPER_ONLY, 40.0))

        lower = parse_indicator_cell("> 1200mg")
        assert lower is not None
        self.assertEqual((lower.kind, lower.lo), (IndicatorKind.LOWER_ONLY, 1200.0))

        fat = parse_indicator_cell("< 27.5% kcal")
        assert fat is not None
        self.assertEqual((fat.kind, fat.fat_pct), (IndicatorKind.FAT_PCT, 0.275))

        single = parse_indicator_cell("42")
        assert single is not None
        self.assertEqual((single.kind, single.lo, single.hi), (IndicatorKind.RANGE, 42.0, 42.0))

    def test_parse_indicator_cell_ignores_blank_dash_and_unparseable_values(self):
        self.assertIsNone(parse_indicator_cell(None))
        self.assertIsNone(parse_indicator_cell(""))
        self.assertIsNone(parse_indicator_cell("-"))
        self.assertIsNone(parse_indicator_cell("abc"))

    def test_day_indicator_profile_pads_or_truncates_to_nutrient_keys(self):
        profile = DayIndicatorProfile.from_row_cells(["1-2", "<3"])

        self.assertEqual(len(profile.nutrients), len(NUTRIENT_KEYS))
        self.assertEqual(profile.nutrients[0].kind, IndicatorKind.RANGE)
        self.assertEqual(profile.nutrients[1].kind, IndicatorKind.UPPER_ONLY)
        self.assertTrue(all(x is None for x in profile.nutrients[2:]))

    def test_indicator_json_round_trip_and_profile_map_order(self):
        parsed = parse_indicator_cell("> 800mg")
        assert parsed is not None
        self.assertEqual(indicator_from_json(indicator_to_json(parsed)), parsed)

        profile = profile_from_json_map({"calcium_mg": indicator_to_json(parsed), "unknown": {"kind": "range"}})
        self.assertIsNone(profile.nutrients[0])
        self.assertEqual(profile.nutrients[NUTRIENT_KEYS.index("calcium_mg")], parsed)


if __name__ == "__main__":
    unittest.main()
