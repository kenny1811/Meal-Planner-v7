"""Diagnostics, violation scoring, and user-facing recommendations."""

from __future__ import annotations

from typing import Any

from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings
from meal_planner.optimizer_models import _Candidate


_NUTRIENT_LABELS = {
    "kcal": "卡路里",
    "protein_g": "蛋白質",
    "carb_g": "碳水",
    "sugar_g": "天然糖",
    "cholesterol_mg": "膽固醇",
    "sodium_mg": "鈉",
    "calcium_mg": "鈣",
    "fat_total_g": "總脂肪",
    "fat_sat_g": "飽和脂肪",
    "fat_trans_g": "反式脂肪",
}

_CONSTRAINT_LABELS = {
    "low": "低過下限",
    "high": "高過上限",
    "fat_cap": "高過脂肪比例上限",
}


def _fmt_num(x: Any) -> str:
    try:
        n = float(x)
    except (TypeError, ValueError):
        return str(x)
    if abs(n - round(n)) < 0.05:
        return str(int(round(n)))
    return f"{n:.1f}"


def _top_contributors(
    selected: list[tuple[_Candidate, float]],
    nutrient_key: str,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c, grams in selected:
        contrib = float(c.entry.nutrients.get(nutrient_key, 0.0)) * float(grams) / 100.0
        if contrib <= 0:
            continue
        rows.append(
            {
                "name": c.entry.name,
                "meal": c.meal,
                "grams": round(float(grams), 1),
                "contribution": round(contrib, 2),
            }
        )
    rows.sort(key=lambda x: float(x["contribution"]), reverse=True)
    return rows[:top_n]


def _build_recommendations(
    *,
    hard_violations: list[dict[str, Any]],
    daymax_tight_rows: list[dict[str, Any]],
    selected: list[tuple[_Candidate, float]],
    all_candidates: list[_Candidate],
    used_by_row: dict[int, float],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not hard_violations:
        return out

    violation_map: dict[tuple[str, str], float] = {}
    for v in hard_violations:
        key = (str(v.get("nutrient", "")), str(v.get("constraint", "")))
        violation_map[key] = float(v.get("gap", 0.0) or 0.0)

    tight_rows = {int(x["row"]) for x in daymax_tight_rows if isinstance(x.get("row"), int)}

    # row 去重（候選列表會重複同一 row）
    row_entry: dict[int, NutritionEntry] = {}
    for c in all_candidates:
        row_entry[c.entry.row_index] = c.entry

    if ("fat_total_g", "fat_cap") in violation_map:
        fat_top = _top_contributors(selected, "fat_total_g")
        msg = "總脂肪超上限，先減高脂來源（尤其油、堅果/芝麻類、高脂零食）或下調其 Min(g)。"
        if fat_top:
            msg += " 主要來源：" + "、".join(f"{x['meal']}:{x['name']}({x['contribution']})" for x in fat_top)
        out.append(
            {
                "issue": "fat_total_g/fat_cap",
                "priority": "high",
                "message": msg,
            }
        )

    if ("calcium_mg", "low") in violation_map:
        calcium_candidates: list[dict[str, Any]] = []
        for row_idx, e in row_entry.items():
            per100 = float(e.nutrients.get("calcium_mg", 0.0))
            if per100 <= 0:
                continue
            daymax = float(e.daymax_g) if e.daymax_g is not None else None
            used = float(used_by_row.get(row_idx, 0.0))
            headroom = max(0.0, daymax - used) if daymax is not None else None
            if headroom is not None and headroom <= 0:
                continue
            # 估算可額外提供鈣（未設 daymax 時以 100g 作保守參考）
            delta_g = headroom if headroom is not None else 100.0
            delta_ca = per100 * delta_g / 100.0
            calcium_candidates.append(
                {
                    "name": e.name,
                    "row": row_idx,
                    "daymax_headroom_g": None if headroom is None else round(headroom, 1),
                    "estimated_extra_calcium_mg": round(delta_ca, 1),
                }
            )
        calcium_candidates.sort(key=lambda x: float(x["estimated_extra_calcium_mg"]), reverse=True)
        top_ca = calcium_candidates[:3]
        msg = "鈣不足，建議優先增加高鈣且仍有 DayMax 餘量嘅食材；若冇餘量，需放寬相關 DayMax 或加入新高鈣候選。"
        if top_ca:
            msg += " 可優先考慮：" + "、".join(
                f"{x['name']}(+~{x['estimated_extra_calcium_mg']}mg)"
                for x in top_ca
            )
        if tight_rows:
            msg += "；目前貼 DayMax 行：" + "、".join(str(r) for r in sorted(tight_rows))
        out.append(
            {
                "issue": "calcium_mg/low",
                "priority": "high",
                "message": msg,
                "candidates": top_ca,
            }
        )

    if ("kcal", "low") in violation_map:
        kcal_gap = violation_map[("kcal", "low")]
        fat_over = violation_map.get(("fat_total_g", "fat_cap"), 0.0)
        msg = (
            f"卡路里不足約 {kcal_gap:.1f}，建議優先加低脂碳水/低脂蛋白來源；"
            "若同時總脂肪超標，應先減油，再把熱量轉去米/燕麥/低脂蛋白。"
        )
        if fat_over > 0:
            msg += f"（現時脂肪超標約 {fat_over:.1f}g）"
        out.append(
            {
                "issue": "kcal/low",
                "priority": "high",
                "message": msg,
            }
        )

    if ("protein_g", "high") in violation_map:
        p_top = _top_contributors(selected, "protein_g")
        msg = "蛋白質略高，若要嚴格硬達標可先下調蛋白粉/高蛋白主菜 Min(g)。"
        if p_top:
            msg += " 主要來源：" + "、".join(f"{x['meal']}:{x['name']}({x['contribution']})" for x in p_top)
        out.append(
            {
                "issue": "protein_g/high",
                "priority": "medium",
                "message": msg,
            }
        )

    return out


def _violation_score(
    hard_violations: list[dict[str, Any]] | Any,
    settings: AppSettings | None = None,
) -> tuple[float, float]:
    """
    越細越好：先比加權違規項數量，再比加權缺口/超標量。

    總脂肪 cap 用較高權重，避免無解時為追其他目標而選中總脂肪超標方案。
    """
    if not isinstance(hard_violations, list):
        return (10**9, 10**9)
    cnt = 0.0
    total_gap = 0.0
    for x in hard_violations:
        if not isinstance(x, dict):
            continue
        gap = float(x.get("gap", 0.0) or 0.0)
        if gap > 1e-5:
            nutrient = str(x.get("nutrient", ""))
            constraint = str(x.get("constraint", ""))
            weight = 1.0
            if constraint == "fat_cap" and settings is not None:
                if nutrient == "fat_total_g":
                    weight = max(1.0, float(settings.optimizer.fat_cap_weights.total))
                elif nutrient == "fat_sat_g":
                    weight = max(1.0, float(settings.optimizer.fat_cap_weights.saturated))
                elif nutrient == "fat_trans_g":
                    weight = max(1.0, float(settings.optimizer.fat_cap_weights.trans))
            cnt += weight
            total_gap += weight * gap
    return (cnt, total_gap)


def _build_parameter_changes(relaxation_plan: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    """
    把 relaxation_plan 轉成可直接改 Excel 的參數清單（Min/Max/DayMax）。
    同一 row+parameter 多次出現時取較大調整值（較保守，減少來回追改）。
    """
    if not isinstance(relaxation_plan, list):
        return []
    merged: dict[tuple[int, str], dict[str, Any]] = {}
    for step in relaxation_plan:
        if not isinstance(step, dict):
            continue
        row = step.get("row")
        name = step.get("name")
        if not isinstance(row, int):
            continue
        if step.get("action") == "relax_min" and step.get("suggest_new_min_g") is not None:
            key = (row, "Min (g)")
            cur = merged.get(key)
            nxt = float(step["suggest_new_min_g"])
            if cur is None or nxt < float(cur["suggest_value"]):
                merged[key] = {
                    "row": row,
                    "name": name,
                    "parameter": "Min (g)",
                    "suggest_value": round(nxt, 1),
                }
        if step.get("action") == "relax_daymax" and step.get("suggest_new_daymax_g") is not None:
            key = (row, "DayMax (g)")
            cur = merged.get(key)
            nxt = float(step["suggest_new_daymax_g"])
            if cur is None or nxt > float(cur["suggest_value"]):
                merged[key] = {
                    "row": row,
                    "name": name,
                    "parameter": "DayMax (g)",
                    "suggest_value": round(nxt, 1),
                }
        also = step.get("also_relax_max")
        if isinstance(also, dict) and also.get("suggest_new_max_g") is not None:
            key = (row, "Max (g)")
            cur = merged.get(key)
            nxt = float(also["suggest_new_max_g"])
            if cur is None or nxt > float(cur["suggest_value"]):
                merged[key] = {
                    "row": row,
                    "name": name,
                    "parameter": "Max (g)",
                    "suggest_value": round(nxt, 1),
                }
    out = list(merged.values())
    out.sort(key=lambda x: (int(x["row"]), str(x["parameter"])))
    return out


def _build_constraint_analysis(
    *,
    hard_violations: list[dict[str, Any]],
    daymax_tight_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    parameter_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    User-facing infeasibility explanation for restricted-diet use.

    It deliberately avoids suggesting new ingredients. The only proposed levers are
    existing Excel parameters or nutrient targets, which keeps FODMAP/medical food
    constraints outside the optimizer's recommendation surface.
    """
    if not hard_violations:
        return {
            "status": "feasible",
            "summary": "現有食材、份量上下限同營養目標可以同時滿足。",
            "violations": [],
            "binding_limits": [],
            "existing_parameter_changes": [],
            "target_options": [],
        }

    violations: list[dict[str, Any]] = []
    for v in hard_violations:
        nutrient = str(v.get("nutrient", ""))
        constraint = str(v.get("constraint", ""))
        gap = float(v.get("gap", 0.0) or 0.0)
        violations.append(
            {
                "nutrient": nutrient,
                "constraint": constraint,
                "gap": round(gap, 1),
                "label": f"{_NUTRIENT_LABELS.get(nutrient, nutrient)}{_CONSTRAINT_LABELS.get(constraint, constraint)} {_fmt_num(gap)}",
            }
        )

    binding_limits: list[dict[str, Any]] = []
    for x in daymax_tight_rows:
        if not isinstance(x, dict):
            continue
        binding_limits.append(
            {
                "row": x.get("row"),
                "name": x.get("name"),
                "used_g": x.get("used_g"),
                "daymax_g": x.get("daymax_g"),
                "label": f"{x.get('name', 'row ' + str(x.get('row')))} 已用 {_fmt_num(x.get('used_g'))}g / DayMax {_fmt_num(x.get('daymax_g'))}g",
            }
        )

    target_options: list[dict[str, Any]] = []
    for v in violations:
        nutrient = str(v.get("nutrient", ""))
        constraint = str(v.get("constraint", ""))
        gap = float(v.get("gap", 0.0) or 0.0)
        label = _NUTRIENT_LABELS.get(nutrient, nutrient)
        if constraint == "low":
            target_options.append(
                {
                    "nutrient": nutrient,
                    "direction": "lower_minimum",
                    "gap": round(gap, 1),
                    "label": f"若不改食材/份量限制，需接受 {label} 下限降低約 {_fmt_num(gap)}。",
                }
            )
        elif constraint == "high":
            target_options.append(
                {
                    "nutrient": nutrient,
                    "direction": "raise_maximum",
                    "gap": round(gap, 1),
                    "label": f"若不改食材/份量限制，需接受 {label} 上限提高約 {_fmt_num(gap)}。",
                }
            )
        elif constraint == "fat_cap":
            target_options.append(
                {
                    "nutrient": nutrient,
                    "direction": "raise_fat_cap",
                    "gap": round(gap, 1),
                    "label": f"若不改食材/份量限制，需接受 {label} 比例上限放寬約 {_fmt_num(gap)}g 等值。",
                }
            )

    selected_by_row = {
        int(x["row"]): x
        for x in selected_rows
        if isinstance(x, dict) and isinstance(x.get("row"), int)
    }
    existing_parameter_changes: list[dict[str, Any]] = []
    for change in parameter_changes:
        if not isinstance(change, dict):
            continue
        row = change.get("row")
        selected = selected_by_row.get(row) if isinstance(row, int) else None
        current = None
        param = str(change.get("parameter", ""))
        if selected:
            if param == "Max (g)":
                current = selected.get("max_g")
            elif param == "DayMax (g)":
                current = selected.get("daymax_g")
            elif param == "Min (g)":
                current = selected.get("min_g")
        item = dict(change)
        item["current_value"] = current
        if current is None:
            item["label"] = f"現有食材 row {row}「{change.get('name')}」：{param} 建議改至 {_fmt_num(change.get('suggest_value'))}g"
        else:
            item["label"] = f"現有食材 row {row}「{change.get('name')}」：{param} {_fmt_num(current)}g -> {_fmt_num(change.get('suggest_value'))}g"
        existing_parameter_changes.append(item)

    return {
        "status": "infeasible",
        "summary": "現有 FODMAP/醫療限制食材清單、份量上下限同營養目標未能同時滿足；fast mode 只影響搜尋深度，唔會改變呢個限制衝突。",
        "violations": violations,
        "binding_limits": binding_limits,
        "existing_parameter_changes": existing_parameter_changes,
        "target_options": target_options,
        "manual_override_note": "如只想做單日寬限，請直接在該日餐單格改現有食材克數後按 Recalculate；不要為單日需要修改營養清單的全局 Max/DayMax。",
        "no_new_foods_suggested": True,
    }

