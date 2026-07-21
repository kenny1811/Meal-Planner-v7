"""Compatibility facade for the split optimizer package.

淨返一個真正有 caller 嘅 re-export（meal_schedule 用）；其餘散件直接
import 各自嘅 optimizer_* module（tests 一直係咁做）。
"""

from __future__ import annotations

from meal_planner.optimizer_lp_model import solve_day_meal_plan

__all__ = ["solve_day_meal_plan"]
