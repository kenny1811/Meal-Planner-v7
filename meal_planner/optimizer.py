"""Compatibility facade for the split optimizer package.

The implementation is now split by concern:
- optimizer_candidates.py: candidate construction and gram bounds
- optimizer_lp_model.py: LP/MILP model assembly and solve orchestration
- optimizer_diagnostics.py: violation scoring, recommendations, and parameter changes
- optimizer_relaxation.py: relaxation suggestions
- optimizer_replacement.py: replacement search
- optimizer_retry.py: auto-retry strategy generation
"""

from __future__ import annotations

from meal_planner.optimizer_candidates import _effective_max_g, build_active_items_and_candidates
from meal_planner.optimizer_constants import LUNCH_DINNER_DUPLICATE_WEIGHT, MEAL_ROTATION_OFFSET, REROLL_BONUS_WEIGHT
from meal_planner.optimizer_diagnostics import _build_parameter_changes, _build_recommendations, _top_contributors, _violation_score
from meal_planner.optimizer_lp_model import solve_day_meal_plan
from meal_planner.optimizer_models import SolveArtifacts, _Candidate
from meal_planner.optimizer_relaxation import _build_relaxation_plan
from meal_planner.optimizer_replacement import _search_replacement_plan as _search_replacement_plan_impl
from meal_planner.optimizer_retry import build_auto_retry_plans


def _search_replacement_plan(**kwargs):
    return _search_replacement_plan_impl(solve_fn=solve_day_meal_plan, **kwargs)


__all__ = [
    "SolveArtifacts",
    "_Candidate",
    "_build_parameter_changes",
    "_build_recommendations",
    "_build_relaxation_plan",
    "_effective_max_g",
    "_search_replacement_plan",
    "_top_contributors",
    "_violation_score",
    "build_active_items_and_candidates",
    "build_auto_retry_plans",
    "solve_day_meal_plan",
]
