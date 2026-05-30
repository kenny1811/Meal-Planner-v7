"""Relaxation suggestions for hard-infeasible optimizer results."""

from __future__ import annotations

from typing import Any
import math


def _build_relaxation_plan(
    *,
    hard_violations: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    row_entry: dict[int, dict[str, Any]],
    used_by_row: dict[int, float],
) -> list[dict[str, Any]]:
    """
    只提供「最少放寬」建議（不改表）：
    - 放寬某食材 Min(g)（多用於降脂）
    - 放寬某食材 DayMax(g)（多用於補鈣/補熱量）
    """
    if not hard_violations:
        return []
    vmap: dict[tuple[str, str], float] = {}
    for v in hard_violations:
        vmap[(str(v.get("nutrient", "")), str(v.get("constraint", "")))] = float(v.get("gap", 0.0) or 0.0)

    plan: list[dict[str, Any]] = []
    selected_by_row: dict[int, list[dict[str, Any]]] = {}
    for r in selected_rows:
        row = r.get("row")
        if isinstance(row, int):
            selected_by_row.setdefault(row, []).append(r)

    def _buffered_delta(need_g: float) -> float:
        # 避免每次只加少少：加 30% 緩衝，最少 10g。
        return max(10.0, float(need_g) * 1.3)

    def _round_up_to_step(x: float, step: float = 10.0) -> float:
        if step <= 0:
            return float(x)
        return math.ceil(float(x) / step) * step

    # 1) fat cap 超標：優先建議下調高脂項 Min(g)
    #    但若 Min==Max（固定份量，例如一條棒），不可建議切半份。
    fat_over = vmap.get(("fat_total_g", "fat_cap"), 0.0)
    if fat_over > 0:
        fat_rows = [
            r
            for r in selected_rows
            if (
                r["fat"] > 0
                and r["min_g"] > 0
                and (
                    r.get("max_g") is None
                    or abs(float(r.get("max_g") or 0.0) - float(r.get("min_g") or 0.0)) > 1e-6
                )
            )
        ]
        fat_rows.sort(key=lambda r: (r["fat"], r["grams"]), reverse=True)
        if fat_rows:
            r = fat_rows[0]
            need_reduce_g = fat_over * 100.0 / max(r["fat"], 1e-6)
            suggest_delta = min(r["min_g"], max(1.0, need_reduce_g))
            plan.append(
                {
                    "action": "relax_min",
                    "row": r["row"],
                    "name": r["name"],
                    "meal": r["meal"],
                    "current_min_g": round(r["min_g"], 1),
                    "suggest_delta_g": round(suggest_delta, 1),
                    "suggest_new_min_g": round(max(0.0, r["min_g"] - suggest_delta), 1),
                    "reason": f"總脂肪超標約 {fat_over:.1f}g，先減最濃脂來源嘅 Min(g)。",
                }
            )
        else:
            plan.append(
                {
                    "action": "replace_fixed_item",
                    "row": None,
                    "name": "固定份量項目",
                    "reason": f"總脂肪超標約 {fat_over:.1f}g，但現有高脂來源屬固定份量（Min=Max），建議改 Pattern 候選或換低脂等價食材。",
                }
            )

    # 2) calcium 低：優先建議放寬高鈣項 DayMax(g)
    ca_gap = vmap.get(("calcium_mg", "low"), 0.0)
    if ca_gap > 0:
        ca_rows = []
        for row, e in row_entry.items():
            if int(row) not in selected_by_row:
                continue
            ca = float(e.get("calcium", 0.0))
            if ca <= 0:
                continue
            fat = float(e.get("fat", 0.0))
            used = float(used_by_row.get(row, 0.0))
            dm = float(e["daymax_g"]) if e.get("daymax_g") is not None else None
            headroom = None if dm is None else max(0.0, dm - used)
            ca_rows.append(
                {
                    "row": row,
                    "name": e.get("name", f"row{row}"),
                    "ca": ca,
                    "fat": fat,
                    "daymax": dm,
                    "headroom": headroom,
                }
            )
        # 優先揀「當前解有用到」的高鈣低脂食材，避免建議落在未選中的行。
        ca_rows.sort(
            key=lambda x: (
                1 if int(x["row"]) in selected_by_row else 0,
                x["ca"] / max(x["fat"], 0.1),
                x["ca"],
            ),
            reverse=True,
        )
        target = next((x for x in ca_rows if x["daymax"] is not None), ca_rows[0] if ca_rows else None)
        if target is not None:
            need_g = ca_gap * 100.0 / max(target["ca"], 1e-6)
            row = int(target["row"])
            picked = selected_by_row.get(row, [])
            current_total = float(used_by_row.get(row, 0.0))
            max_headroom = 0.0
            max_vals = [float(x.get("max_g") or 0.0) for x in picked if x.get("max_g") is not None]
            if picked and max_vals:
                max_headroom = max(0.0, sum(max_vals) - current_total)
            need_raise_max_total = max(0.0, need_g - max_headroom)
            if target["daymax"] is not None:
                delta = _buffered_delta(need_g)
                new_daymax = _round_up_to_step(float(target["daymax"]) + delta, 10.0)
                step = {
                    "action": "relax_daymax",
                    "row": row,
                    "name": target["name"],
                    "current_daymax_g": round(float(target["daymax"]), 1),
                    "suggest_delta_g": round(max(1.0, new_daymax - float(target["daymax"])), 1),
                    "suggest_new_daymax_g": round(new_daymax, 1),
                    "reason": f"鈣不足約 {ca_gap:.1f}mg，放寬高鈣來源 DayMax（已加緩衝同取整，減少再追改）。",
                }
                if need_raise_max_total > 1e-6:
                    cur_max = float(max_vals[0]) if max_vals else None
                    if cur_max is not None:
                        per_item_raise = need_raise_max_total / max(len(picked), 1)
                        step["also_relax_max"] = {
                            "current_max_g": round(cur_max, 1),
                            "suggest_delta_g": round(per_item_raise, 1),
                            "suggest_new_max_g": round(cur_max + per_item_raise, 1),
                        }
                        step["reason"] += " 目前已觸及 Max，需同步放寬 Max(g)。"
                plan.append(step)

    # 3) kcal 低：建議放寬低脂高熱量來源 DayMax(g)
    kcal_gap = vmap.get(("kcal", "low"), 0.0)
    if kcal_gap > 0:
        k_rows = []
        for row, e in row_entry.items():
            if int(row) not in selected_by_row:
                continue
            kcal = float(e.get("kcal", 0.0))
            fat = float(e.get("fat", 0.0))
            # 避免為補熱量而建議大幅增加低熱量蔬果（例如車厘茄上千克）。
            # 若現有可用食材沒有合理熱量密度，就應回報目標/餐次限制衝突。
            if kcal < 80:
                continue
            dm = float(e["daymax_g"]) if e.get("daymax_g") is not None else None
            if dm is None:
                continue
            k_rows.append(
                {
                    "row": row,
                    "name": e.get("name", f"row{row}"),
                    "kcal": kcal,
                    "fat": fat,
                    "daymax": dm,
                    "score": kcal / max(fat, 0.2),
                }
            )
        k_rows.sort(
            key=lambda x: (
                1 if int(x["row"]) in selected_by_row else 0,
                x["score"],
                x["kcal"],
            ),
            reverse=True,
        )
        target_k = next((x for x in k_rows if int(x["row"]) in selected_by_row), None) or (k_rows[0] if k_rows else None)
        if target_k is not None:
            need_g = kcal_gap * 100.0 / max(target_k["kcal"], 1e-6)
            row = int(target_k["row"])
            picked = selected_by_row.get(row, [])
            current_total = float(used_by_row.get(row, 0.0))
            max_headroom = 0.0
            max_vals = [float(x.get("max_g") or 0.0) for x in picked if x.get("max_g") is not None]
            if picked and max_vals:
                max_headroom = max(0.0, sum(max_vals) - current_total)
            need_raise_max_total = max(0.0, need_g - max_headroom)
            delta = _buffered_delta(need_g)
            new_daymax = _round_up_to_step(float(target_k["daymax"]) + delta, 10.0)
            step = {
                "action": "relax_daymax",
                "row": row,
                "name": target_k["name"],
                "current_daymax_g": round(float(target_k["daymax"]), 1),
                "suggest_delta_g": round(max(1.0, new_daymax - float(target_k["daymax"])), 1),
                "suggest_new_daymax_g": round(new_daymax, 1),
                "reason": f"熱量不足約 {kcal_gap:.1f}kcal，放寬低脂高熱量來源 DayMax（已加緩衝同取整）。",
            }
            if need_raise_max_total > 1e-6:
                cur_max = float(max_vals[0]) if max_vals else None
                if cur_max is not None:
                    per_item_raise = need_raise_max_total / max(len(picked), 1)
                    step["also_relax_max"] = {
                        "current_max_g": round(cur_max, 1),
                        "suggest_delta_g": round(per_item_raise, 1),
                        "suggest_new_max_g": round(cur_max + per_item_raise, 1),
                    }
                    step["reason"] += " 目前已觸及 Max，需同步放寬 Max(g)。"
            plan.append(step)

    return plan[:3]

