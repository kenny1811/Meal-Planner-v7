"""每週固定食材：派日子嘅排序／配額邏輯，同埋 LP 嗰條 required_rows 約束。"""

import unittest
from datetime import date
from pathlib import Path

from meal_planner.indicators import NUTRIENT_KEYS, DayIndicatorProfile
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import WeeklyIngredientRule, _build_settings
from meal_planner.weekly_rules import (
    DayInfo,
    candidates_for_row,
    day_payload_rows_used,
    group_by_week,
    meal_plan_rows_used,
    needs_resolve,
    quota_for_week,
    resolve_rule_rows,
    slot_counts_for_rows,
    week_dates,
    week_start,
    weekday_days,
)

try:
    import pulp  # noqa: F401

    _HAS_PULP = True
except Exception:  # pragma: no cover
    _HAS_PULP = False


def _entry(row, name, category="蛋白質", **nut):
    nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
    nutrients.update(nut)
    return NutritionEntry(
        row_index=row,
        paused=False,
        category=category,
        name=name,
        nutrients=nutrients,
        min_g=0.0,
        max_g=100.0,
        daymax_g=100.0,
    )


ENTRIES = [
    _entry(2, "糙米(熟)", "五穀", carb_g=25.6, kcal=123.0),
    _entry(3, "藜麥米(熟)", "五穀", carb_g=21.3, kcal=120.0),
    _entry(42, "三文魚", protein_g=19.5, kcal=191.4),
    _entry(43, "鱈魚", protein_g=17.8, kcal=82.0),
]


class ResolveRuleRowsTest(unittest.TestCase):
    def test_exact_name_wins(self):
        rule = WeeklyIngredientRule(name="糙米(熟)", per_week=2)
        self.assertEqual(resolve_rule_rows([rule], ENTRIES), [(rule, 2)])

    def test_unique_substring_match(self):
        rule = WeeklyIngredientRule(name="三文魚", per_week=2)
        self.assertEqual(resolve_rule_rows([rule], ENTRIES), [(rule, 42)])

    def test_ambiguous_or_missing_is_skipped(self):
        # 「米」同時中糙米同藜麥米，對唔實就寧願唔理，唔好亂派。
        ambiguous = WeeklyIngredientRule(name="米", per_week=1)
        missing = WeeklyIngredientRule(name="乜乜物物", per_week=1)
        self.assertEqual(resolve_rule_rows([ambiguous, missing], ENTRIES), [])


class RowsUsedTest(unittest.TestCase):
    def test_zero_grams_does_not_count(self):
        meal_plan = {
            "meal_items": {
                "晚餐": [
                    {"name": "糙米(熟)", "row": 2, "grams": 300},
                    {"name": "三文魚", "row": 42, "grams": 0},
                ],
            }
        }
        self.assertEqual(meal_plan_rows_used(meal_plan), {2})

    def test_stored_payload_shape(self):
        payload = {
            "date": "2026-09-04",
            "meal_plan": {"meal_items": {"晚餐": [{"row": 42, "grams": 85}]}},
        }
        self.assertEqual(day_payload_rows_used(payload), {42})


class SlotCountsTest(unittest.TestCase):
    def _plan(self, lunch_items):
        slot = {"raw": "魚/肉", "alternatives": ["三文魚", "鱈魚"]}
        return {
            "meal_pattern_parts": {"午餐": [slot], "晚餐": [slot]},
            "meal_items": {"午餐": lunch_items, "晚餐": [{"row": 43, "grams": 90}]},
        }

    def test_counts_only_meals_that_have_items(self):
        two = slot_counts_for_rows(self._plan([{"row": 43, "grams": 90}]), ENTRIES, {42})
        one = slot_counts_for_rows(self._plan([]), ENTRIES, {42})
        # 餐廳午餐嗰日午餐冇 solver 食材，得返一個格可以放三文魚。
        self.assertEqual(two[42], 2)
        self.assertEqual(one[42], 1)


class CandidateOrderTest(unittest.TestCase):
    def test_more_slots_beats_better_score(self):
        loose = DayInfo(day=date(2026, 9, 2), score=(0.0, 0.0, 10.0), slot_counts={42: 1})
        roomy = DayInfo(day=date(2026, 9, 3), score=(0.0, 0.0, 900.0), slot_counts={42: 2})
        _, rest = candidates_for_row([loose, roomy], 42)
        self.assertEqual([d.day.day for d in rest], [3, 2])

    def test_score_breaks_ties_and_natural_comes_separately(self):
        a = DayInfo(day=date(2026, 9, 2), score=(0.0, 0.0, 900.0), slot_counts={42: 2})
        b = DayInfo(day=date(2026, 9, 3), score=(0.0, 0.0, 100.0), slot_counts={42: 2})
        already = DayInfo(
            day=date(2026, 9, 4), score=(1.0, 5.0, 50.0), slot_counts={42: 2}, rows_used={42}
        )
        natural, rest = candidates_for_row([a, b, already], 42)
        self.assertEqual([d.day.day for d in natural], [4])
        self.assertEqual([d.day.day for d in rest], [3, 2])

    def test_days_without_the_slot_are_not_candidates(self):
        no_slot = DayInfo(day=date(2026, 9, 2), score=(0.0, 0.0, 1.0), slot_counts={42: 0})
        self.assertEqual(candidates_for_row([no_slot], 42), ([], []))


class QuotaTest(unittest.TestCase):
    def test_outside_usage_eats_into_the_quota(self):
        rule = WeeklyIngredientRule(name="糙米(熟)", per_week=2)
        week = date(2026, 9, 20)
        self.assertEqual(quota_for_week(rule, week, 2, {}), 2)
        self.assertEqual(quota_for_week(rule, week, 2, {(week, 2): 1}), 1)
        self.assertEqual(quota_for_week(rule, week, 2, {(week, 2): 5}), 0)


class WeekHelpersTest(unittest.TestCase):
    def test_week_runs_sunday_to_saturday(self):
        # 2026-09-04 係星期五，嗰週由 8/30（日）去到 9/5（六）。
        days = week_dates(week_start(date(2026, 9, 4)))
        self.assertEqual((days[0], days[-1]), (date(2026, 8, 30), date(2026, 9, 5)))

    def test_sunday_starts_its_own_week(self):
        self.assertEqual(week_start(date(2026, 9, 6)), date(2026, 9, 6))
        self.assertEqual(week_start(date(2026, 9, 5)), date(2026, 8, 30))

    def test_group_by_week_splits_on_saturday_sunday(self):
        # 9/5 六、9/6 日：星期日開新一週，唔係 ISO 嗰個星期一界。
        infos = [DayInfo(day=date(2026, 9, d), score=(0.0, 0.0, 0.0)) for d in (5, 6)]
        self.assertEqual(sorted(group_by_week(infos)), [date(2026, 8, 30), date(2026, 9, 6)])

    def test_weekday_days_filters_by_isoweekday(self):
        infos = [DayInfo(day=date(2026, 9, d), score=(0.0, 0.0, 0.0)) for d in range(1, 8)]
        self.assertEqual([d.day.day for d in weekday_days(infos, [3, 7])], [2, 6])


class NeedsResolveTest(unittest.TestCase):
    def test_no_work_when_already_compliant(self):
        self.assertFalse(needs_resolve({2, 42}, {2}, {43}))

    def test_missing_required_row(self):
        self.assertTrue(needs_resolve({3}, {2}, set()))

    def test_excluded_row_present(self):
        self.assertTrue(needs_resolve({2}, set(), {2}))


class ConfigParsingTest(unittest.TestCase):
    def _rules(self, raw):
        return _build_settings(Path("."), {"weekly_ingredient_rules": raw}).weekly_ingredient_rules

    def test_quota_mode_and_weekday_mode(self):
        rules = self._rules(
            [
                {"name": "糙米(熟)", "per_week": 2, "weekdays": [], "exclusive": True},
                {"name": "三文魚", "per_week": 2, "weekdays": [7, 3, 3, 99]},
            ]
        )
        self.assertEqual(len(rules), 2)
        self.assertTrue(rules[0].is_quota)
        self.assertEqual(rules[0].per_week, 2)
        # 星期要去重、排序，範圍外嘅丟走。
        self.assertEqual(rules[1].weekdays, (3, 7))
        self.assertFalse(rules[1].is_quota)
        self.assertTrue(rules[1].exclusive)

    def test_junk_entries_are_dropped(self):
        rules = self._rules([{"name": "", "per_week": 2}, {"name": "x", "per_week": 0}, "唔係 dict"])
        self.assertEqual(rules, ())

    def test_absent_section_means_no_rules(self):
        self.assertEqual(_build_settings(Path("."), {}).weekly_ingredient_rules, ())


@unittest.skipUnless(_HAS_PULP, "pulp not installed")
class RequiredRowsConstraintTest(unittest.TestCase):
    """LP 層面：required_rows 要迫到嗰行入選，但唔指定邊一餐。"""

    def _solve(self, required_rows):
        from meal_planner.optimizer_lp_model import solve_day_meal_plan
        from meal_planner.settings import get_settings

        cells = [""] * len(NUTRIENT_KEYS)
        cells[NUTRIENT_KEYS.index("protein_g")] = "0-100"
        for key in ("fat_total_g", "fat_sat_g", "fat_trans_g"):
            cells[NUTRIENT_KEYS.index(key)] = "<50% kcal"
        indicators = DayIndicatorProfile.from_row_cells(cells)

        salmon = _entry(42, "三文魚", protein_g=19.5, kcal=191.4)
        cod = _entry(43, "鱈魚", protein_g=17.8, kcal=82.0)
        slot = {"alternatives": ["魚"], "raw": "魚", "name": "魚"}
        return solve_day_meal_plan(
            settings=get_settings(),
            indicators=indicators,
            meal_pattern_parts={"午餐": [dict(slot)], "晚餐": [dict(slot)]},
            candidates_by_item={("午餐", 0): [cod, salmon], ("晚餐", 0): [cod, salmon]},
            visible_meals={"午餐", "晚餐"},
            rice_token="米",
            day_offset=0,
            required_rows=required_rows,
        )

    def _names(self, art):
        return [it["name"] for items in art.meal_items.values() for it in items]

    def test_required_row_appears_somewhere(self):
        art = self._solve(frozenset({42}))
        self.assertIsNotNone(art)
        self.assertIn("三文魚", self._names(art))

    def test_unknown_row_is_ignored_not_infeasible(self):
        # 食材畀人暫停／刪咗就唔喺候選；呢條規則要當冇發生，唔可以搞到無解。
        art = self._solve(frozenset({9999}))
        self.assertIsNotNone(art)
        self.assertTrue(self._names(art))


if __name__ == "__main__":
    unittest.main()
