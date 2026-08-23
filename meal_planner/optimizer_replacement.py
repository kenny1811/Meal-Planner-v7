"""Bounded replacement search for improving infeasible solutions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from meal_planner.indicators import DayIndicatorProfile
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings
from meal_planner.optimizer_diagnostics import _violation_score
from meal_planner.optimizer_models import SolveArtifacts, _Candidate


def _search_replacement_plan(
    *,
    solve_fn: Callable[..., SolveArtifacts | None],
    settings: AppSettings,
    indicators: DayIndicatorProfile,
    meal_pattern_parts: dict[str, list[dict[str, object]]],
    candidates_by_item: dict[tuple[str, int], list[NutritionEntry]],
    visible_meals: set[str],
    rice_token: str,
    day_offset: int,
    reroll_nonce: int,
    focus_multiplier: dict[str, float] | None,
    fixed_nutrients: dict[str, float] | None,
    bound_overrides: dict[int, dict[str, float]] | None,
    by_item: dict[tuple[str, int], list[_Candidate]],
    selected_rows_info: list[dict[str, Any]],
    base_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    score_before = _violation_score(base_violations, settings=settings)
    chosen_by_key: dict[tuple[str, int], int] = {}
    for r in selected_rows_info:
        meal = r.get("meal")
        idx = r.get("item_idx")
        row = r.get("row")
        if isinstance(meal, str) and isinstance(idx, int) and isinstance(row, int):
            chosen_by_key[(meal, idx)] = row

    forced: dict[tuple[str, int], int] = {}
    best_artifact: SolveArtifacts | None = None
    current_score = score_before
    plan_steps: list[dict[str, Any]] = []
    attempts = 0

    mutable_keys = [k for k, cs in by_item.items() if len(cs) >= 2 and k in chosen_by_key]
    # 米格要成日一齊郁：淨係 force 一格米，另一格米同佢冇交集，solve_day_meal_plan
    # 個「一日一米」約束就會靜靜哋唔建立（嗰度係 `if common_rows:`），出到嚟兩餐
    # 唔同米。所以試米嘅時候，要嗰款米每一格米都揀得到，然後一次過全部 force。
    rice_keys = [k for k, cs in by_item.items() if cs and cs[0].is_rice_item]
    rice_rows_by_key = {
        k: {int(c.entry.row_index) for c in by_item.get(k, [])} for k in rice_keys
    }

    def _forced_with(base: dict[tuple[str, int], int], key: tuple[str, int], to_row: int):
        """回傳 trial 用嘅 forced dict；米格唔夾就回 None（跳過呢個 candidate）。"""
        out = dict(base)
        if key in rice_rows_by_key:
            if any(to_row not in rows for rows in rice_rows_by_key.values()):
                return None
            for rk in rice_keys:
                out[rk] = to_row
        else:
            out[key] = to_row
        return out

    for _round in range(2):
        best_local: dict[str, Any] | None = None
        for key in mutable_keys:
            if key in forced:
                continue
            cs = by_item.get(key, [])
            if not cs:
                continue
            cur_row = forced.get(key, chosen_by_key.get(key))
            if cur_row is None:
                continue
            for cand in cs:
                to_row = int(cand.entry.row_index)
                if to_row == int(cur_row):
                    continue
                trial_forced = _forced_with(forced, key, to_row)
                if trial_forced is None:
                    continue
                sim = solve_fn(
                    settings=settings,
                    indicators=indicators,
                    meal_pattern_parts=meal_pattern_parts,
                    candidates_by_item=candidates_by_item,
                    visible_meals=visible_meals,
                    rice_token=rice_token,
                    day_offset=day_offset,
                    reroll_nonce=reroll_nonce + attempts + 31,
                    focus_multiplier=focus_multiplier,
                    fixed_nutrients=fixed_nutrients,
                    _auto_retry_depth=4,
                    bound_overrides=bound_overrides,
                    forced_item_rows=trial_forced,
                )
                attempts += 1
                if sim is None or not isinstance(sim.diagnostics, dict):
                    continue
                s = _violation_score(sim.diagnostics.get("hard_violations", []), settings=settings)
                if s >= current_score:
                    continue
                cand_info = {
                    "key": key,
                    "from_row": int(cur_row),
                    "to_row": to_row,
                    "from_name": next((x.entry.name for x in cs if int(x.entry.row_index) == int(cur_row)), f"row{cur_row}"),
                    "to_name": cand.entry.name,
                    "artifact": sim,
                    "score": s,
                }
                if best_local is None or s < best_local["score"]:
                    best_local = cand_info
        if best_local is None:
            break
        key = best_local["key"]
        accepted = _forced_with(forced, key, int(best_local["to_row"]))
        forced = accepted if accepted is not None else dict(forced)
        best_artifact = best_local["artifact"]
        current_score = best_local["score"]
        plan_steps.append(
            {
                "meal": key[0],
                "item_idx": key[1],
                "from_row": best_local["from_row"],
                "from_name": best_local["from_name"],
                "to_row": best_local["to_row"],
                "to_name": best_local["to_name"],
                "score": current_score,
            }
        )
        if current_score[0] == 0 and current_score[1] <= 1e-6:
            break

    return {
        "attempts": attempts,
        "score_before": score_before,
        "score_after": current_score,
        "hard_feasible_after": bool(best_artifact and isinstance(best_artifact.diagnostics, dict) and best_artifact.diagnostics.get("hard_feasible", False)),
        "plan": plan_steps,
        "artifact": best_artifact,
    }

