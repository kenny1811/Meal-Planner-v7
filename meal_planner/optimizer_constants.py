"""Tuning constants for optimizer scoring and tie-breaking.

MEAL_ROTATION_OFFSET 亦係 meal_schedule 嘅日期輪替 offset——得呢一份，
meal_schedule 由呢度 import（佢 import optimizer，反方向會 circular）。
"""

from __future__ import annotations

MEAL_ROTATION_OFFSET = {"早餐": 0, "午餐": 1, "小食": 2, "晚餐": 3}
REROLL_BONUS_WEIGHT = 80.0
LUNCH_DINNER_DUPLICATE_WEIGHT = 25.0
