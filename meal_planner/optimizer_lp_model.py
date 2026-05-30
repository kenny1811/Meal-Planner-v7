"""LP/MILP model assembly and solve orchestration."""

from __future__ import annotations

from typing import Any
import zlib

from meal_planner.indicators import DayIndicatorProfile, IndicatorKind, NUTRIENT_KEYS
from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings
from meal_planner.optimizer_candidates import build_active_items_and_candidates
from meal_planner.optimizer_constants import LUNCH_DINNER_DUPLICATE_WEIGHT, MEAL_ROTATION_OFFSET, REROLL_BONUS_WEIGHT
from meal_planner.optimizer_diagnostics import (
    _build_constraint_analysis,
    _build_parameter_changes,
    _build_recommendations,
    _violation_score,
)
from meal_planner.optimizer_models import SolveArtifacts, _Candidate
from meal_planner.optimizer_relaxation import _build_relaxation_plan
from meal_planner.optimizer_replacement import _search_replacement_plan
from meal_planner.optimizer_retry import build_auto_retry_plans

try:
    import pulp
except Exception:  # pragma: no cover - 執行環境未安裝 solver 時回退
    pulp = None


def _nutrient_weight(key: str, settings: AppSettings) -> float:
    w = settings.optimizer.weights
    return {
        "kcal": float(w.kcal),
        "protein_g": float(w.protein),
        "carb_g": float(w.carb),
        "sugar_g": float(w.sugar),
        "cholesterol_mg": float(w.cholesterol),
        "sodium_mg": float(w.sodium),
        "calcium_mg": float(w.calcium),
        "fat_total_g": 1.0,
        "fat_sat_g": 1.0,
        "fat_trans_g": 1.0,
    }.get(key, 1.0)



def solve_day_meal_plan(
    *,
    settings: AppSettings,
    indicators: DayIndicatorProfile,
    meal_pattern_parts: dict[str, list[dict[str, object]]],
    candidates_by_item: dict[tuple[str, int], list[NutritionEntry]],
    visible_meals: set[str],
    rice_token: str,
    day_offset: int,
    reroll_nonce: int = 0,
    focus_multiplier: dict[str, float] | None = None,
    fixed_nutrients: dict[str, float] | None = None,
    _auto_retry_depth: int = 0,
    bound_overrides: dict[int, dict[str, float]] | None = None,
    forced_item_rows: dict[tuple[str, int], int] | None = None,
) -> SolveArtifacts | None:
    """
    以 MILP 做 item 候選離散選擇，並以 LP 做克數分配：
    - 每個 item 恰選 1 個候選（如有候選）
    - 每候選克數受 Min/Max 約束
    - 同一食材列受 DayMax 约束
    - 營養目標用 slack 最小化（不可行時回最小違規）
    """
    if pulp is None:
        return None

    base_meals = list(meal_pattern_parts.keys())
    out_meal_ingredients = {m: [] for m in base_meals}
    out_meal_nutrients = {m: {k: 0.0 for k in NUTRIENT_KEYS} for m in base_meals}
    out_meal_items = {m: [] for m in base_meals}

    active_items, candidates = build_active_items_and_candidates(
        settings=settings,
        meal_pattern_parts=meal_pattern_parts,
        candidates_by_item=candidates_by_item,
        visible_meals=visible_meals,
        rice_token=rice_token,
        bound_overrides=bound_overrides,
        forced_item_rows=forced_item_rows,
    )

    if not active_items:
        return SolveArtifacts(
            meal_ingredients=out_meal_ingredients,
            meal_nutrients=out_meal_nutrients,
            meal_items=out_meal_items,
            status="no_active_items",
            diagnostics={"note": "冇可見餐次 item，略過求解。"},
        )

    model = pulp.LpProblem("meal_plan_milp", pulp.LpMinimize)

    y: dict[tuple[str, int, int], Any] = {}
    g: dict[tuple[str, int, int], Any] = {}
    by_item: dict[tuple[str, int], list[_Candidate]] = {}
    by_row: dict[int, list[_Candidate]] = {}
    for c in candidates:
        key = (c.meal, c.item_idx)
        by_item.setdefault(key, []).append(c)
        by_row.setdefault(c.entry.row_index, []).append(c)

    for key, cs in by_item.items():
        meal, item_idx = key
        for local_idx, c in enumerate(cs):
            vkey = (meal, item_idx, local_idx)
            y[vkey] = pulp.LpVariable(f"y_{meal}_{item_idx}_{local_idx}", lowBound=0, upBound=1, cat="Binary")
            g[vkey] = pulp.LpVariable(f"g_{meal}_{item_idx}_{local_idx}", lowBound=0, cat="Integer")
            model += g[vkey] >= c.min_g * y[vkey]
            model += g[vkey] <= c.max_g * y[vkey]

    for meal, idx, item in active_items:
        cs = by_item.get((meal, idx), [])
        if not cs:
            continue
        model += pulp.lpSum(y[(meal, idx, j)] for j in range(len(cs))) == 1

    # 米類同日同款（只在交集存在時啟用）
    rice_item_keys = [k for k, cs in by_item.items() if cs and cs[0].is_rice_item]
    if rice_item_keys:
        common_rows: set[int] | None = None
        for k in rice_item_keys:
            rows = {c.entry.row_index for c in by_item.get(k, [])}
            common_rows = rows if common_rows is None else (common_rows & rows)
        if common_rows:
            rice_row_vars = {
                r: pulp.LpVariable(f"rice_row_{r}", lowBound=0, upBound=1, cat="Binary")
                for r in sorted(common_rows)
            }
            model += pulp.lpSum(rice_row_vars.values()) == 1
            for meal, idx in rice_item_keys:
                cs = by_item.get((meal, idx), [])
                allowed = []
                for j, c in enumerate(cs):
                    if c.entry.row_index in rice_row_vars:
                        model += y[(meal, idx, j)] <= rice_row_vars[c.entry.row_index]
                        allowed.append(y[(meal, idx, j)])
                if allowed:
                    model += pulp.lpSum(allowed) == 1

    # 午餐/晚餐避免重覆同一食材列。米類另有「同日同款」規則，所以不計入重覆 penalty。
    duplicate_terms = []
    lunch_dinner_rows = {
        c.entry.row_index
        for c in candidates
        if c.meal in {"午餐", "晚餐"} and not c.is_rice_item
    }
    for row_idx in sorted(lunch_dinner_rows):
        lunch_vars = []
        dinner_vars = []
        for c in by_row.get(row_idx, []):
            if c.is_rice_item or c.meal not in {"午餐", "晚餐"}:
                continue
            local = by_item[(c.meal, c.item_idx)].index(c)
            if c.meal == "午餐":
                lunch_vars.append(y[(c.meal, c.item_idx, local)])
            elif c.meal == "晚餐":
                dinner_vars.append(y[(c.meal, c.item_idx, local)])
        if not lunch_vars or not dinner_vars:
            continue
        dup = pulp.LpVariable(f"dup_lunch_dinner_row_{row_idx}", lowBound=0, upBound=1, cat="Continuous")
        model += dup >= pulp.lpSum(lunch_vars) + pulp.lpSum(dinner_vars) - 1
        duplicate_terms.append(LUNCH_DINNER_DUPLICATE_WEIGHT * dup)

    # DayMax 約束：同一食材列當日總克數不可超標
    for row_idx, cs in by_row.items():
        daymax_vals = []
        for c in cs:
            ov = (bound_overrides or {}).get(c.entry.row_index, {})
            if "daymax_g" in ov:
                daymax_vals.append(float(ov["daymax_g"]))
            elif c.entry.daymax_g is not None:
                daymax_vals.append(float(c.entry.daymax_g))
        if not daymax_vals:
            continue
        daymax = min(daymax_vals)
        row_grams = []
        for c in cs:
            meal, idx = c.meal, c.item_idx
            local = by_item[(meal, idx)].index(c)
            row_grams.append(g[(meal, idx, local)])
        model += pulp.lpSum(row_grams) <= daymax

    nutrient_expr = {k: [] for k in NUTRIENT_KEYS}
    for (meal, idx), cs in by_item.items():
        for j, c in enumerate(cs):
            for k in NUTRIENT_KEYS:
                coef = float(c.entry.nutrients.get(k, 0.0)) / 100.0
                nutrient_expr[k].append(coef * g[(meal, idx, j)])
    fixed_totals = {
        k: float((fixed_nutrients or {}).get(k, 0.0) or 0.0)
        for k in NUTRIENT_KEYS
    }
    totals = {k: fixed_totals[k] + pulp.lpSum(nutrient_expr[k]) for k in NUTRIENT_KEYS}
    kcal_total = totals["kcal"]

    penalties = []
    hi_pull_terms = []
    hard_weight = 1000.0
    soft_weight = 0.05
    slack_vars: list[tuple[str, str, Any]] = []
    for i, key in enumerate(NUTRIENT_KEYS):
        p = indicators.nutrients[i] if i < len(indicators.nutrients) else None
        if p is None:
            continue
        base_w = _nutrient_weight(key, settings)
        mul = float((focus_multiplier or {}).get(key, 1.0))
        w = base_w * max(0.1, mul)
        t = totals[key]
        if p.kind == IndicatorKind.RANGE and p.lo is not None and p.hi is not None:
            s_low = pulp.LpVariable(f"s_low_{key}", lowBound=0, cat="Continuous")
            s_high = pulp.LpVariable(f"s_high_{key}", lowBound=0, cat="Continuous")
            model += t + s_low >= float(p.lo)
            model += t - s_high <= float(p.hi)
            penalties.extend([hard_weight * w * s_low, hard_weight * w * s_high])
            slack_vars.append((key, "low", s_low))
            slack_vars.append((key, "high", s_high))
            h_gap = pulp.LpVariable(f"hgap_{key}", lowBound=0, cat="Continuous")
            model += h_gap >= float(p.hi) - t
            hi_pull_terms.append(soft_weight * w * h_gap)
        elif p.kind == IndicatorKind.UPPER_ONLY and p.hi is not None:
            s_high = pulp.LpVariable(f"s_high_{key}", lowBound=0, cat="Continuous")
            model += t - s_high <= float(p.hi)
            penalties.append(hard_weight * w * s_high)
            slack_vars.append((key, "high", s_high))
            h_gap = pulp.LpVariable(f"hgap_{key}", lowBound=0, cat="Continuous")
            model += h_gap >= float(p.hi) - t
            hi_pull_terms.append(soft_weight * w * h_gap)
        elif p.kind == IndicatorKind.LOWER_ONLY and p.lo is not None:
            s_low = pulp.LpVariable(f"s_low_{key}", lowBound=0, cat="Continuous")
            model += t + s_low >= float(p.lo)
            penalties.append(hard_weight * w * s_low)
            slack_vars.append((key, "low", s_low))

    nf = settings.nutrition_format
    fat_caps = {
        "fat_total_g": float(nf.fat_pct_total) / float(nf.kcal_per_fat_g),
        "fat_sat_g": float(nf.fat_pct_saturated) / float(nf.kcal_per_fat_g),
        "fat_trans_g": float(nf.fat_pct_trans) / float(nf.kcal_per_fat_g),
    }
    fat_cap_weights = {
        "fat_total_g": max(1.0, float(settings.optimizer.fat_cap_weights.total)),
        "fat_sat_g": max(1.0, float(settings.optimizer.fat_cap_weights.saturated)),
        "fat_trans_g": max(1.0, float(settings.optimizer.fat_cap_weights.trans)),
    }
    for key, ratio in fat_caps.items():
        s_fat = pulp.LpVariable(f"s_fat_{key}", lowBound=0, cat="Continuous")
        model += totals[key] <= ratio * kcal_total + s_fat
        penalties.append(hard_weight * fat_cap_weights[key] * s_fat)
        slack_vars.append((key, "fat_cap", s_fat))

    # 同分時輕微偏好：跟日期偏移與餐次偏移排序，保留「每日有變化」感
    tie_break_terms = []
    reroll_bonus_terms = []
    for (meal, idx), cs in by_item.items():
        meal_offset = MEAL_ROTATION_OFFSET.get(meal, 0)
        if len(cs) >= 2:
            pref_j = (day_offset + meal_offset + int(reroll_nonce or 0)) % len(cs)
            reroll_bonus_terms.append(-REROLL_BONUS_WEIGHT * y[(meal, idx, pref_j)])
        for j, _ in enumerate(cs):
            base_pref = ((j + day_offset + meal_offset) % max(len(cs), 1)) * 1e-4
            token = f"{meal}|{idx}|{j}|{reroll_nonce}"
            jitter = (zlib.crc32(token.encode("utf-8")) % 997) * 1e-7
            tie_break_terms.append((base_pref + jitter) * y[(meal, idx, j)])

    model += pulp.lpSum(penalties + hi_pull_terms + duplicate_terms + tie_break_terms + reroll_bonus_terms)

    status = "not_solved"
    try:
        solver = pulp.PULP_CBC_CMD(msg=False)
        model.solve(solver)
        status = pulp.LpStatus.get(model.status, str(model.status))
    except Exception as ex:  # pragma: no cover
        return None

    if status not in {"Optimal", "Feasible"}:
        return None

    slack_tol = 1e-5
    hard_violations: list[dict[str, Any]] = []
    for key, kind, var in slack_vars:
        v = float(var.value() or 0.0)
        if v > slack_tol:
            hard_violations.append(
                {
                    "nutrient": key,
                    "constraint": kind,
                    "gap": round(v, 4),
                }
            )
    hard_feasible = len(hard_violations) == 0

    selected_pairs: list[tuple[_Candidate, float]] = []
    selected_rows_info: list[dict[str, Any]] = []
    for meal, idx, item in active_items:
        cs = by_item.get((meal, idx), [])
        chosen_j = None
        for j in range(len(cs)):
            if float(y[(meal, idx, j)].value() or 0.0) > 0.5:
                chosen_j = j
                break
        if chosen_j is None:
            raw = str(item.get("raw", "")).strip()
            if raw:
                out_meal_ingredients[meal].append(raw)
                out_meal_items[meal].append({"name": raw, "grams": None, "row": None})
            continue
        c = cs[chosen_j]
        grams = max(0.0, float(g[(meal, idx, chosen_j)].value() or 0.0))
        selected_pairs.append((c, grams))
        selected_rows_info.append(
            {
                "row": c.entry.row_index,
                "name": c.entry.name,
                "meal": c.meal,
                "item_idx": idx,
                "grams": float(grams),
                "min_g": float(c.min_g),
                "max_g": float(c.max_g),
                "daymax_g": float(c.entry.daymax_g) if c.entry.daymax_g is not None else None,
                "kcal": float(c.entry.nutrients.get("kcal", 0.0)),
                "fat": float(c.entry.nutrients.get("fat_total_g", 0.0)),
                "calcium": float(c.entry.nutrients.get("calcium_mg", 0.0)),
            }
        )
        out_meal_ingredients[meal].append(f"{c.entry.name}({grams:.0f}g)")
        out_meal_items[meal].append({"name": c.entry.name, "grams": grams, "row": c.entry.row_index})
        ratio = grams / 100.0
        for k in NUTRIENT_KEYS:
            out_meal_nutrients[meal][k] += float(c.entry.nutrients.get(k, 0.0)) * ratio

    daymax_tight: list[dict[str, Any]] = []
    used_by_row: dict[int, float] = {}
    row_entry_metrics: dict[int, dict[str, Any]] = {}
    for c in candidates:
        row_entry_metrics[c.entry.row_index] = {
            "name": c.entry.name,
            "kcal": float(c.entry.nutrients.get("kcal", 0.0)),
            "fat": float(c.entry.nutrients.get("fat_total_g", 0.0)),
            "calcium": float(c.entry.nutrients.get("calcium_mg", 0.0)),
            "max_g": float(c.entry.max_g) if c.entry.max_g is not None else None,
            "daymax_g": float(c.entry.daymax_g) if c.entry.daymax_g is not None else None,
        }
    for row_idx, cs in by_row.items():
        daymax_vals = []
        for c in cs:
            ov = (bound_overrides or {}).get(c.entry.row_index, {})
            if "daymax_g" in ov:
                daymax_vals.append(float(ov["daymax_g"]))
            elif c.entry.daymax_g is not None:
                daymax_vals.append(float(c.entry.daymax_g))
        if not daymax_vals:
            continue
        daymax = min(daymax_vals)
        used = 0.0
        for c in cs:
            local = by_item[(c.meal, c.item_idx)].index(c)
            used += max(0.0, float(g[(c.meal, c.item_idx, local)].value() or 0.0))
        used_by_row[row_idx] = used
        if daymax > 0 and used >= daymax * 0.98:
            daymax_tight.append(
                {
                    "row": row_idx,
                    "name": cs[0].entry.name,
                    "used_g": round(used, 1),
                    "daymax_g": round(daymax, 1),
                }
            )
    recommendations = _build_recommendations(
        hard_violations=hard_violations,
        daymax_tight_rows=daymax_tight,
        selected=selected_pairs,
        all_candidates=candidates,
        used_by_row=used_by_row,
    )
    relaxation_plan = _build_relaxation_plan(
        hard_violations=hard_violations,
        selected_rows=selected_rows_info,
        row_entry=row_entry_metrics,
        used_by_row=used_by_row,
    )
    relaxation_eval: dict[str, Any] | None = None
    relaxation_rounds: list[dict[str, Any]] = []
    if (
        relaxation_plan
        and _auto_retry_depth == 0
        and bool(settings.optimizer.relaxation_simulation_enabled)
    ):
        cumulative_overrides: dict[int, dict[str, float]] = {}
        cur_viol = list(hard_violations)
        cur_selected_rows = list(selected_rows_info)
        cur_used_by_row = dict(used_by_row)
        combined_plan: list[dict[str, Any]] = []

        for ridx in range(1, 4):
            step_plan = _build_relaxation_plan(
                hard_violations=cur_viol,
                selected_rows=cur_selected_rows,
                row_entry=row_entry_metrics,
                used_by_row=cur_used_by_row,
            )
            if not step_plan:
                break
            for step in step_plan:
                s = dict(step)
                s["round"] = ridx
                combined_plan.append(s)
                row = s.get("row")
                if not isinstance(row, int):
                    continue
                ov = cumulative_overrides.setdefault(row, {})
                if s.get("action") == "relax_min" and s.get("suggest_new_min_g") is not None:
                    ov["min_g"] = float(s["suggest_new_min_g"])
                elif s.get("action") == "relax_daymax" and s.get("suggest_new_daymax_g") is not None:
                    ov["daymax_g"] = float(s["suggest_new_daymax_g"])

            sim = solve_day_meal_plan(
                settings=settings,
                indicators=indicators,
                meal_pattern_parts=meal_pattern_parts,
                candidates_by_item=candidates_by_item,
                visible_meals=visible_meals,
                rice_token=rice_token,
                day_offset=day_offset,
                reroll_nonce=reroll_nonce + 19 + ridx,
                focus_multiplier=focus_multiplier,
                fixed_nutrients=fixed_nutrients,
                _auto_retry_depth=2,
                bound_overrides=cumulative_overrides,
            )
            if sim is None or not isinstance(sim.diagnostics, dict):
                relaxation_eval = {
                    "simulated_with_plan_hard_feasible": False,
                    "simulated_remaining_violations": [],
                    "simulated_score": None,
                    "note": "模擬求解未得到可用結果（可能模型無解或 solver 失敗）。",
                }
                break
            sim_viol = sim.diagnostics.get("hard_violations", [])
            sim_feasible = bool(sim.diagnostics.get("hard_feasible", False))
            round_info = {
                "round": ridx,
                "score": _violation_score(sim_viol, settings=settings),
                "hard_feasible": sim_feasible,
                "actions_count": len(step_plan),
            }
            relaxation_rounds.append(round_info)
            relaxation_eval = {
                "simulated_with_plan_hard_feasible": sim_feasible,
                "simulated_remaining_violations": sim_viol if isinstance(sim_viol, list) else [],
                "simulated_score": _violation_score(sim_viol, settings=settings),
                "round": ridx,
            }
            if sim_feasible:
                break
            cur_viol = sim_viol if isinstance(sim_viol, list) else cur_viol
            if isinstance(sim.state, dict):
                cur_selected_rows = list(sim.state.get("selected_rows_info", cur_selected_rows))
                cur_used_by_row = dict(sim.state.get("used_by_row", cur_used_by_row))

        relaxation_plan = combined_plan or relaxation_plan

    parameter_changes = _build_parameter_changes(relaxation_plan)
    diagnostics = {
        "solver_status": status,
        "hard_feasible": hard_feasible,
        "hard_violations": hard_violations,
        "daymax_tight_rows": daymax_tight,
        "recommendations": recommendations,
        "relaxation_plan": relaxation_plan,
        "parameter_changes": parameter_changes,
        "constraint_analysis": _build_constraint_analysis(
            hard_violations=hard_violations,
            daymax_tight_rows=daymax_tight,
            selected_rows=selected_rows_info,
            parameter_changes=parameter_changes,
        ),
        "relaxation_plan_eval": relaxation_eval,
        "relaxation_plan_rounds": relaxation_rounds,
        "auto_retry_used": False,
        "auto_retry_rounds": 0,
        "replacement_applied": False,
    }
    replacement_candidate: SolveArtifacts | None = None
    if _auto_retry_depth == 0 and bool(settings.optimizer.replacement_search_enabled):
        rep = _search_replacement_plan(
            solve_fn=solve_day_meal_plan,
            settings=settings,
            indicators=indicators,
            meal_pattern_parts=meal_pattern_parts,
            candidates_by_item=candidates_by_item,
            visible_meals=visible_meals,
            rice_token=rice_token,
            day_offset=day_offset,
            reroll_nonce=reroll_nonce,
            focus_multiplier=focus_multiplier,
            fixed_nutrients=fixed_nutrients,
            bound_overrides=bound_overrides,
            by_item=by_item,
            selected_rows_info=selected_rows_info,
            base_violations=hard_violations,
        )
        replacement_candidate = rep.get("artifact") if isinstance(rep, dict) else None
        if isinstance(rep, dict):
            rep = dict(rep)
            rep.pop("artifact", None)
            diagnostics["replacement_search"] = rep
    elif _auto_retry_depth == 0:
        diagnostics["replacement_search"] = {
            "enabled": False,
            "attempts": 0,
            "plan": [],
        }

    # 自動再試：第一次硬不可行時，用多輪策略（低脂/補鈣/補熱量）再求解。
    if (
        not hard_feasible
        and _auto_retry_depth == 0
        and bool(settings.optimizer.auto_retry_enabled)
    ):
        # 最多 6 輪：基礎放大 + 針對三難局（kcal低、鈣低、總脂高）偏置 + nonce 擾動
        retry_plans = build_auto_retry_plans(hard_violations, reroll_nonce)

        best_artifact: SolveArtifacts | None = None
        best_score = _violation_score(hard_violations, settings=settings)
        rounds = 0
        for focus_map, retry_nonce in retry_plans:
            rounds += 1
            retry = solve_day_meal_plan(
                settings=settings,
                indicators=indicators,
                meal_pattern_parts=meal_pattern_parts,
                candidates_by_item=candidates_by_item,
                visible_meals=visible_meals,
                rice_token=rice_token,
                day_offset=day_offset,
                reroll_nonce=retry_nonce,
                focus_multiplier=focus_map,
                fixed_nutrients=fixed_nutrients,
                _auto_retry_depth=1,
                bound_overrides=bound_overrides,
            )
            if retry is None or not isinstance(retry.diagnostics, dict):
                continue
            retry_score = _violation_score(retry.diagnostics.get("hard_violations", []), settings=settings)
            if retry_score < best_score:
                best_score = retry_score
                best_artifact = retry

        diagnostics["auto_retry_rounds"] = rounds
        if best_artifact is not None and isinstance(best_artifact.diagnostics, dict):
            rep_best: dict[str, Any] | None = None
            rep_best_art: SolveArtifacts | None = None
            if bool(settings.optimizer.replacement_search_enabled):
                # 以 auto-retry 較佳方案為基準，再做一次替換搜索。
                rep_best = _search_replacement_plan(
            solve_fn=solve_day_meal_plan,
                    settings=settings,
                    indicators=indicators,
                    meal_pattern_parts=meal_pattern_parts,
                    candidates_by_item=candidates_by_item,
                    visible_meals=visible_meals,
                    rice_token=rice_token,
                    day_offset=day_offset,
                    reroll_nonce=reroll_nonce + 97,
                    focus_multiplier=focus_multiplier,
                    fixed_nutrients=fixed_nutrients,
                    bound_overrides=bound_overrides,
                    by_item=by_item,
                    selected_rows_info=list((best_artifact.state or {}).get("selected_rows_info", [])),
                    base_violations=list(best_artifact.diagnostics.get("hard_violations", [])),
                )
                rep_best_art = rep_best.get("artifact") if isinstance(rep_best, dict) else None
            best_artifact.diagnostics["auto_retry_used"] = True
            best_artifact.diagnostics["auto_retry_rounds"] = rounds
            if isinstance(rep_best, dict):
                rep_best = dict(rep_best)
                rep_best.pop("artifact", None)
                best_artifact.diagnostics["replacement_search"] = rep_best
            elif "replacement_search" not in best_artifact.diagnostics:
                best_artifact.diagnostics["replacement_search"] = {
                    "enabled": False,
                    "attempts": 0,
                    "plan": [],
                }
            if best_artifact.diagnostics.get("relaxation_plan_eval") is None:
                best_artifact.diagnostics["relaxation_plan_eval"] = diagnostics.get("relaxation_plan_eval")
            if not best_artifact.diagnostics.get("relaxation_plan"):
                best_artifact.diagnostics["relaxation_plan"] = diagnostics.get("relaxation_plan", [])
            if not best_artifact.diagnostics.get("relaxation_plan_rounds"):
                best_artifact.diagnostics["relaxation_plan_rounds"] = diagnostics.get("relaxation_plan_rounds", [])
            if isinstance(rep_best_art, SolveArtifacts) and isinstance(rep_best_art.diagnostics, dict):
                rep_score = _violation_score(rep_best_art.diagnostics.get("hard_violations", []), settings=settings)
                best_score_now = _violation_score(best_artifact.diagnostics.get("hard_violations", []), settings=settings)
                if rep_score < best_score_now:
                    rep_best_art.diagnostics["auto_retry_used"] = True
                    rep_best_art.diagnostics["auto_retry_rounds"] = rounds
                    rep_best_art.diagnostics["replacement_applied"] = True
                    rep_best_art.diagnostics["replacement_search"] = best_artifact.diagnostics.get("replacement_search")
                    return rep_best_art
            return best_artifact

    if isinstance(replacement_candidate, SolveArtifacts) and isinstance(replacement_candidate.diagnostics, dict):
        rep_score = _violation_score(replacement_candidate.diagnostics.get("hard_violations", []), settings=settings)
        base_score = _violation_score(hard_violations, settings=settings)
        if rep_score < base_score:
            replacement_candidate.diagnostics["replacement_applied"] = True
            replacement_candidate.diagnostics["replacement_search"] = diagnostics.get("replacement_search")
            return replacement_candidate

    return SolveArtifacts(
        meal_ingredients=out_meal_ingredients,
        meal_nutrients=out_meal_nutrients,
        meal_items=out_meal_items,
        status=status,
        diagnostics=diagnostics,
        state={
            "selected_rows_info": selected_rows_info,
            "used_by_row": used_by_row,
            "row_entry_metrics": row_entry_metrics,
        },
    )

