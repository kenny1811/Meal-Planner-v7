"""更碼定義：邊啲更碼唔使返工，同埋一個更碼屬邊個品牌。

更碼定義表（Config → 系統參數）**淨係列非返工嘅 pattern**（`WL*` 週假、`SB` Stand by、
`TP` 颱風假…）加一行 `其他 → 返工日` 做包尾。列咗＝唔使返工，夾唔到＝返工。
以前 `roster.is_work_day` 將呢套規則寫死咗，而家改表就得，唔使改 Python。

品牌唔入表——由更碼推得出，一條規則講晒：`V*` 或 `Lecole*` ＝ VCA，其餘 ＝ 其他 form。
打風落波之後幾耐開工都係跟品牌——兩個牌而家都係等一個鐘（60 分鐘）；
分開兩個常數係因為呢個係公司政策，隨時可以再各行各路。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CATCH_ALL_PATTERN = "其他"

VCA_PREFIXES = ("v", "lecole")
VCA_TYPHOON_OFFSET_MIN = 60    # 落波後一個鐘開工（以前係即開，2026-07 改咗）
OTHER_TYPHOON_OFFSET_MIN = 60  # 落波後一個鐘開工


@dataclass(frozen=True)
class RosterCodeDef:
    pattern: str
    label: str


def defs_from_rows(rows: list[dict[str, Any]] | None) -> list[RosterCodeDef]:
    return [
        RosterCodeDef(pattern=str(row.get("pattern") or "").strip(), label=str(row.get("label") or "").strip())
        for row in (rows or [])
        if isinstance(row, dict) and str(row.get("pattern") or "").strip()
    ]


def match_roster_code(defs: list[RosterCodeDef], roster_code: str) -> RosterCodeDef | None:
    """揀啱嗰條定義：確切更碼 → 最長 wildcard。夾唔到就 None（`其他` 唔當夾到）。"""
    code = str(roster_code or "").strip()
    if not code:
        return None
    lowered = code.casefold()
    for item in defs:
        if item.pattern != CATCH_ALL_PATTERN and item.pattern.casefold() == lowered:
            return item
    best: RosterCodeDef | None = None
    for item in defs:
        pattern = item.pattern.casefold()
        if pattern.endswith("*") and lowered.startswith(pattern[:-1]):
            if best is None or len(pattern) > len(best.pattern):
                best = item
    return best


def is_work_day(defs: list[RosterCodeDef], roster_code: str) -> bool:
    """喺定義表列咗＝唔使返工；夾唔到（即係跟 `其他` 嗰行）＝返工。"""
    return match_roster_code(defs, roster_code) is None


def form_key_for_code(roster_code: str) -> str:
    """更碼 → 打卡 form：`V*` / `Lecole*` 行 VCA form，其餘行另一條。"""
    lowered = str(roster_code or "").strip().casefold()
    return "vca" if any(lowered.startswith(prefix) for prefix in VCA_PREFIXES) else "other"


def typhoon_offset_minutes(roster_code: str) -> int:
    """打風落 8 號波之後幾多分鐘開工（跟品牌）。"""
    return VCA_TYPHOON_OFFSET_MIN if form_key_for_code(roster_code) == "vca" else OTHER_TYPHOON_OFFSET_MIN
