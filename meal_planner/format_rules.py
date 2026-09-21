"""
餐單v5：總計列／誤差列 字色與誤差數值邏輯。

對應規格見專案根目錄 規則.md §16。
脂肪比例由 target row 提供；9 kcal/g 由 config.yaml 載入。
"""

from __future__ import annotations


def _nutrition_format():
    from meal_planner.settings import get_settings

    return get_settings().nutrition_format


def fat_cap_grams(daily_kcal: float, pct_of_kcal: float) -> float:
    """當日某類脂肪允許上限（克）= K × 比例 ÷ 每克脂肪 kcal。"""
    nf = _nutrition_format()
    if daily_kcal <= 0:
        return 0.0
    return daily_kcal * pct_of_kcal / nf.kcal_per_fat_g


def total_row_font_red_range(total: float, lo: float, hi: float) -> bool:
    """卡路里／蛋白質／碳水：總計列紅色。"""
    eps = 1e-9
    return total < lo - eps or total > hi + eps


def total_row_font_red_upper_only(total: float, hi: float) -> bool:
    """天然糖／膽固醇／鈉：總計列紅色。"""
    eps = 1e-9
    return total > hi + eps


def total_row_font_red_calcium(total: float, lo: float) -> bool:
    """鈣：總計列紅色。"""
    eps = 1e-9
    return total < lo - eps


def total_row_font_red_fat_pct(fat_g: float, daily_kcal: float, pct_of_kcal: float) -> bool:
    """總脂／飽和／反式：總計列紅色（逾 K 換算上限）。"""
    cap = fat_cap_grams(daily_kcal, pct_of_kcal)
    eps = 1e-9
    return fat_g > cap + eps


def error_font_red_range(total: float, lo: float, hi: float) -> bool:
    eps = 1e-9
    return (total - hi > eps) or (total - lo < -eps)


def error_font_red_upper_only(total: float, hi: float) -> bool:
    eps = 1e-9
    return total - hi > eps


def error_font_red_calcium(total: float, lo: float) -> bool:
    eps = 1e-9
    return total < lo - eps


def error_font_red_fat_pct(fat_g: float, daily_kcal: float, pct_of_kcal: float) -> bool:
    cap = fat_cap_grams(daily_kcal, pct_of_kcal)
    eps = 1e-9
    return fat_g > cap + eps
