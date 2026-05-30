"""
餐單v5：總計列／誤差列 字色與誤差數值邏輯。

對應規格見專案根目錄 規則.md §16。
數值（容忍、脂肪比例、9 kcal/g）由 config.yaml 載入（§2）。
openpyxl 字色可用 Font(color=FONT_RED_ARGB)。
"""

from __future__ import annotations

from typing import Final

# Excel ARGB（無 #）
FONT_RED_ARGB: Final[str] = "FFFF0000"
FONT_BLACK_ARGB: Final[str] = "FF000000"


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


def error_cell_range(total: float, lo: float, hi: float) -> float:
    """卡路里／蛋白／碳水誤差：範圍內 0；偏低 total-lo；偏高 total-hi。"""
    if lo <= total <= hi:
        return 0.0
    if total < lo:
        return total - lo
    return total - hi


def error_font_red_range(total: float, lo: float, hi: float) -> bool:
    eps = 1e-9
    return (total - hi > eps) or (total - lo < -eps)


def error_cell_upper_only(total: float, hi: float) -> float:
    """天然糖／膽固醇／鈉誤差。"""
    if total <= hi:
        return 0.0
    return total - hi


def error_font_red_upper_only(total: float, hi: float) -> bool:
    eps = 1e-9
    return total - hi > eps


def error_cell_calcium(total: float, lo: float) -> float:
    if total >= lo:
        return 0.0
    return total - lo


def error_font_red_calcium(total: float, lo: float) -> bool:
    eps = 1e-9
    return total < lo - eps


def error_cell_fat_pct(fat_g: float, daily_kcal: float, pct_of_kcal: float) -> float:
    cap = fat_cap_grams(daily_kcal, pct_of_kcal)
    if fat_g <= cap:
        return 0.0
    return fat_g - cap


def error_font_red_fat_pct(fat_g: float, daily_kcal: float, pct_of_kcal: float) -> bool:
    cap = fat_cap_grams(daily_kcal, pct_of_kcal)
    eps = 1e-9
    return fat_g > cap + eps


def total_row_font_red_total_fat(fat_g: float, daily_kcal: float) -> bool:
    return total_row_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_total)


def total_row_font_red_sat_fat(fat_g: float, daily_kcal: float) -> bool:
    return total_row_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_saturated)


def total_row_font_red_trans_fat(fat_g: float, daily_kcal: float) -> bool:
    return total_row_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_trans)


def error_cell_total_fat(fat_g: float, daily_kcal: float) -> float:
    return error_cell_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_total)


def error_cell_sat_fat(fat_g: float, daily_kcal: float) -> float:
    return error_cell_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_saturated)


def error_cell_trans_fat(fat_g: float, daily_kcal: float) -> float:
    return error_cell_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_trans)


def error_font_red_total_fat(fat_g: float, daily_kcal: float) -> bool:
    return error_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_total)


def error_font_red_sat_fat(fat_g: float, daily_kcal: float) -> bool:
    return error_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_saturated)


def error_font_red_trans_fat(fat_g: float, daily_kcal: float) -> bool:
    return error_font_red_fat_pct(fat_g, daily_kcal, _nutrition_format().fat_pct_trans)
