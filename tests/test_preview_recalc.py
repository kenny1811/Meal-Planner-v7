import unittest

from meal_planner.indicators import DayIndicatorProfile, NUTRIENT_KEYS
from meal_planner.preview import _calc_day_summary, _is_meal_visible, _parse_edited_line, _summary_score
from meal_planner.settings import get_settings


def nutrient_map(**overrides):
    values = {k: 0.0 for k in NUTRIENT_KEYS}
    values.update(overrides)
    return values


class PreviewRecalcTests(unittest.TestCase):
    def test_parse_edited_line_accepts_meal_prefix_grams_and_unknown_grams(self):
        self.assertEqual(
            _parse_edited_line("早餐 - 雞蛋(50g)+燕麥(?g)+蘋果"),
            [("雞蛋", 50.0), ("燕麥", "?"), ("蘋果", None)],
        )
        self.assertEqual(_parse_edited_line("—"), [])
        self.assertEqual(_parse_edited_line(""), [])

    def test_is_meal_visible_prefers_resolved_time_and_accepts_fixed_primary_clock(self):
        self.assertTrue(_is_meal_visible("早餐", {"meal_times_resolved": {"早餐": "07:30"}}))
        self.assertTrue(_is_meal_visible("早餐", {"primary_rule": {"早餐": "7:30"}}))
        self.assertFalse(_is_meal_visible("午餐", {"primary_rule": {"午餐": "跟行位表"}}))
        self.assertFalse(_is_meal_visible("晚餐", {"meal_times_resolved": {"晚餐": ""}, "primary_rule": {"晚餐": ""}}))

    def test_calc_day_summary_ignores_hidden_meals_and_flags_visible_range_errors(self):
        settings = get_settings()
        indicators = DayIndicatorProfile.from_row_cells(["100-200", "10-20", "30-40", "<5", "<10", "<100", ">300"])
        meal_plan = {
            "meal_times_resolved": {"早餐": "08:00", "午餐": ""},
            "primary_rule": {"早餐": "08:00", "午餐": ""},
            "meal_nutrients": {
                "早餐": nutrient_map(kcal=250, protein_g=15, carb_g=35, sugar_g=6, sodium_mg=90, calcium_mg=250),
                "午餐": nutrient_map(kcal=9999, protein_g=9999, carb_g=9999, sugar_g=9999, sodium_mg=9999, calcium_mg=9999),
            },
        }

        summary = _calc_day_summary(meal_plan, indicators, settings)

        self.assertEqual(summary["totals"][NUTRIENT_KEYS.index("kcal")], 250.0)
        self.assertEqual(summary["errors"][NUTRIENT_KEYS.index("kcal")], 50.0)
        self.assertTrue(summary["total_red_flags"][NUTRIENT_KEYS.index("kcal")])
        self.assertTrue(summary["error_red_flags"][NUTRIENT_KEYS.index("sugar_g")])
        self.assertTrue(summary["total_red_flags"][NUTRIENT_KEYS.index("calcium_mg")])

    def test_calc_day_summary_clears_red_when_displayed_error_rounds_to_zero(self):
        settings = get_settings()
        indicators = DayIndicatorProfile.from_row_cells(["100-200"])
        meal_plan = {
            "meal_times_resolved": {"早餐": "08:00"},
            "meal_nutrients": {"早餐": nutrient_map(kcal=200.04)},
        }

        summary = _calc_day_summary(meal_plan, indicators, settings)

        self.assertEqual(summary["errors"][NUTRIENT_KEYS.index("kcal")], 0.0)
        self.assertFalse(summary["error_red_flags"][NUTRIENT_KEYS.index("kcal")])
        self.assertFalse(summary["total_red_flags"][NUTRIENT_KEYS.index("kcal")])

    def test_calc_day_summary_red_flags_values_outside_range(self):
        settings = get_settings()
        indicators = DayIndicatorProfile.from_row_cells(["1500-1600", "95-110"])
        meal_plan = {
            "meal_times_resolved": {"早餐": "08:00"},
            "meal_nutrients": {"早餐": nutrient_map(kcal=1500.1, protein_g=113.3)},
        }

        summary = _calc_day_summary(meal_plan, indicators, settings)
        protein_idx = NUTRIENT_KEYS.index("protein_g")

        self.assertEqual(summary["totals"][protein_idx], 113.3)
        self.assertEqual(summary["errors"][protein_idx], 3.3)
        self.assertTrue(summary["total_red_flags"][protein_idx])
        self.assertTrue(summary["error_red_flags"][protein_idx])

    def test_summary_score_prioritizes_red_count_then_violation_then_total_deviation(self):
        self.assertLess(
            _summary_score({"total_red_flags": [False, True], "errors": [100, 2]}),
            _summary_score({"total_red_flags": [True, True], "errors": [1, 1]}),
        )
        self.assertLess(
            _summary_score({"total_red_flags": [True, False], "errors": [1, 100]}),
            _summary_score({"total_red_flags": [True, False], "errors": [2, 0]}),
        )


if __name__ == "__main__":
    unittest.main()
