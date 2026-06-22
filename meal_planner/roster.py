"""更表：每月一行、日↔更碼、返工／非返工（規則.md §6–§7）。"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterator


_MONTH_HEAD_RE = re.compile(r"^(\d{4})年(\d{1,2})月")


@dataclass(frozen=True)
class RosterMonth:
    year: int
    month: int
    day_to_code: dict[int, str]


def parse_roster_line(cell_text: str) -> RosterMonth | None:
    """
    解析更表單格全文：開頭 YYYY年M月，其後為「日 更碼」。
    更碼可包含空格，會一路讀到下一個日期 token。
    """
    if cell_text is None:
        return None
    s = str(cell_text).strip()
    if not s:
        return None
    m = _MONTH_HEAD_RE.match(s)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    rest = s[m.end() :].strip()
    tokens = rest.split()
    day_to_code: dict[int, str] = {}
    i = 0
    while i < len(tokens):
        d_tok = tokens[i]
        if not d_tok.isdigit():
            break
        day = int(d_tok)
        if day < 1 or day > 31:
            break
        i += 1
        code_parts: list[str] = []
        while i < len(tokens) and not (tokens[i].isdigit() and 1 <= int(tokens[i]) <= 31):
            code_parts.append(tokens[i])
            i += 1
        if not code_parts:
            break
        day_to_code[day] = " ".join(code_parts)
    return RosterMonth(year=y, month=mo, day_to_code=day_to_code)


def roster_for_month(rows: Iterator[str | None]) -> dict[tuple[int, int], RosterMonth]:
    """掃描多格／多行，回傳 (年,月) → RosterMonth。"""
    out: dict[tuple[int, int], RosterMonth] = {}
    for raw in rows:
        rm = parse_roster_line(raw)
        if rm is not None:
            out[(rm.year, rm.month)] = rm
    return out


def is_work_day(code: str) -> bool:
    if code == "SB":
        return False
    for prefix in ("WL", "SH", "AL", "SL"):
        if code.startswith(prefix):
            return False
    return True


def code_for_date(rm: RosterMonth, d: date) -> str | None:
    if d.year != rm.year or d.month != rm.month:
        return None
    return rm.day_to_code.get(d.day)


def last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]
