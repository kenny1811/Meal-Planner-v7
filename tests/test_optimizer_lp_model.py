import unittest

from meal_planner.indicators import DayIndicatorProfile
from meal_planner.optimizer_lp_model import _fat_cap_ratio_for_target
from meal_planner.settings import get_settings


class OptimizerLpModelTests(unittest.TestCase):
    def test_fat_cap_ratio_uses_indicator_fat_pct(self):
        settings = get_settings()
        indicators = DayIndicatorProfile.from_row_cells([
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "<30% kcal",
        ])

        self.assertAlmostEqual(
            _fat_cap_ratio_for_target("fat_total_g", indicators, settings),
            0.30 / settings.nutrition_format.kcal_per_fat_g,
        )

    def test_fat_cap_ratio_rejects_missing_fat_pct(self):
        settings = get_settings()
        indicators = DayIndicatorProfile.from_row_cells([])

        with self.assertRaisesRegex(ValueError, "reading config is not allowed"):
            _fat_cap_ratio_for_target("fat_total_g", indicators, settings)


if __name__ == "__main__":
    unittest.main()
