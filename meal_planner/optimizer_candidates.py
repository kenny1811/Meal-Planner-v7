"""Candidate construction and gram bound helpers."""

from __future__ import annotations

from meal_planner.nutrition_catalog import NutritionEntry
from meal_planner.settings import AppSettings
from meal_planner.optimizer_models import _Candidate


def _effective_max_g(entry: NutritionEntry, settings: AppSettings) -> float:
    floor = float(entry.min_g) if entry.min_g is not None else 0.0
    if entry.max_g is not None:
        return max(float(entry.max_g), floor)
    if entry.daymax_g is not None:
        return max(float(entry.daymax_g), floor)
    default_g = float(settings.nutrition_portion.default_g)
    return max(floor, default_g * 2.0)



def build_active_items_and_candidates(
    *,
    settings: AppSettings,
    meal_pattern_parts: dict[str, list[dict[str, object]]],
    candidates_by_item: dict[tuple[str, int], list[NutritionEntry]],
    visible_meals: set[str],
    rice_token: str,
    bound_overrides: dict[int, dict[str, float]] | None,
    forced_item_rows: dict[tuple[str, int], int] | None,
) -> tuple[list[tuple[str, int, dict[str, object]]], list[_Candidate]]:
    active_items: list[tuple[str, int, dict[str, object]]] = []
    candidates: list[_Candidate] = []
    singleton_min_pressure: dict[int, float] = {}

    for meal, items in meal_pattern_parts.items():
        if meal not in visible_meals:
            continue
        for i, item in enumerate(items):
            alts = item.get("alternatives", [])
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            item_candidates = candidates_by_item.get((meal, i), [])
            forced_row = (forced_item_rows or {}).get((meal, i))
            if forced_row is not None:
                item_candidates = [x for x in item_candidates if int(x.row_index) == int(forced_row)]
            if len(item_candidates) != 1:
                continue
            e = item_candidates[0]
            if e.daymax_g is None or e.min_g is None:
                continue
            singleton_min_pressure[e.row_index] = singleton_min_pressure.get(e.row_index, 0.0) + float(e.min_g)

    for meal, items in meal_pattern_parts.items():
        if meal not in visible_meals:
            continue
        for i, item in enumerate(items):
            active_items.append((meal, i, item))
            alts = item.get("alternatives", [])
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            item_candidates = candidates_by_item.get((meal, i), [])
            forced_row = (forced_item_rows or {}).get((meal, i))
            if forced_row is not None:
                item_candidates = [x for x in item_candidates if int(x.row_index) == int(forced_row)]
            is_rice_item = any((a or "").strip().lower() == rice_token for a in alts_list)
            for rank, e in enumerate(item_candidates):
                ov = (bound_overrides or {}).get(e.row_index, {})
                ov_min = ov.get("min_g")
                ov_daymax = ov.get("daymax_g")
                eff_min = float(ov_min) if ov_min is not None else (float(e.min_g) if e.min_g is not None else 0.0)
                eff_daymax = (
                    float(ov_daymax) if ov_daymax is not None else (float(e.daymax_g) if e.daymax_g is not None else None)
                )
                pressure = singleton_min_pressure.get(e.row_index, 0.0)
                if (
                    eff_daymax is not None
                    and pressure > eff_daymax
                    and len(item_candidates) == 1
                    and e.min_g is not None
                ):
                    # DayMax is the harder daily safety bound.  If a pattern repeats
                    # the same fixed ingredient so often that summed Min(g) already
                    # exceeds DayMax(g), reduce the slot minimum proportionally
                    # instead of making the whole MILP infeasible and falling back
                    # to non-optimised default portions.
                    eff_min = min(eff_min, float(int(max(0.0, eff_daymax * float(e.min_g) / pressure))))
                eff_max = _effective_max_g(e, settings)
                if e.max_g is None and eff_daymax is not None:
                    eff_max = max(eff_max, eff_daymax)
                candidates.append(
                    _Candidate(
                        meal=meal,
                        item_idx=i,
                        alt_key="|".join(alts_list),
                        entry=e,
                        min_g=eff_min,
                        max_g=max(eff_max, eff_min),
                        is_rice_item=is_rice_item,
                        rank=rank,
                    )
                )

    return active_items, candidates
