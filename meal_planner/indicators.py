"""餐單v5 頂部指標列：由儲存格字串解析 Lo／Hi／脂肪比例（規則.md §16.1）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class IndicatorKind(str, Enum):
    RANGE = "range"  # Lo..Hi
    UPPER_ONLY = "upper_only"  # total <= Hi
    LOWER_ONLY = "lower_only"  # total >= Lo
    FAT_PCT = "fat_pct"  # 由 "< 27.5% kcal" 得比例，上限用 K 換算


@dataclass(frozen=True)
class ParsedIndicator:
    kind: IndicatorKind
    lo: float | None
    hi: float | None
    fat_pct: float | None
    raw: str


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")
_PCT_RE = re.compile(r"(\d*\.?\d+)\s*%")


def _first_float(s: str) -> float | None:
    m = _NUM_RE.search(s.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_indicator_cell(raw: Any) -> ParsedIndicator | None:
    """
    支援示例：
    - "1700-1800" → range
    - "< 40g" / "<40g" → upper_only Hi=40
    - "> 1200mg" → lower_only Lo=1200
    - "< 27.5% kcal" → fat_pct 0.275
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "-":
        return None

    s_compact = s.replace(" ", "")

    if "%" in s or "kcal" in s.lower():
        pm = _PCT_RE.search(s)
        if pm:
            pct = float(pm.group(1)) / 100.0
            return ParsedIndicator(
                kind=IndicatorKind.FAT_PCT,
                lo=None,
                hi=None,
                fat_pct=pct,
                raw=s,
            )

    if "-" in s_compact and not s_compact.startswith("<") and not s_compact.startswith(">"):
        parts = re.split(r"-", s_compact, maxsplit=1)
        if len(parts) == 2 and parts[0] and parts[1]:
            a = _first_float(parts[0])
            b = _first_float(parts[1])
            if a is not None and b is not None:
                lo, hi = (a, b) if a <= b else (b, a)
                return ParsedIndicator(
                    kind=IndicatorKind.RANGE,
                    lo=lo,
                    hi=hi,
                    fat_pct=None,
                    raw=s,
                )

    if s_compact.startswith("<"):
        hi = _first_float(s)
        if hi is not None:
            return ParsedIndicator(
                kind=IndicatorKind.UPPER_ONLY,
                lo=None,
                hi=hi,
                fat_pct=None,
                raw=s,
            )

    if s_compact.startswith(">"):
        lo = _first_float(s)
        if lo is not None:
            return ParsedIndicator(
                kind=IndicatorKind.LOWER_ONLY,
                lo=lo,
                hi=None,
                fat_pct=None,
                raw=s,
            )

    single = _first_float(s)
    if single is not None:
        return ParsedIndicator(
            kind=IndicatorKind.RANGE,
            lo=single,
            hi=single,
            fat_pct=None,
            raw=s,
        )
    return None


NUTRIENT_KEYS = (
    "kcal",
    "protein_g",
    "carb_g",
    "sugar_g",
    "cholesterol_mg",
    "sodium_mg",
    "calcium_mg",
    "fat_total_g",
    "fat_sat_g",
    "fat_trans_g",
)


@dataclass
class DayIndicatorProfile:
    """單日指標（返工或非返工列），與 NUTRIENT_KEYS 對齊。"""

    nutrients: list[ParsedIndicator | None]

    @staticmethod
    def empty() -> DayIndicatorProfile:
        return DayIndicatorProfile(nutrients=[None] * len(NUTRIENT_KEYS))

    @staticmethod
    def from_row_cells(values: list[object]) -> DayIndicatorProfile:
        parsed: list[ParsedIndicator | None] = []
        for i, v in enumerate(values):
            if i >= len(NUTRIENT_KEYS):
                break
            parsed.append(parse_indicator_cell(v))
        while len(parsed) < len(NUTRIENT_KEYS):
            parsed.append(None)
        return DayIndicatorProfile(nutrients=parsed)


def indicator_to_json(p: ParsedIndicator) -> dict:
    return {
        "kind": p.kind.value,
        "lo": p.lo,
        "hi": p.hi,
        "fat_pct": p.fat_pct,
        "raw": p.raw,
    }


def indicator_from_json(obj: Any) -> ParsedIndicator | None:
    if not isinstance(obj, dict):
        return None
    kind_raw = obj.get("kind")
    try:
        kind = IndicatorKind(str(kind_raw))
    except Exception:
        return None
    lo = obj.get("lo")
    hi = obj.get("hi")
    fat_pct = obj.get("fat_pct")
    raw = obj.get("raw")
    return ParsedIndicator(
        kind=kind,
        lo=float(lo) if lo is not None else None,
        hi=float(hi) if hi is not None else None,
        fat_pct=float(fat_pct) if fat_pct is not None else None,
        raw=str(raw or ""),
    )


def profile_from_json_map(nutrient_indicators: dict[str, Any]) -> DayIndicatorProfile:
    parsed: list[ParsedIndicator | None] = []
    for k in NUTRIENT_KEYS:
        parsed.append(indicator_from_json(nutrient_indicators.get(k)))
    return DayIndicatorProfile(nutrients=parsed)
