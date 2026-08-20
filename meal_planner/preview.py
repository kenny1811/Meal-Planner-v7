"""彙總：讀取維護表、更表、指標，產生含 MILP/LP 配餐結果的預覽 JSON。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from typing import Any

from meal_planner.dates_input import validate_dates_within_allowed_months
from meal_planner.format_rules import (
    error_font_red_calcium,
    error_font_red_fat_pct,
    error_font_red_range,
    error_font_red_upper_only,
    total_row_font_red_calcium,
    total_row_font_red_fat_pct,
    total_row_font_red_range,
    total_row_font_red_upper_only,
)
from meal_planner.meal_schedule import build_day_meal_plan, build_meal_planning_cache, build_rice_note
from meal_planner.indicators import (
    DayIndicatorProfile,
    IndicatorKind,
    NUTRIENT_KEYS,
    indicator_to_json,
    profile_from_json_map,
)
from meal_planner.nutrition_catalog import candidate_entries_from_alternatives
from meal_planner.nutrition_db import load_catalog_entries, load_target_rows
from meal_planner.patterns import parse_meal_patterns
from meal_planner.roster import code_for_date, load_roster_map
from meal_planner.maintenance_db import roster_code_defs
from meal_planner.roster_codes import is_work_day
from meal_planner.settings import AppSettings, get_settings


_FAT_PCT_KEYS = {"fat_total_g", "fat_sat_g", "fat_trans_g"}
_MEAL_NAMES = ("早餐", "午餐", "小食", "晚餐")


def _visible_meals_from_resolved(meal_plan: dict[str, Any]) -> set[str]:
    """由 meal_times_resolved 決定邊幾餐可見（非空時間字串）。"""
    resolved = meal_plan.get("meal_times_resolved", {}) if isinstance(meal_plan, dict) else {}
    if not isinstance(resolved, dict):
        return set()
    return {
        meal
        for meal in _MEAL_NAMES
        if resolved.get(meal) is not None and str(resolved.get(meal)).strip() != ""
    }


def _clear_restaurant_lunch_items(meal_plan: dict[str, Any]) -> None:
    """餐廳午餐模式：清空午餐配餐 item / 食材，令米類提示不當佢係米飯來源。"""
    if not isinstance(meal_plan, dict) or not isinstance(meal_plan.get("restaurant_lunch"), dict):
        return
    for key in ("meal_items", "meal_ingredients"):
        d = meal_plan.get(key)
        if isinstance(d, dict):
            d["午餐"] = []


def _apply_rice_note_and_summary(
    meal_plan: dict[str, Any],
    indicators: DayIndicatorProfile,
    settings: AppSettings,
    *,
    visible_meals: set[str] | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    """統一重算米類備註同全日 summary（清餐廳午餐後）。"""
    if visible_meals is None:
        visible_meals = _visible_meals_from_resolved(meal_plan)
    meal_items = meal_plan.get("meal_items", {}) if isinstance(meal_plan, dict) else {}
    meal_plan["rice_note"] = build_rice_note(meal_items, settings, visible_meals=visible_meals)
    meal_plan["summary"] = summary if summary is not None else _calc_day_summary(meal_plan, indicators, settings)


class IndicatorDataError(ValueError):
    pass


@dataclass(frozen=True)
class DayPreview:
    date: date
    roster_code: str | None
    is_work_day: bool | None
    indicator_profile: str  # "workday" | "nonworkday" | "missing_roster"

    def to_dict(
        self,
        nutrients_json: list[Any],
        meal_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        d: dict[str, Any] = {
            "date": self.date.isoformat(),
            "roster_code": self.roster_code,
            "is_work_day": self.is_work_day,
            "indicator_profile": self.indicator_profile,
            "nutrient_indicators": {NUTRIENT_KEYS[i]: nutrients_json[i] for i in range(len(NUTRIENT_KEYS))},
            "data_source": "sqlite",
        }
        if meal_plan is not None:
            d["meal_plan"] = meal_plan
        return d


def _serialize_profile(prof: DayIndicatorProfile) -> list[Any]:
    out: list[Any] = []
    for x in prof.nutrients:
        if x is None:
            out.append(None)
        else:
            out.append(indicator_to_json(x))
    return out


def _round1(x: float) -> float:
    return round(float(x), 1)


def _is_meal_visible(meal: str, meal_plan: dict[str, Any]) -> bool:
    resolved = meal_plan.get("meal_times_resolved", {}) if isinstance(meal_plan, dict) else {}
    r = resolved.get(meal) if isinstance(resolved, dict) else None
    if r is not None and str(r).strip() != "":
        return True
    if isinstance(resolved, dict) and meal in (resolved.get("_skipped") or {}):
        return False  # 行位表食位喺開工前，食唔到 —— 唔好經飯時原文復活佢
    primary = meal_plan.get("primary_rule", {}) if isinstance(meal_plan, dict) else {}
    raw = primary.get(meal) if isinstance(primary, dict) else None
    if raw is None:
        return False
    s = str(raw).strip()
    if not s:
        return False
    # 與前端一致：只有固定 HH:MM 視為可顯示時間
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", s))


def _fat_pct_for_indicator(key: str, indicator: Any) -> float:
    if (
        indicator is not None
        and getattr(indicator, "kind", None) == IndicatorKind.FAT_PCT
        and getattr(indicator, "fat_pct", None) is not None
    ):
        return float(indicator.fat_pct)
    raise IndicatorDataError(f"指標格式錯誤：{key} 必須係 '<x% kcal>'，不可讀取 config。")


def _calc_day_summary(
    meal_plan: dict[str, Any],
    indicators: DayIndicatorProfile,
    settings: AppSettings,
) -> dict[str, list[float]]:
    eps = 1e-9
    meals = meal_plan.get("meal_nutrients", {}) if isinstance(meal_plan, dict) else {}
    totals = {k: 0.0 for k in NUTRIENT_KEYS}
    for meal_name, m in meals.items():
        if not _is_meal_visible(str(meal_name), meal_plan):
            continue
        if not isinstance(m, dict):
            continue
        for k in NUTRIENT_KEYS:
            totals[k] += float(m.get(k, 0.0) or 0.0)

    kcal_total = totals["kcal"]
    errors: dict[str, float] = {}
    total_red_flags: dict[str, bool] = {}
    error_red_flags: dict[str, bool] = {}
    for i, k in enumerate(NUTRIENT_KEYS):
        p = indicators.nutrients[i] if i < len(indicators.nutrients) else None
        t = totals[k]
        e = 0.0
        total_red = False
        err_red = False
        if p is not None:
            if k in ("kcal", "protein_g", "carb_g") and p.kind == IndicatorKind.RANGE and p.lo is not None and p.hi is not None:
                if t < p.lo:
                    e = t - p.lo
                elif t > p.hi:
                    e = t - p.hi
                total_red = total_row_font_red_range(t, p.lo, p.hi)
                err_red = error_font_red_range(t, p.lo, p.hi)
            elif k in ("sugar_g", "cholesterol_mg", "sodium_mg") and p.kind == IndicatorKind.UPPER_ONLY and p.hi is not None:
                e = t - p.hi
                total_red = total_row_font_red_upper_only(t, p.hi)
                err_red = error_font_red_upper_only(t, p.hi)
            elif k == "calcium_mg" and p.kind == IndicatorKind.LOWER_ONLY and p.lo is not None:
                e = t - p.lo
                total_red = total_row_font_red_calcium(t, p.lo)
                err_red = error_font_red_calcium(t, p.lo)

        if k in _FAT_PCT_KEYS:
            pct = _fat_pct_for_indicator(k, p)
            cap = kcal_total * pct / settings.nutrition_format.kcal_per_fat_g if kcal_total > 0 else 0.0
            e = t - cap
            total_red = total_row_font_red_fat_pct(t, kcal_total, pct)
            err_red = error_font_red_fat_pct(t, kcal_total, pct)

        # 防止浮點尾差造成「顯示 0.0 但仍紅字」。
        # 只容許極細數值（浮點誤差）清零，避免把真實偏差吞掉。
        if abs(e) <= eps:
            e = 0.0
            err_red = False
        # UI 以 1 位小數顯示；若顯示上為 0.0，字色必須黑色。
        if _round1(e) == 0.0:
            err_red = False
        # UI 與字色一致：若顯示值（1 位小數）已達標，總計列必須黑色。
        disp_t = _round1(t)
        if p is not None:
            if k in ("kcal", "protein_g", "carb_g") and p.kind == IndicatorKind.RANGE and p.lo is not None and p.hi is not None:
                if p.lo <= disp_t <= p.hi:
                    total_red = False
            elif k in ("sugar_g", "cholesterol_mg", "sodium_mg") and p.kind == IndicatorKind.UPPER_ONLY and p.hi is not None:
                if disp_t <= p.hi:
                    total_red = False
            elif k == "calcium_mg" and p.kind == IndicatorKind.LOWER_ONLY and p.lo is not None:
                if disp_t >= p.lo:
                    total_red = False
        if k in ("fat_total_g", "fat_sat_g", "fat_trans_g") and _round1(e) == 0.0:
            total_red = False

        errors[k] = e
        total_red_flags[k] = bool(total_red)
        error_red_flags[k] = bool(err_red)

    return {
        "totals": [_round1(totals[k]) for k in NUTRIENT_KEYS],
        "errors": [_round1(errors[k]) for k in NUTRIENT_KEYS],
        "total_red_flags": [bool(total_red_flags[k]) for k in NUTRIENT_KEYS],
        "error_red_flags": [bool(error_red_flags[k]) for k in NUTRIENT_KEYS],
    }


def _validate_indicator_rows_or_raise(work_vals: list[Any], nonwork_vals: list[Any]) -> None:
    missing: list[str] = []
    invalid: list[str] = []
    for i in range(len(NUTRIENT_KEYS)):
        w = work_vals[i] if i < len(work_vals) else None
        n = nonwork_vals[i] if i < len(nonwork_vals) else None
        if w is None or str(w).strip() == "":
            missing.append(f"返工日/{NUTRIENT_KEYS[i]}")
        if n is None or str(n).strip() == "":
            missing.append(f"非返工日/{NUTRIENT_KEYS[i]}")
        if NUTRIENT_KEYS[i] in _FAT_PCT_KEYS:
            for label, raw in (("返工日", w), ("非返工日", n)):
                parsed = DayIndicatorProfile.from_row_cells([None] * i + [raw]).nutrients[i]
                if parsed is None or parsed.kind != IndicatorKind.FAT_PCT or parsed.fat_pct is None:
                    invalid.append(f"{label}/{NUTRIENT_KEYS[i]}")
    if missing:
        raise IndicatorDataError(
            "指標冇數據：餐單v5 頂部指標存在空白。缺少 -> " + ", ".join(missing)
        )
    if invalid:
        raise IndicatorDataError(
            "脂肪指標必須來自 target row，格式要係 '<x% kcal>'。錯誤 -> " + ", ".join(invalid)
        )


def preview_days(
    dates: list[date],
    *,
    skip_allowed_month_validation: bool = False,
    reroll_nonce: int = 0,
    fast_mode: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    if not fast_mode:
        settings = replace(
            settings,
            optimizer=replace(
                settings.optimizer,
                replacement_search_enabled=True,
                auto_retry_enabled=True,
                relaxation_simulation_enabled=True,
            ),
        )
    if not skip_allowed_month_validation:
        validate_dates_within_allowed_months(
            dates,
            timezone=settings.dates.timezone,
        )

    planning_cache = build_meal_planning_cache(settings)
    headers, work_vals, nonwork_vals = load_target_rows(settings)
    _validate_indicator_rows_or_raise(work_vals, nonwork_vals)
    roster = load_roster_map(settings)

    work_prof = DayIndicatorProfile.from_row_cells(list(work_vals))
    nonwork_prof = DayIndicatorProfile.from_row_cells(list(nonwork_vals))

    days_out: list[dict[str, Any]] = []
    for d in sorted(set(dates)):
        rm = roster.get((d.year, d.month))
        code = code_for_date(rm, d) if rm else None
        if code is None:
            prof_kind = "missing_roster"
            is_wd = None
            nutrients = DayIndicatorProfile.empty()
        else:
            is_wd = is_work_day(roster_code_defs(settings), code)
            prof_kind = "workday" if is_wd else "nonworkday"
            nutrients = work_prof if is_wd else nonwork_prof

        meal_plan = build_day_meal_plan(
            settings,
            code,
            is_wd,
            d,
            indicators=nutrients,
            reroll_nonce=reroll_nonce,
            cache=planning_cache,
        )
        meal_plan["summary"] = _calc_day_summary(meal_plan, nutrients, settings)

        dp = DayPreview(
            date=d,
            roster_code=code,
            is_work_day=is_wd,
            indicator_profile=prof_kind,
        )
        days_out.append(dp.to_dict(_serialize_profile(nutrients), meal_plan=meal_plan))

    return {
        "headers": [str(h) if h is not None else None for h in headers],
        "indicator_rows": {
            "workday": [str(v) if v is not None else "" for v in work_vals],
            "nonworkday": [str(v) if v is not None else "" for v in nonwork_vals],
        },
        "nutrient_keys": list(NUTRIENT_KEYS),
        "days": days_out,
        "fast_mode": bool(fast_mode),
    }


def _parse_edited_line(line: str | None) -> list[tuple[str, float | str | None]]:
    if not line:
        return []
    text = str(line).strip()
    if not text:
        return []
    # 容忍「早餐 - xxx+yyy」或直接「xxx+yyy」
    if "-" in text:
        text = text.split("-", 1)[1].strip()
    if text == "—":
        return []
    out: list[tuple[str, float | str | None]] = []
    for tok in [x.strip() for x in text.split("+") if x.strip()]:
        m = re.match(r"^(.*)\(\s*(\?|[-+]?\d*\.?\d+)\s*g?\s*\)$", tok, flags=re.IGNORECASE)
        if m:
            raw_g = m.group(2).strip()
            out.append((m.group(1).strip(), "?" if raw_g == "?" else float(raw_g)))
        else:
            out.append((tok, None))
    return out


def _summary_score(summary: dict[str, list[Any]]) -> tuple[float, float, float]:
    total_red = summary.get("total_red_flags", [])
    errors = summary.get("errors", [])
    red_count = 0
    violation = 0.0
    all_deviation = 0.0
    for i, e_raw in enumerate(errors if isinstance(errors, list) else []):
        try:
            e = float(e_raw or 0.0)
        except (TypeError, ValueError):
            e = 0.0
        is_red = bool(total_red[i]) if isinstance(total_red, list) and i < len(total_red) else False
        if is_red:
            red_count += 1
            violation += abs(e)
        all_deviation += abs(e)
    return (float(red_count), violation, all_deviation)


def recalc_days_from_edits(days_payload: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    entries = load_catalog_entries(settings)
    by_name = {e.name.strip().lower(): e for e in entries}

    out_days: list[dict[str, Any]] = []
    for d in days_payload:
        date_s = str(d.get("date") or "")
        meal_plan = d.get("meal_plan") if isinstance(d.get("meal_plan"), dict) else {}
        edited = d.get("edited_lines") if isinstance(d.get("edited_lines"), dict) else {}
        indicators_json = d.get("nutrient_indicators") if isinstance(d.get("nutrient_indicators"), dict) else {}
        indicators = profile_from_json_map(indicators_json)

        meal_items: dict[str, list[dict[str, object]]] = {}
        meal_ingredients: dict[str, list[str]] = {}
        meal_nutrients: dict[str, dict[str, float]] = {}
        old_items = meal_plan.get("meal_items", {}) if isinstance(meal_plan, dict) else {}
        old_ingredients = meal_plan.get("meal_ingredients", {}) if isinstance(meal_plan, dict) else {}
        old_nutrients = meal_plan.get("meal_nutrients", {}) if isinstance(meal_plan, dict) else {}
        unknown_candidates: list[dict[str, Any]] = []
        for meal in ("早餐", "午餐", "小食", "晚餐"):
            if meal not in edited:
                meal_items[meal] = list(old_items.get(meal, [])) if isinstance(old_items, dict) else []
                meal_ingredients[meal] = list(old_ingredients.get(meal, [])) if isinstance(old_ingredients, dict) else []
                base = old_nutrients.get(meal, {}) if isinstance(old_nutrients, dict) else {}
                meal_nutrients[meal] = {k: float(base.get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS}
                continue
            parsed = _parse_edited_line(edited.get(meal))
            items: list[dict[str, object]] = []
            names: list[str] = []
            nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
            computed_from_catalog = False
            for name, grams in parsed:
                key = name.strip().lower()
                entry = by_name.get(key)
                if entry is not None and isinstance(grams, (int, float)):
                    g = float(grams)
                    computed_from_catalog = True
                    items.append({"name": entry.name, "grams": g, "row": entry.row_index})
                    names.append(f"{entry.name}({g:.0f}g)")
                    ratio = g / 100.0
                    for k in NUTRIENT_KEYS:
                        nutrients[k] += float(entry.nutrients.get(k, 0.0)) * ratio
                elif entry is not None and grams == "?":
                    computed_from_catalog = True
                    idx = len(items)
                    items.append({"name": entry.name, "grams": "?", "row": entry.row_index})
                    names.append(f"{entry.name}(?g)")
                    unknown_candidates.append({"meal": meal, "item_idx": idx, "entry": entry})
                else:
                    items.append({"name": name, "grams": grams, "row": None})
                    if grams is None:
                        names.append(name)
                    elif grams == "?":
                        names.append(f"{name}(?g)")
                    else:
                        names.append(f"{name}({float(grams):.0f}g)")

            # 無法由文字有效重建（例如餐廳選擇餐/非克數格式）時，
            # 回退到原本該餐營養值，避免重算後變 0。
            if not computed_from_catalog:
                meal_items[meal] = list(old_items.get(meal, [])) if isinstance(old_items, dict) else []
                meal_ingredients[meal] = (
                    list(old_ingredients.get(meal, [])) if isinstance(old_ingredients, dict) else []
                )
                base = old_nutrients.get(meal, {}) if isinstance(old_nutrients, dict) else {}
                meal_nutrients[meal] = {k: float(base.get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS}
                continue
            meal_items[meal] = items
            meal_ingredients[meal] = names
            meal_nutrients[meal] = nutrients

        visible_meals = _visible_meals_from_resolved(meal_plan)
        meal_plan["meal_items"] = meal_items
        meal_plan["meal_ingredients"] = meal_ingredients
        meal_plan["meal_nutrients"] = meal_nutrients
        question_search_meta: dict[str, Any] | None = None
        best_summary: dict[str, Any] | None = None
        if unknown_candidates:
            target = unknown_candidates[0]
            meal = str(target["meal"])
            item_idx = int(target["item_idx"])
            entry = target["entry"]
            base_nutrients = {k: float(meal_nutrients.get(meal, {}).get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS}
            best_g = 1
            best_score: tuple[float, float, float] | None = None
            for g in range(1, 401):
                ratio = float(g) / 100.0
                meal_nutrients[meal] = {
                    k: base_nutrients[k] + float(entry.nutrients.get(k, 0.0)) * ratio
                    for k in NUTRIENT_KEYS
                }
                summary = _calc_day_summary(meal_plan, indicators, settings)
                score = _summary_score(summary)
                if best_score is None or score < best_score:
                    best_score = score
                    best_g = g
                    best_summary = summary
                    if score[0] == 0 and score[1] == 0:
                        # 已達標，之後只會用全偏差 tie-break；保留繼續試可能揀到更貼指標。
                        pass
            ratio = float(best_g) / 100.0
            meal_nutrients[meal] = {
                k: base_nutrients[k] + float(entry.nutrients.get(k, 0.0)) * ratio
                for k in NUTRIENT_KEYS
            }
            meal_items[meal][item_idx]["grams"] = float(best_g)
            meal_ingredients[meal] = [
                f"{str(it.get('name', '')).strip()}({float(it.get('grams')):.0f}g)"
                if isinstance(it.get("grams"), (int, float))
                else str(it.get("name", "")).strip()
                for it in meal_items[meal]
                if str(it.get("name", "")).strip()
            ]
            meal_plan["meal_items"] = meal_items
            meal_plan["meal_ingredients"] = meal_ingredients
            meal_plan["meal_nutrients"] = meal_nutrients
            question_search_meta = {
                "meal": meal,
                "name": entry.name,
                "row": entry.row_index,
                "best_g": best_g,
                "score": list(best_score or ()),
                "searched_min_g": 1,
                "searched_max_g": 400,
                "extra_unknown_count": max(0, len(unknown_candidates) - 1),
            }
        # 餐廳午餐模式下，米類提示不應計入午餐配餐 item。
        _clear_restaurant_lunch_items(meal_plan)
        _apply_rice_note_and_summary(
            meal_plan,
            indicators,
            settings,
            visible_meals=visible_meals,
            summary=best_summary if unknown_candidates and best_summary is not None else None,
        )
        # 一次性手動重算模式：只回報重算結果，不再要求改營養清單參數。
        meal_plan["optimization"] = {
            "mode": "manual_recalc",
            "status": "OK",
            "manual_override": True,
            "question_weight_search": question_search_meta,
            "recommendations": [],
            "relaxation_plan": [],
            "parameter_changes": [],
            "replacement_search": None,
            "replacement_applied": False,
            "auto_retry_used": False,
            "auto_retry_rounds": 0,
        }
        out_days.append({"date": date_s, "meal_plan": meal_plan})

    return {"days": out_days}


def resolve_day_out_of_stock(
    day_payload: dict[str, Any],
    locked_meal_names: list[str],
    forced_item_rows: dict[tuple[str, int], int] | None = None,
) -> dict[str, Any]:
    """
    Partial-day re-solve：鎖住已食餐（原內容當固定營養），只對其餘餐次重跑 MILP。
    營養清單嘅「暫停」旗喺呼叫前已更新，所以缺貨食材自然唔會再入候選。
    DayMax 會扣減已食餐消耗咗嘅克數。
    """
    settings = get_settings()
    # 單日 on-demand 重解，用 full-mode 求解機制（replacement search／auto-retry／
    # relaxation simulation）盡力達標；解唔到先回退最少違規方案。
    settings = replace(
        settings,
        optimizer=replace(
            settings.optimizer,
            replacement_search_enabled=True,
            auto_retry_enabled=True,
            relaxation_simulation_enabled=True,
        ),
    )
    date_s = str(day_payload.get("date") or "")
    d = date.fromisoformat(date_s)
    meal_plan_in = day_payload.get("meal_plan") if isinstance(day_payload.get("meal_plan"), dict) else {}
    indicators_json = day_payload.get("nutrient_indicators") if isinstance(day_payload.get("nutrient_indicators"), dict) else {}
    indicators = profile_from_json_map(indicators_json)

    planning_cache = build_meal_planning_cache(settings)
    roster = load_roster_map(settings)
    rm = roster.get((d.year, d.month))
    code = code_for_date(rm, d) if rm else None
    if code is None:
        raise ValueError(f"無 {date_s} 更表更碼，無法重解。")
    is_wd = is_work_day(roster_code_defs(settings), code)

    old_items = meal_plan_in.get("meal_items", {}) if isinstance(meal_plan_in.get("meal_items"), dict) else {}
    old_ings = meal_plan_in.get("meal_ingredients", {}) if isinstance(meal_plan_in.get("meal_ingredients"), dict) else {}
    old_nut = meal_plan_in.get("meal_nutrients", {}) if isinstance(meal_plan_in.get("meal_nutrients"), dict) else {}
    locked: dict[str, dict[str, Any]] = {}
    for meal in _MEAL_NAMES:
        if meal not in set(locked_meal_names or []):
            continue
        base = old_nut.get(meal, {}) if isinstance(old_nut.get(meal), dict) else {}
        locked[meal] = {
            "items": list(old_items.get(meal, []) or []),
            "ingredients": list(old_ings.get(meal, []) or []),
            "nutrients": {k: float(base.get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS},
        }

    # DayMax 扣已食：locked 餐消耗咗嘅克數唔會再喺 solver 度計，要由每日上限扣走。
    eaten_by_row: dict[int, float] = {}
    for data in locked.values():
        for it in data["items"]:
            row = it.get("row") if isinstance(it, dict) else None
            grams = it.get("grams") if isinstance(it, dict) else None
            try:
                row_i = int(row) if row is not None else None
            except (TypeError, ValueError):
                row_i = None
            if row_i is not None and isinstance(grams, (int, float)):
                eaten_by_row[row_i] = eaten_by_row.get(row_i, 0.0) + float(grams)
    entries_by_row = {e.row_index: e for e in planning_cache.nutrition_entries}
    bound_overrides: dict[int, dict[str, float]] = {}
    for row_i, grams in eaten_by_row.items():
        entry = entries_by_row.get(row_i)
        if entry is not None and entry.daymax_g is not None:
            bound_overrides[row_i] = {"daymax_g": max(0.0, float(entry.daymax_g) - grams)}

    meal_plan = build_day_meal_plan(
        settings,
        code,
        is_wd,
        d,
        indicators=indicators,
        cache=planning_cache,
        locked_meals=locked,
        bound_overrides=bound_overrides or None,
        forced_item_rows=forced_item_rows or None,
    )
    meal_plan["summary"] = _calc_day_summary(meal_plan, indicators, settings)
    return {"date": date_s, "meal_plan": meal_plan}


def meal_item_candidates() -> dict[str, Any]:
    """
    每個餐次每格可以揀咩食材（畀前端「指定食材」個 picker 用）。

    Pattern 表同日期／更碼無關（同一份 早餐／午餐／小食／晚餐 pattern），所以呢度
    唔使收日期。候選次序同內容跟足 solver 嗰條路（`candidate_entries_from_alternatives`
    會篩走暫停＝缺貨嘅食材），所以 picker 見到嘅就係 solver 真係揀得到嘅。
    """
    settings = get_settings()
    cache = build_meal_planning_cache(settings)
    parts = parse_meal_patterns(dict(cache.meal_patterns), settings.pattern)
    out: dict[str, Any] = {}
    for meal, items in parts.items():
        slots = []
        for i, item in enumerate(items):
            alts = item.get("alternatives", [])
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            entries = candidate_entries_from_alternatives(cache.nutrition_entries, alts_list)
            slots.append(
                {
                    "item_index": i,
                    "label": str(item.get("raw", "")).strip(),
                    "candidates": [{"row": int(e.row_index), "name": str(e.name)} for e in entries],
                }
            )
        out[meal] = slots
    return out


def refresh_payload_with_latest_indicators(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Refresh saved memory payload with latest SQLite indicator rows.

    Browser refresh loads memory_payload instead of generating a fresh preview, so this
    keeps the fixed top indicator panel and per-day summaries in sync with 餐單v5.
    """
    settings = get_settings()
    headers, work_vals, nonwork_vals = load_target_rows(settings)
    _validate_indicator_rows_or_raise(work_vals, nonwork_vals)

    work_prof = DayIndicatorProfile.from_row_cells(list(work_vals))
    nonwork_prof = DayIndicatorProfile.from_row_cells(list(nonwork_vals))
    work_json = _serialize_profile(work_prof)
    nonwork_json = _serialize_profile(nonwork_prof)

    refreshed = dict(payload)
    refreshed["headers"] = [str(h) if h is not None else None for h in headers]
    refreshed["indicator_rows"] = {
        "workday": [str(v) if v is not None else "" for v in work_vals],
        "nonworkday": [str(v) if v is not None else "" for v in nonwork_vals],
    }
    refreshed["nutrient_keys"] = list(NUTRIENT_KEYS)

    days_out: list[dict[str, Any]] = []
    for d in (payload.get("days", []) if isinstance(payload.get("days"), list) else []):
        if not isinstance(d, dict):
            continue
        nd = dict(d)
        is_wd = nd.get("is_work_day")
        if is_wd is True:
            nutrients_json = work_json
            indicators = work_prof
            nd["indicator_profile"] = "workday"
        elif is_wd is False:
            nutrients_json = nonwork_json
            indicators = nonwork_prof
            nd["indicator_profile"] = "nonworkday"
        else:
            nutrients_json = [None] * len(NUTRIENT_KEYS)
            indicators = DayIndicatorProfile.empty()
            nd["indicator_profile"] = nd.get("indicator_profile") or "missing_roster"

        nd["nutrient_indicators"] = {NUTRIENT_KEYS[i]: nutrients_json[i] for i in range(len(NUTRIENT_KEYS))}
        meal_plan = nd.get("meal_plan") if isinstance(nd.get("meal_plan"), dict) else {}
        if isinstance(meal_plan, dict):
            _clear_restaurant_lunch_items(meal_plan)
            _apply_rice_note_and_summary(meal_plan, indicators, settings)
            nd["meal_plan"] = meal_plan
        days_out.append(nd)

    refreshed["days"] = days_out
    return refreshed
