import unittest

from meal_planner.settings import RiceConfig, RiceConversion


def _rice(conversions, default=2.67):
    return RiceConfig(
        conversions=tuple(conversions),
        cooked_to_raw_default=default,
        water_multiplier=2.0,
        rice_category_exact="米",
        note_name_contains=("米",),
    )


class RiceRatioForTests(unittest.TestCase):
    def test_first_matching_row_wins(self):
        rice = _rice(
            [
                RiceConversion(name_contains="十穀糙米", ratio=2.5),
                RiceConversion(name_contains="糙米", ratio=2.623),
            ]
        )
        self.assertEqual(rice.ratio_for("十穀糙米飯"), 2.5)
        self.assertEqual(rice.ratio_for("糙米飯"), 2.623)

    def test_unmatched_name_uses_default(self):
        rice = _rice([RiceConversion(name_contains="糙米", ratio=2.623)], default=2.67)
        self.assertEqual(rice.ratio_for("白飯"), 2.67)
        self.assertEqual(rice.ratio_for(""), 2.67)

    def test_empty_rows_use_default(self):
        rice = _rice([], default=2.8)
        self.assertEqual(rice.ratio_for("糙米飯"), 2.8)


if __name__ == "__main__":
    unittest.main()
