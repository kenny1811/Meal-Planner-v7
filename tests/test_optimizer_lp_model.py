import unittest
from dataclasses import replace

from meal_planner.indicators import NUTRIENT_KEYS, DayIndicatorProfile
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.optimizer_lp_model import _fat_cap_ratio_for_target, solve_day_meal_plan
from meal_planner.settings import get_settings

try:
    import pulp  # noqa: F401

    _HAS_PULP = True
except Exception:  # pragma: no cover
    _HAS_PULP = False


def _filler_veggie_entry() -> NutritionEntry:
    # 低營養密度「填充」食材：碳水少、其餘近零，Min/Max 有闊範圍。
    nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
    nutrients["carb_g"] = 10.0
    return NutritionEntry(
        row_index=1,
        paused=False,
        category="菜",
        name="測試菜",
        nutrients=nutrients,
        min_g=100.0,
        max_g=200.0,
        daymax_g=200.0,
    )


def _solve_veggie_grams(midpoint_weight: float) -> float:
    base = get_settings()
    settings = replace(base, optimizer=replace(base.optimizer, midpoint_pull_weight=midpoint_weight))
    # 只有碳水一個寬鬆 RANGE 目標；脂肪比例給非約束值以滿足 fat-cap 需求。
    cells = [""] * len(NUTRIENT_KEYS)
    cells[NUTRIENT_KEYS.index("carb_g")] = "0-100"
    for key in ("fat_total_g", "fat_sat_g", "fat_trans_g"):
        cells[NUTRIENT_KEYS.index(key)] = "<50% kcal"
    indicators = DayIndicatorProfile.from_row_cells(cells)

    entry = _filler_veggie_entry()
    meal_pattern_parts = {"晚餐": [{"alternatives": ["菜"], "raw": "測試菜", "name": "測試菜"}]}
    candidates_by_item = {("晚餐", 0): [entry]}

    art = solve_day_meal_plan(
        settings=settings,
        indicators=indicators,
        meal_pattern_parts=meal_pattern_parts,
        candidates_by_item=candidates_by_item,
        visible_meals={"晚餐"},
        rice_token="米",
        day_offset=0,
    )
    assert art is not None
    item = art.meal_items["晚餐"][0]
    return float(item["grams"])


def _rice_entry() -> NutritionEntry:
    nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
    nutrients["carb_g"] = 25.0
    nutrients["kcal"] = 123.0
    return NutritionEntry(
        row_index=1,
        paused=False,
        category="五穀",
        name="測試米",
        nutrients=nutrients,
        min_g=120.0,
        max_g=390.0,
        daymax_g=390.0,  # 全日上限逼使午/晚餐要分攤同一堆米
    )


def _solve_rice_split(rice_balance_weight: float) -> tuple[float, float]:
    base = get_settings()
    settings = replace(
        base,
        optimizer=replace(
            base.optimizer, midpoint_pull_weight=0.0, rice_balance_weight=rice_balance_weight
        ),
    )
    cells = [""] * len(NUTRIENT_KEYS)
    cells[NUTRIENT_KEYS.index("carb_g")] = "0-100"  # 寬鬆 → hi_pull 把米推到 daymax
    for key in ("fat_total_g", "fat_sat_g", "fat_trans_g"):
        cells[NUTRIENT_KEYS.index(key)] = "<50% kcal"
    indicators = DayIndicatorProfile.from_row_cells(cells)

    entry = _rice_entry()
    meal_pattern_parts = {
        "午餐": [{"alternatives": ["米"], "raw": "測試米", "name": "測試米"}],
        "晚餐": [{"alternatives": ["米"], "raw": "測試米", "name": "測試米"}],
    }
    candidates_by_item = {("午餐", 0): [entry], ("晚餐", 0): [entry]}

    art = solve_day_meal_plan(
        settings=settings,
        indicators=indicators,
        meal_pattern_parts=meal_pattern_parts,
        candidates_by_item=candidates_by_item,
        visible_meals={"午餐", "晚餐"},
        rice_token="米",
        day_offset=0,
    )
    assert art is not None
    lunch = float(art.meal_items["午餐"][0]["grams"])
    dinner = float(art.meal_items["晚餐"][0]["grams"])
    return lunch, dinner


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

    @unittest.skipUnless(_HAS_PULP, "pulp solver not installed")
    def test_midpoint_pull_reduces_low_density_filler_grams(self):
        # 冇中點回拉時，hi_pull 會把填充菜谷到 Max(200g)。
        grams_off = _solve_veggie_grams(0.0)
        self.assertEqual(grams_off, 200.0)

        # 開啟中點回拉後，菜應離開 Max 向中點(150g)回拉。
        grams_on = _solve_veggie_grams(0.2)
        self.assertLess(grams_on, grams_off)
        self.assertLessEqual(grams_on, 150.0)

    @unittest.skipUnless(_HAS_PULP, "pulp solver not installed")
    def test_rice_balance_evens_split_across_meals(self):
        off = _solve_rice_split(0.0)
        on = _solve_rice_split(1.0)

        # 分餐屬營養中性：全日米總量不受平均分配影響。
        self.assertEqual(sum(off), sum(on))

        # 開啟平均分配後，兩餐米克數應近乎相等（整數捨入內）。
        self.assertLessEqual(abs(on[0] - on[1]), 1.0)

        # 且至少同「未開啟」一樣平均（唔會更唔平均）。
        self.assertLessEqual(abs(on[0] - on[1]), abs(off[0] - off[1]))


if __name__ == "__main__":
    unittest.main()
