"""每週固定食材：按星期（日至六）分配「邊幾日出邊樣嘢」。

規則喺 `config.yaml` 嘅 `weekly_ingredient_rules`（見 `WeeklyIngredientRule`）。
呢度淨係決定**邊幾日**要／唔要某行食材，決定完交返畀 solver 自己揀份量同埋
落喺邊一餐——所以唔會硬撼營養目標，只係收窄咗個揀選空間。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from meal_planner.nutrition_catalog import NutritionEntry, candidate_entries_from_alternatives
from meal_planner.settings import WeeklyIngredientRule

# 一週用「嗰週嘅星期日」做 key——用戶當星期日係一週第一日，唔係 ISO 嘅星期一。
WeekKey = date


def week_start(d: date) -> WeekKey:
    """`d` 嗰個禮拜嘅星期日。`isoweekday()` 一=1…日=7，%7 之後日=0。"""
    return d - timedelta(days=d.isoweekday() % 7)


def week_dates(week: WeekKey) -> list[date]:
    """由星期日數起嘅七日。"""
    return [week + timedelta(days=i) for i in range(7)]


def resolve_rule_rows(
    rules: Sequence[WeeklyIngredientRule],
    entries: Sequence[NutritionEntry],
) -> list[tuple[WeeklyIngredientRule, int]]:
    """規則名 → 營養清單 row。先要求全名相同，唔中就試「唯一一個名包含」。

    對唔到（打錯名、行畀人刪咗）就靜靜略過嗰條規則——餐單照出，總好過成個
    生成 crash。
    """
    by_name = {str(e.name).strip().lower(): e for e in entries}
    out: list[tuple[WeeklyIngredientRule, int]] = []
    for rule in rules:
        key = str(rule.name).strip().lower()
        if not key:
            continue
        entry = by_name.get(key)
        if entry is None:
            hits = [e for e in entries if key in str(e.name).strip().lower()]
            entry = hits[0] if len(hits) == 1 else None
        if entry is not None:
            out.append((rule, int(entry.row_index)))
    return out


def meal_plan_rows_used(meal_plan: Mapping[str, Any] | None) -> set[int]:
    """餐單實際用咗（克數 > 0）嘅食材列。"""
    used: set[int] = set()
    for items in ((meal_plan or {}).get("meal_items") or {}).values():
        for it in items or []:
            if not isinstance(it, Mapping):
                continue
            row = it.get("row")
            try:
                grams = float(it.get("grams") or 0.0)
            except (TypeError, ValueError):
                grams = 0.0
            if isinstance(row, int) and grams > 0:
                used.add(int(row))
    return used


def day_payload_rows_used(payload: Mapping[str, Any] | None) -> set[int]:
    """已儲存嘅一日餐單（`plan_versions` 嗰種 shape）用咗邊幾行。"""
    if not isinstance(payload, Mapping):
        return set()
    inner = payload.get("meal_plan")
    return meal_plan_rows_used(inner if isinstance(inner, Mapping) else payload)


def slot_counts_for_rows(
    meal_plan: Mapping[str, Any] | None,
    entries: Sequence[NutritionEntry],
    rows: Iterable[int],
) -> dict[int, int]:
    """每行食材當日有幾多個 pattern 格揀得到佢。

    只數有嘢出嘅餐（餐廳午餐嗰日午餐係冇 solver 食材嘅，唔計）。格數愈多，
    solver 愈有得補返其他嘢（例如三文魚食咗個蛋白格，另一餐仲可以出沙甸魚
    補鈣），所以呢個係「邊日最頂得順」嘅主要指標。
    """
    wanted = {int(r) for r in rows}
    counts = {r: 0 for r in wanted}
    parts = (meal_plan or {}).get("meal_pattern_parts") or {}
    items_by_meal = (meal_plan or {}).get("meal_items") or {}
    for meal, slots in parts.items():
        if not items_by_meal.get(meal):
            continue
        for slot in slots or []:
            alts = slot.get("alternatives") if isinstance(slot, Mapping) else None
            alts_list = [str(x) for x in alts] if isinstance(alts, list) else []
            if not alts_list:
                continue
            for e in candidate_entries_from_alternatives(list(entries), alts_list):
                row = int(e.row_index)
                if row in counts:
                    counts[row] += 1
    return counts


@dataclass
class DayInfo:
    """排序一日「夠唔夠位頂多樣嘢」所需嘅資料，全部由第一輪求解結果嚟。"""

    day: date
    score: tuple[float, float, float]
    slot_counts: dict[int, int] = field(default_factory=dict)
    rows_used: set[int] = field(default_factory=set)


def group_by_week(days: Sequence[DayInfo]) -> dict[WeekKey, list[DayInfo]]:
    out: dict[WeekKey, list[DayInfo]] = {}
    for info in days:
        out.setdefault(week_start(info.day), []).append(info)
    return out


def quota_for_week(
    rule: WeeklyIngredientRule,
    week: WeekKey,
    row: int,
    outside_counts: Mapping[tuple[WeekKey, int], int] | None = None,
) -> int:
    """呢個禮拜仲要派幾多次——扣返同週但今次冇重生成嗰啲日子已經用咗嘅。"""
    used_outside = int((outside_counts or {}).get((week, row), 0))
    return max(0, int(rule.per_week) - used_outside)


def candidates_for_row(
    week_days: Sequence[DayInfo],
    row: int,
) -> tuple[list[DayInfo], list[DayInfo]]:
    """回 `(本身已經有, 可以加)`，兩邊都排好序（好揀嘅喺前）。

    排序：可用格數多者先——格數多即係 solver 仲有第二個格補返被頂走嘅營養
    （例如三文魚佔咗晚餐蛋白格，午餐仲可以出沙甸魚補鈣）；同分先至比第一輪
    嘅 `_summary_score`（紅旗 > 超標量 > 總偏離，愈細愈鬆動），最後用日期
    定死次序，令同一批輸入永遠派出同一個答案。
    """

    def rank(info: DayInfo) -> tuple[Any, ...]:
        return (-info.slot_counts.get(row, 0), info.score, info.day.toordinal())

    eligible = [d for d in week_days if d.slot_counts.get(row, 0) > 0]
    natural = sorted((d for d in eligible if row in d.rows_used), key=rank)
    rest = sorted((d for d in eligible if row not in d.rows_used), key=rank)
    return natural, rest


def weekday_days(week_days: Sequence[DayInfo], weekdays: Sequence[int]) -> list[DayInfo]:
    wanted = {int(x) for x in weekdays}
    return [d for d in week_days if d.day.isoweekday() in wanted]


def needs_resolve(
    rows_used: set[int],
    required: set[int] | None,
    excluded: set[int] | None,
) -> bool:
    """第一輪個結果本身已經合規就唔使再解一次。

    要重解淨係兩種情況：要嘅嘢冇喺度，或者唔准嘅嘢喺度。剩低嗰啲日子直接留
    返第一輪嘅答案，慳返成半生成時間。
    """
    if (required or set()) - rows_used:
        return True
    return bool((excluded or set()) & rows_used)
