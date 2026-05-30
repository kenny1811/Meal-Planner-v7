"""Auto-retry strategy generation for hard-infeasible optimizer runs."""

from __future__ import annotations

from typing import Any


def build_auto_retry_plans(
    hard_violations: list[dict[str, Any]],
    reroll_nonce: int,
) -> list[tuple[dict[str, float], int]]:
    boost_base: dict[str, float] = {}
    for v in hard_violations:
        k = str(v.get("nutrient", "")).strip()
        if k:
            boost_base[k] = 8.0

    if not boost_base:
        return []

    return [
        (dict(boost_base), reroll_nonce + 1),
        ({**boost_base, "fat_total_g": 14.0}, reroll_nonce + 2),
        ({**boost_base, "calcium_mg": 14.0}, reroll_nonce + 3),
        ({**boost_base, "kcal": 14.0}, reroll_nonce + 4),
        ({**boost_base, "kcal": 12.0, "calcium_mg": 12.0, "fat_total_g": 14.0}, reroll_nonce + 5),
        ({**boost_base, "protein_g": 4.0}, reroll_nonce + 6),
    ]
