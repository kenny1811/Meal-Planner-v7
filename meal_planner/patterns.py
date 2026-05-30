"""Pattern 拆解：`+` item、`/` 候選（規則.md §11.1）。"""

from __future__ import annotations

from dataclasses import dataclass

from meal_planner.settings import PatternConfig


@dataclass(frozen=True)
class PatternItem:
    raw: str
    alternatives: tuple[str, ...]


def _norm_token(s: str) -> str:
    return s.strip()


def split_pattern_items(pattern: str, cfg: PatternConfig) -> list[str]:
    if not pattern:
        return []
    parts = [_norm_token(x) for x in pattern.split(cfg.item_separator)]
    return [x for x in parts if x]


def split_item_alternatives(item: str, cfg: PatternConfig) -> tuple[str, ...]:
    if not item:
        return ()
    alts = [_norm_token(x) for x in item.split(cfg.item_alt_separator)]
    alts = [x for x in alts if x]
    return tuple(alts)


def parse_pattern(pattern: str | None, cfg: PatternConfig) -> list[PatternItem]:
    if not pattern:
        return []
    out: list[PatternItem] = []
    for item in split_pattern_items(pattern, cfg):
        out.append(PatternItem(raw=item, alternatives=split_item_alternatives(item, cfg)))
    return out


def parse_meal_patterns(
    meal_patterns: dict[str, str | None],
    cfg: PatternConfig,
) -> dict[str, list[dict[str, object]]]:
    """
    回傳：
    {
      "早餐": [{"raw":"種子/堅果", "alternatives":["種子","堅果"]}, ...],
      ...
    }
    """
    out: dict[str, list[dict[str, object]]] = {}
    for meal, pattern in meal_patterns.items():
        parsed = parse_pattern(pattern, cfg)
        out[meal] = [
            {
                "raw": x.raw,
                "alternatives": list(x.alternatives),
            }
            for x in parsed
        ]
    return out

