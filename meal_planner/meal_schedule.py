"""飯時、餐廳選擇：更碼匹配（含 wildcard）與每日餐單草稿欄位。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any


from meal_planner.indicators import DayIndicatorProfile, NUTRIENT_HEADERS, NUTRIENT_KEYS
from meal_planner.nutrition_catalog import candidate_entries_from_alternatives
from meal_planner.nutrition_db import load_catalog_entries
from meal_planner.optimizer import solve_day_meal_plan
from meal_planner.patterns import parse_meal_patterns
from meal_planner.settings import AppSettings
from meal_planner.timeparse import cell_text


def roster_matches_rule(rule_cell: str | None, roster_code: str) -> bool:
    if not rule_cell or not roster_code:
        return False
    rule = str(rule_cell).strip()
    code = roster_code.strip()
    if not rule:
        return False
    if rule == "其他":
        return False
    rule_cmp = rule.casefold()
    code_cmp = code.casefold()
    if rule_cmp.endswith("*"):
        return code_cmp.startswith(rule_cmp[:-1])
    return code_cmp == rule_cmp


@dataclass(frozen=True)
class MealTimeRule:
    row_index: int
    code_pattern: str
    breakfast: str | None
    lunch: str | None
    snack: str | None
    dinner: str | None


@dataclass(frozen=True)
class MealPlanningCache:
    meal_time_rules: list[MealTimeRule]
    meal_patterns: dict[str, str | None]
    restaurant_rows: list[dict[str, Any]]
    nutrition_entries: list[Any]
    schedule_rows: list[Any]
    overtime_overrides: dict[date, tuple[time | None, time | None]]


def load_meal_time_rules_from_rows(raw_rows: list[list[Any]]) -> list[MealTimeRule]:
    if not raw_rows:
        return []
    headers = [str(v).strip() if v is not None else "" for v in raw_rows[0]]
    h = {name: idx for idx, name in enumerate(headers) if name}
    c_code = h.get("更碼")
    if c_code is None:
        return []
    cols = {k: h.get(k) for k in ("早餐", "午餐", "小食", "晚餐")}
    rules: list[MealTimeRule] = []
    for row_index, row in enumerate(raw_rows[1:], start=2):
        code = row[c_code] if c_code < len(row) else None
        if code is None or str(code).strip() == "":
            continue

        def gv(name: str) -> str | None:
            idx = cols.get(name)
            return cell_text(row[idx]) if idx is not None and idx < len(row) else None

        rules.append(
            MealTimeRule(
                row_index=row_index,
                code_pattern=str(code).strip(),
                breakfast=gv("早餐"),
                lunch=gv("午餐"),
                snack=gv("小食"),
                dinner=gv("晚餐"),
            )
        )
    return rules


def load_meal_patterns_table_from_rows(raw_rows: list[list[Any]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {m: None for m in MEAL_LABELS}
    if not raw_rows:
        return out
    headers = [str(v).strip() if v is not None else "" for v in raw_rows[0]]
    h = {name: idx for idx, name in enumerate(headers) if name}
    c_meal = h.get("餐名")
    c_pat = h.get("Pattern")
    if c_meal is None or c_pat is None:
        return out
    for row in raw_rows[1:]:
        meal = cell_text(row[c_meal]) if c_meal < len(row) else None
        pat = cell_text(row[c_pat]) if c_pat < len(row) else None
        if meal not in out or not pat:
            continue
        if out[meal] is None:
            out[meal] = pat
    return out


def first_matching_meal_rule(rules: list[MealTimeRule], roster_code: str) -> MealTimeRule | None:
    """§10.1：由上而下，更碼第一個命中（不含「其他」列，該列單獨兜底）。"""
    for rule in rules:
        if roster_matches_rule(rule.code_pattern, roster_code):
            return rule
    for rule in rules:
        if rule.code_pattern == "其他":
            return rule
    return None


MEAL_LABELS = ("早餐", "午餐", "小食", "晚餐")
MEAL_ROTATION_OFFSET = {"早餐": 0, "午餐": 1, "小食": 2, "晚餐": 3}


def load_restaurant_rows_from_rows(raw_rows: list[list[Any]]) -> list[dict[str, Any]]:
    if not raw_rows:
        return []
    headers = [str(v).strip() if v is not None else "" for v in raw_rows[0]]
    h = {name: idx for idx, name in enumerate(headers) if name}
    if "更碼關鍵字" not in h:
        return []
    cols = {name: h.get(name) for name in ("舖頭 (Store)", "營業時間", "餐廳選擇", "地址")}
    nutrient_cols = {k: h.get(NUTRIENT_HEADERS[k]) for k in NUTRIENT_KEYS}
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(raw_rows[1:], start=2):
        kw_idx = h["更碼關鍵字"]
        kw = row[kw_idx] if kw_idx < len(row) else None
        if kw is None or str(kw).strip() == "":
            continue

        def gv(name: str) -> Any:
            idx = cols.get(name)
            return row[idx] if idx is not None and idx < len(row) else None

        def nv(key: str) -> float:
            idx = nutrient_cols.get(key)
            if idx is None or idx >= len(row):
                return 0.0
            try:
                return float(row[idx] or 0.0)
            except (TypeError, ValueError):
                return 0.0

        rows.append(
            {
                "row": row_index,
                "keyword": str(kw).strip(),
                "store": gv("舖頭 (Store)"),
                "hours": gv("營業時間"),
                "choice": gv("餐廳選擇"),
                "address": gv("地址"),
                "nutrients": {k: nv(k) for k in NUTRIENT_KEYS},
            }
        )
    return rows


def build_meal_planning_cache(settings: AppSettings) -> MealPlanningCache:
    from meal_planner.reference_db import load_planning_references

    rules, patterns, restaurant_rows, schedule_rows = load_planning_references(settings)

    nutrition_entries = load_catalog_entries(settings)

    overtime_overrides: dict[date, tuple[time | None, time | None]] = {}
    try:
        from meal_planner.maintenance_db import load_sheet_rows
        from meal_planner.schedule_grid import load_overtime_overrides_from_rows

        overtime_sheet = load_sheet_rows("overtime", settings)
        overtime_overrides = load_overtime_overrides_from_rows(overtime_sheet.get("rows", []))
    except Exception:
        pass

    return MealPlanningCache(
        meal_time_rules=rules,
        meal_patterns=patterns,
        restaurant_rows=restaurant_rows,
        nutrition_entries=nutrition_entries,
        schedule_rows=schedule_rows,
        overtime_overrides=overtime_overrides,
    )


def first_matching_restaurant(rest_rows: list[dict[str, Any]], roster_code: str) -> dict[str, Any] | None:
    for row in rest_rows:
        if roster_matches_rule(row["keyword"], roster_code):
            return row
    return None


def choose_ingredients_for_meals(
    settings: AppSettings,
    meal_pattern_parts: dict[str, list[dict[str, object]]],
    day: date | None = None,
    indicators: DayIndicatorProfile | None = None,
    visible_meals: set[str] | None = None,
    fixed_nutrients: dict[str, float] | None = None,
    fixed_meals: set[str] | None = None,
    reroll_nonce: int = 0,
    nutrition_entries: list[Any] | None = None,
    bound_overrides: dict[int, dict[str, float]] | None = None,
    forced_rice_row: int | None = None,
    forced_item_rows: dict[tuple[str, int], int] | None = None,
) -> tuple[
    dict[str, list[str]],
    dict[str, dict[str, float]],
    dict[str, list[dict[str, object]]],
    dict[str, Any],
]:
    """
    依 §11.2：每個 item 先類別 exact，再名稱 contains；左右候選取第一個可用。
    回傳每餐對應食材名稱列表（按 pattern item 次序）。
    """
    def default_grams_for_entry(entry: Any) -> float:
        if entry.min_g is not None:
            return float(round(float(entry.min_g)))
        return 0.0

    if nutrition_entries is None:
        entries = load_catalog_entries(settings)
    else:
        entries = nutrition_entries
    visible_set = set(visible_meals or meal_pattern_parts.keys())
    fixed_meal_set = set(fixed_meals or set())
    rice_token = settings.rice.rice_category_exact.strip().lower()
    day_offset = (int(day.day) if isinstance(day, date) else 0) + int(reroll_nonce or 0)

    candidates_by_item: dict[tuple[str, int], list[Any]] = {}
    for meal, items in meal_pattern_parts.items():
        if meal not in visible_set:
            continue
        for i, item in enumerate(items):
            alts = item.get("alternatives", [])
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            candidates_by_item[(meal, i)] = candidate_entries_from_alternatives(entries, alts_list)

    # 指定食材：直接收窄嗰格嘅候選。唔用 solver 個 forced_item_rows 參數，因為
    # auto-retry／replacement search／relaxation 嗰幾條遞歸路唔會帶住佢——帶頭嗰次
    # 指定得中，一有違規就會被「冇指定」嘅重試方案蓋過。
    for (f_meal, f_idx), f_row in (forced_item_rows or {}).items():
        cands = candidates_by_item.get((f_meal, int(f_idx)))
        if not cands:
            continue
        picked = [e for e in cands if int(e.row_index) == int(f_row)]
        if picked:
            candidates_by_item[(f_meal, int(f_idx))] = picked

    if forced_rice_row is not None:
        # 一日一米：鎖咗嘅餐已經食咗某款米，重解餐次嘅米類候選只准同款
        # （除非嗰款米本身已暫停／唔喺候選，先容許轉款）。
        for meal, items in meal_pattern_parts.items():
            if meal not in visible_set:
                continue
            for i, item in enumerate(items):
                alts = item.get("alternatives", [])
                alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
                if not any((a or "").strip().lower() == rice_token for a in alts_list):
                    continue
                cands = candidates_by_item.get((meal, i), [])
                forced = [e for e in cands if int(e.row_index) == int(forced_rice_row)]
                if forced:
                    candidates_by_item[(meal, i)] = forced

    fixed_names: dict[str, list[str]] = {meal: [] for meal in meal_pattern_parts.keys()}
    fixed_items: dict[str, list[dict[str, object]]] = {meal: [] for meal in meal_pattern_parts.keys()}
    fixed_meal_nutrients: dict[str, dict[str, float]] = {
        meal: {k: 0.0 for k in NUTRIENT_KEYS}
        for meal in meal_pattern_parts.keys()
    }
    extra_fixed_nutrients = {k: float((fixed_nutrients or {}).get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS}
    for meal in fixed_meal_set:
        if meal not in visible_set:
            continue
        for i, item in enumerate(meal_pattern_parts.get(meal, [])):
            candidates = candidates_by_item.get((meal, i), [])
            entry = None
            if candidates:
                meal_offset = MEAL_ROTATION_OFFSET.get(meal, 0)
                entry = candidates[(day_offset + meal_offset + i) % len(candidates)]
            if entry is None:
                raw = str(item.get("raw", "")).strip()
                if raw:
                    fixed_names[meal].append(raw)
                    fixed_items[meal].append({"name": raw, "grams": None, "row": None})
                continue
            grams = default_grams_for_entry(entry)
            fixed_names[meal].append(f"{entry.name}({grams:.0f}g)")
            fixed_items[meal].append({"name": entry.name, "grams": grams, "row": entry.row_index})
            ratio = grams / 100.0
            for k in NUTRIENT_KEYS:
                v = float(entry.nutrients.get(k, 0.0)) * ratio
                fixed_meal_nutrients[meal][k] += v
                extra_fixed_nutrients[k] += v

    solver_visible_set = visible_set - fixed_meal_set

    if indicators is not None:
        solved = solve_day_meal_plan(
            settings=settings,
            indicators=indicators,
            meal_pattern_parts=meal_pattern_parts,
            candidates_by_item=candidates_by_item,
            visible_meals=solver_visible_set,
            rice_token=rice_token,
            day_offset=day_offset,
            reroll_nonce=int(reroll_nonce or 0),
            fixed_nutrients=extra_fixed_nutrients,
            bound_overrides=bound_overrides,
        )
        if solved is not None:
            for meal in fixed_meal_set:
                if meal in visible_set:
                    solved.meal_ingredients[meal] = fixed_names.get(meal, [])
                    solved.meal_nutrients[meal] = fixed_meal_nutrients.get(meal, {k: 0.0 for k in NUTRIENT_KEYS})
                    solved.meal_items[meal] = fixed_items.get(meal, [])
            return (
                solved.meal_ingredients,
                solved.meal_nutrients,
                solved.meal_items,
                {"mode": "milp", "status": solved.status, **solved.diagnostics},
            )

    out_names: dict[str, list[str]] = {}
    out_nutrients: dict[str, dict[str, float]] = {}
    out_items: dict[str, list[dict[str, object]]] = {}
    pick_cursor: dict[str, int] = {}
    rice_locked_entry = None
    for meal, items in meal_pattern_parts.items():
        if meal in fixed_meal_set and meal in visible_set:
            out_names[meal] = fixed_names.get(meal, [])
            out_nutrients[meal] = fixed_meal_nutrients.get(meal, {k: 0.0 for k in NUTRIENT_KEYS})
            out_items[meal] = fixed_items.get(meal, [])
            continue
        if meal not in visible_set:
            out_names[meal] = []
            out_nutrients[meal] = {k: 0.0 for k in NUTRIENT_KEYS}
            out_items[meal] = []
            continue
        chosen: list[str] = []
        nutrient_sum = {k: 0.0 for k in NUTRIENT_KEYS}
        chosen_items: list[dict[str, object]] = []
        for i, item in enumerate(items):
            alts = item.get("alternatives", [])
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            candidates = candidates_by_item.get((meal, i), [])
            entry = None
            is_rice_item = any((a or "").strip().lower() == rice_token for a in alts_list)
            if is_rice_item:
                if rice_locked_entry is None and candidates:
                    key = "|".join(alts_list)
                    base = pick_cursor.get(key, 0)
                    idx = (base + day_offset) % len(candidates)
                    rice_locked_entry = candidates[idx]
                    pick_cursor[key] = base + 1
                entry = rice_locked_entry
            elif candidates:
                # 輪替按「餐次 + alternatives」分開，避免午餐序列被晚餐推進。
                key = f"{meal}|{'|'.join(alts_list)}"
                base = pick_cursor.get(key, 0)
                meal_offset = MEAL_ROTATION_OFFSET.get(meal, 0)
                idx = (base + day_offset + meal_offset) % len(candidates)
                entry = candidates[idx]
                pick_cursor[key] = base + 1
            if entry is not None:
                # Min(g) 有值就照用（包括 0）；Min 空白時用 default_g，但不可超過 Max/DayMax。
                grams = default_grams_for_entry(entry)
                chosen.append(f"{entry.name}({grams:.0f}g)")
                chosen_items.append({"name": entry.name, "grams": grams, "row": entry.row_index})
                ratio = grams / 100.0
                for k in NUTRIENT_KEYS:
                    nutrient_sum[k] += float(entry.nutrients.get(k, 0.0)) * ratio
            else:
                raw = str(item.get("raw", "")).strip()
                if raw:
                    chosen.append(raw)
                    chosen_items.append({"name": raw, "grams": None, "row": None})
        out_names[meal] = chosen
        out_nutrients[meal] = nutrient_sum
        out_items[meal] = chosen_items
    return out_names, out_nutrients, out_items, {"mode": "fallback_rotation"}


def build_rice_note(
    meal_items: dict[str, list[dict[str, object]]],
    settings: AppSettings,
    visible_meals: set[str] | None = None,
) -> str:
    """
    依 §13：同日只一款米。根據已選米類熟重總和，換算生重與水重。
    """
    rice_items: list[tuple[str, float]] = []
    for meal, items in meal_items.items():
        if visible_meals is not None and meal not in visible_meals:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            name = str(it.get("name", "")).strip()
            grams = it.get("grams")
            if not name or not isinstance(grams, (int, float)):
                continue
            rice_markers = tuple(x for x in settings.rice.note_name_contains if x)
            if any(marker in name for marker in rice_markers):
                rice_items.append((name, float(grams)))

    if not rice_items:
        return "（米類備註：配餐後填）"

    rice_name = rice_items[0][0]
    cooked_g = sum(g for _, g in rice_items)
    ratio = settings.rice.ratio_for(rice_name)
    if ratio is None:
        return f"（{rice_name} 未設定生熟換算率：去 Config → Rice conversion 加行）"
    raw_g = cooked_g / ratio
    water_g = raw_g * settings.rice.water_multiplier
    return f"{rice_name}({cooked_g:.0f}g)=生重{raw_g:.0f}g\n水={water_g:.0f}g"


def build_day_meal_plan(
    settings: AppSettings,
    roster_code: str | None,
    is_work_day: bool | None,
    day: date | None = None,
    indicators: DayIndicatorProfile | None = None,
    reroll_nonce: int = 0,
    cache: MealPlanningCache | None = None,
    locked_meals: dict[str, dict[str, Any]] | None = None,
    bound_overrides: dict[int, dict[str, float]] | None = None,
    meal_time_overrides: dict[str, str] | None = None,
    # 指定食材：{(餐, item 位置): 營養清單 row}。淨係喺嗰格原本嘅候選入面篩，
    # 所以只可以換成同格嘅嘢（米格換唔到魚）。
    forced_item_rows: dict[tuple[str, int], int] | None = None,
) -> dict[str, Any]:
    """組合飯時主規則、各餐 Pattern、返工日午餐餐廳（第一命中）；可選 `day` 以解析行位表實際用餐時間。"""
    if not roster_code:
        return {
            "primary_rule": None,
            "meal_patterns": {},
            "restaurant_lunch": None,
            "meal_times_resolved": {},
            "note": "無更表更碼，無法對應飯時。",
        }

    if cache is None:
        raise ValueError("build_day_meal_plan requires a MealPlanningCache (Worksheet fallback removed)")
    rules = cache.meal_time_rules
    primary = first_matching_meal_rule(rules, roster_code)
    pattern_table = cache.meal_patterns

    rest = None
    if (not settings.meal_business_rules.restaurant_lunch_workday_only) or is_work_day is True:
        r_rows = cache.restaurant_rows
        hit = first_matching_restaurant(r_rows, roster_code)
        if hit:
            rest = {
                "keyword": hit["keyword"],
                "store": hit["store"],
                "hours": hit["hours"],
                "choice": hit["choice"],
                "address": hit["address"],
                "nutrients": hit.get("nutrients", {}),
            }

    primary_dict = None
    if primary:
        primary_dict = {
            "code_pattern": primary.code_pattern,
            "早餐": primary.breakfast,
            "午餐": primary.lunch,
            "小食": primary.snack,
            "晚餐": primary.dinner,
            "餐名": None,
            "pattern": None,
        }

    # 打風加開嘅一餐（例如飯鐘食唔到，改為喺長 break 帶小食）：直接寫死鐘點入主規則，
    # 之後照走 resolve_meal_times_display 同一條路，唔會另開一套時間邏輯。
    if primary_dict and meal_time_overrides:
        for meal, hhmm in meal_time_overrides.items():
            if meal in MEAL_LABELS and str(hhmm or "").strip():
                primary_dict[meal] = str(hhmm).strip()

    meal_times_resolved: dict[str, Any] = {}
    if day is not None and primary_dict:
        from meal_planner.schedule_grid import resolve_meal_times_display

        meal_times_resolved = resolve_meal_times_display(
            settings,
            day=day,
            roster_code=roster_code,
            primary_rule=primary_dict,
            is_work_day=is_work_day,
            restaurant=rest,
            schedule_rows=cache.schedule_rows,
            overtime_overrides=cache.overtime_overrides,
        )
    if meal_times_resolved:
        visible_meals = {
            meal
            for meal in MEAL_LABELS
            if (
                meal_times_resolved.get(meal) is not None
                and str(meal_times_resolved.get(meal)).strip() != ""
            )
        }
    else:
        # 無 day/無 resolved 時，退回 A:E 命中行本身嘅時間欄判斷可見餐次
        visible_meals = set()
        if primary is not None:
            if primary.breakfast:
                visible_meals.add("早餐")
            if primary.lunch:
                visible_meals.add("午餐")
            if primary.snack:
                visible_meals.add("小食")
            if primary.dinner:
                visible_meals.add("晚餐")

    # 規則：先由 A:E 決定有邊幾餐；再只為該幾餐從 G:H 拿 Pattern。
    # 餐廳午餐是固定營養值，求解時要當成已食用，其他餐次再遷就它。
    fixed_nutrients = None
    solver_visible_meals = set(visible_meals)
    if "午餐" in visible_meals and rest and isinstance(rest.get("nutrients"), dict):
        fixed_nutrients = {
            k: float(rest["nutrients"].get(k, 0.0) or 0.0)
            for k in NUTRIENT_KEYS
        }
        solver_visible_meals.discard("午餐")

    # 已食餐（partial-day re-solve）：當成固定營養，剔出求解範圍，內容原封不動。
    locked = {m: v for m, v in (locked_meals or {}).items() if m in visible_meals and isinstance(v, dict)}
    # 一日一米：鎖咗嘅餐如果已包含米類，重解餐次要焗住用同一款米。
    forced_rice_row: int | None = None
    if locked:
        rice_markers = tuple(x for x in settings.rice.note_name_contains if x)
        for data in locked.values():
            items_in = data.get("items")
            for it in items_in if isinstance(items_in, list) else []:
                if not isinstance(it, dict):
                    continue
                try:
                    row_i = int(it.get("row")) if it.get("row") is not None else None
                except (TypeError, ValueError):
                    row_i = None
                if row_i is not None and any(m in str(it.get("name", "")) for m in rice_markers):
                    forced_rice_row = row_i
                    break
            if forced_rice_row is not None:
                break
    for meal, data in locked.items():
        if meal not in solver_visible_meals:
            # 例如餐廳午餐已經以固定營養處理，locked 數值同佢一致，唔好重複計。
            continue
        solver_visible_meals.discard(meal)
        if fixed_nutrients is None:
            fixed_nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
        nut = data.get("nutrients") if isinstance(data.get("nutrients"), dict) else {}
        for k in NUTRIENT_KEYS:
            fixed_nutrients[k] += float(nut.get(k, 0.0) or 0.0)
    by_meal = {m: (pattern_table.get(m) if m in solver_visible_meals else None) for m in MEAL_LABELS}
    fixed_meals = {
        meal
        for meal in settings.meal_business_rules.fixed_meals
        if meal in solver_visible_meals and pattern_table.get(meal)
    }

    meal_pattern_parts = parse_meal_patterns(by_meal, settings.pattern)
    meal_ingredients, meal_nutrients, meal_items, optimization_meta = choose_ingredients_for_meals(
        settings,
        meal_pattern_parts,
        day=day,
        indicators=indicators,
        visible_meals=solver_visible_meals,
        fixed_nutrients=fixed_nutrients,
        fixed_meals=fixed_meals,
        reroll_nonce=reroll_nonce,
        nutrition_entries=cache.nutrition_entries if cache is not None else None,
        bound_overrides=bound_overrides,
        forced_rice_row=forced_rice_row,
        forced_item_rows=forced_item_rows,
    )
    if rest and isinstance(rest.get("nutrients"), dict):
        meal_nutrients["午餐"] = {
            k: float(rest["nutrients"].get(k, 0.0)) for k in NUTRIENT_KEYS
        }
        # 餐廳午餐由餐廳固定營養值提供；唔應再用求解器午餐食材去計米類熟重。
        meal_items["午餐"] = []
        choice = str(rest.get("choice") or "").strip()
        store = str(rest.get("store") or "").strip()
        if choice or store:
            label = f'Lunch — "{choice}"'
            if store:
                label += f" ({store})"
            meal_ingredients["午餐"] = [label]
        else:
            meal_ingredients["午餐"] = ["Lunch — restaurant meal"]

    # locked 餐內容以傳入為準（放喺餐廳覆寫之後，locked 贏）。
    for meal, data in locked.items():
        items_in = data.get("items")
        ings_in = data.get("ingredients")
        nut_in = data.get("nutrients") if isinstance(data.get("nutrients"), dict) else {}
        meal_items[meal] = list(items_in) if isinstance(items_in, list) else []
        meal_ingredients[meal] = [str(x) for x in ings_in] if isinstance(ings_in, list) else []
        meal_nutrients[meal] = {k: float(nut_in.get(k, 0.0) or 0.0) for k in NUTRIENT_KEYS}

    return {
        "primary_rule": primary_dict,
        "meal_patterns": by_meal,
        "meal_pattern_parts": meal_pattern_parts,
        "meal_ingredients": meal_ingredients,
        "meal_items": meal_items,
        "meal_nutrients": meal_nutrients,
        "rice_note": build_rice_note(meal_items, settings, visible_meals=visible_meals),
        "restaurant_lunch": rest,
        "meal_times_resolved": meal_times_resolved,
        "optimization": optimization_meta,
        "peninsula_stack_applied": False,
        # 開工遲過行位表食位嗰啲餐次唔會出，要喺呢度講明點解（唔好靜靜哋消失）。
        "note": "；".join(
            f"{meal}：{why}" for meal, why in (meal_times_resolved.get("_skipped") or {}).items()
        ) or None,
    }
