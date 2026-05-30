import unittest

from meal_planner.patterns import parse_meal_patterns, parse_pattern, split_item_alternatives, split_pattern_items
from meal_planner.settings import PatternConfig


class PatternTests(unittest.TestCase):
    def setUp(self):
        self.cfg = PatternConfig(item_separator="+", item_alt_separator="/")

    def test_split_pattern_items_trims_and_drops_empty_items(self):
        self.assertEqual(split_pattern_items(" 米 +  菜/瓜 ++ 肉 ", self.cfg), ["米", "菜/瓜", "肉"])

    def test_split_item_alternatives_trims_and_drops_empty_alternatives(self):
        self.assertEqual(split_item_alternatives(" 菜 / 瓜 / ", self.cfg), ("菜", "瓜"))
        self.assertEqual(split_item_alternatives("", self.cfg), ())

    def test_parse_pattern_preserves_raw_item_and_alternatives(self):
        parsed = parse_pattern("米+菜/瓜+魚/肉", self.cfg)

        self.assertEqual([p.raw for p in parsed], ["米", "菜/瓜", "魚/肉"])
        self.assertEqual([p.alternatives for p in parsed], [("米",), ("菜", "瓜"), ("魚", "肉")])

    def test_parse_meal_patterns_outputs_json_ready_shape(self):
        self.assertEqual(
            parse_meal_patterns({"早餐": "麥皮/包+蛋", "午餐": None}, self.cfg),
            {
                "早餐": [
                    {"raw": "麥皮/包", "alternatives": ["麥皮", "包"]},
                    {"raw": "蛋", "alternatives": ["蛋"]},
                ],
                "午餐": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
