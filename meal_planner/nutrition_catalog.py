"""營養清單查找：按 §11.2 規則由 Pattern item 對應食材列。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any



@dataclass(frozen=True)
class NutritionEntry:
    row_index: int
    paused: bool
    category: str
    name: str
    nutrients: dict[str, float]
    min_g: float | None
    max_g: float | None
    daymax_g: float | None


def _match_entries_for_token(entries: list[NutritionEntry], token: str) -> list[NutritionEntry]:
    t = token.strip().lower()
    if not t:
        return []

    exact_cat = [e for e in entries if e.category.lower() == t and not e.paused]
    if exact_cat:
        return exact_cat

    by_name = [e for e in entries if t in e.name.lower() and not e.paused]
    if by_name:
        return by_name
    return []


def candidate_entries_from_alternatives(
    entries: list[NutritionEntry],
    alternatives: list[str],
) -> list[NutritionEntry]:
    """
    item 內 `/` 候選：按 alternatives 次序串接候選清單（去重，保留原順序）。
    """
    out: list[NutritionEntry] = []
    seen_rows: set[int] = set()
    for token in alternatives:
        matches = _match_entries_for_token(entries, token)
        for e in matches:
            if e.row_index in seen_rows:
                continue
            out.append(e)
            seen_rows.add(e.row_index)
    return out

