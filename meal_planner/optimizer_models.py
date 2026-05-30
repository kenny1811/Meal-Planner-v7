"""Shared data models for the optimizer pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meal_planner.nutrition_catalog import NutritionEntry


@dataclass
class _Candidate:
    meal: str
    item_idx: int
    alt_key: str
    entry: NutritionEntry
    min_g: float
    max_g: float
    is_rice_item: bool
    rank: int


@dataclass
class SolveArtifacts:
    meal_ingredients: dict[str, list[str]]
    meal_nutrients: dict[str, dict[str, float]]
    meal_items: dict[str, list[dict[str, object]]]
    status: str
    diagnostics: dict[str, Any]
    state: dict[str, Any] | None = None
