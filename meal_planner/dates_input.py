"""日期輸入、界限日與拒絕規則（規則.md §3）。"""

from __future__ import annotations

import re
import calendar
from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo


class DateValidationError(ValueError):
    def __init__(self, message: str, rejected_dates: tuple[date, ...]):
        super().__init__(message)
        self.rejected_dates = rejected_dates


def validate_dates_within_allowed_months(
    dates: Iterable[date],
    *,
    timezone: str,
) -> None:
    z = ZoneInfo(timezone)
    today = datetime.now(z).date()
    
    allowed_months = {(today.year, today.month)}
    if today.month == 12:
        allowed_months.add((today.year + 1, 1))
    else:
        allowed_months.add((today.year, today.month + 1))
        
    bad = tuple(sorted({d for d in dates if (d.year, d.month) not in allowed_months}))
    if bad:
        raise DateValidationError(
            message=f"只限生成本月（{today.month}月）及下個月的餐單，以下日期已超出範圍並被拒絕。",
            rejected_dates=bad,
        )


_RANGE_SEG_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def _expand_segment(
    seg: str,
    year: int,
    month: int,
) -> list[date]:
    seg = seg.strip()
    if not seg:
        return []
    m = _RANGE_SEG_RE.match(seg)
    if not m:
        raise ValueError(f"無法解析日期範圍段：{seg!r}")
    start_d, end_d = int(m.group(1)), int(m.group(2))
    if start_d <= end_d:
        last = calendar.monthrange(year, month)[1]
        out: list[date] = []
        for d in range(start_d, end_d + 1):
            if d > last:
                raise ValueError(f"日期 {d} 超出 {year}-{month} 當月天數")
            out.append(date(year, month, d))
        return out
    # 跨月：由當月起日至月底，再下月 1 日至 end_d
    last_cur = calendar.monthrange(year, month)[1]
    out2: list[date] = []
    for d in range(start_d, last_cur + 1):
        out2.append(date(year, month, d))
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1
    last_next = calendar.monthrange(ny, nm)[1]
    for d in range(1, end_d + 1):
        if d > last_next:
            raise ValueError(f"日期 {d} 超出 {ny}-{nm} 當月天數")
        out2.append(date(ny, nm, d))
    return out2


def _parse_token(tok: str, year: int, month: int) -> list[date]:
    """單一 token：同月範圍 `15-17`、跨月範圍 `27-3`、或單日 `12`。"""
    tok = tok.strip()
    if not tok:
        return []
    if _RANGE_SEG_RE.match(tok):
        return _expand_segment(tok, year, month)
    if tok.isdigit():
        last = calendar.monthrange(year, month)[1]
        d = int(tok)
        if d < 1 or d > last:
            raise ValueError(f"日數 {d} 超出 {year}-{month}（1–{last}）")
        return [date(year, month, d)]
    raise ValueError(
        f"無法解析日期：{tok!r}。"
        f"單日用空格分隔（如 12 13 14），同月範圍用 15-17，多段範圍用逗號（如 12-15,27-3）。"
    )


def parse_date_expression(
    expr: str,
    *,
    year: int,
    month: int,
) -> list[date]:
    """
    - 多段以逗號分隔：「12-15,27-3」（每段係起日-止日，或單一數字日）
    - 無逗號而整句係單一段範圍：「12-15」或「27-3」
    - 空格分隔：「3 5 7」或「12 13 14 15-17」（每個 token 可為單日或範圍）
    """
    s = expr.strip()
    if not s:
        return []

    if "," in s:
        comma_segments = [segment.strip() for segment in s.split(",")]
        for segment in comma_segments:
            if re.search(r"\s", segment):
                raise ValueError("逗號分段內唔可含空格；請用 3,5,7-9 或 3 5 7-9。")
        tokens = [segment for segment in comma_segments if segment]
    else:
        tokens = s.split()
    
    out: list[date] = []
    current_y = year
    current_m = month
    last_d = 0
    
    for tok in tokens:
        if _RANGE_SEG_RE.match(tok):
            m = _RANGE_SEG_RE.match(tok)
            start_d = int(m.group(1))
            
            # 若起日細過前一個日字，代表跨去下個月
            if start_d < last_d:
                if current_m == 12:
                    current_y += 1
                    current_m = 1
                else:
                    current_m += 1
                    
            seg_dates = _expand_segment(tok, current_y, current_m)
            out.extend(seg_dates)
            
            if seg_dates:
                last_d = seg_dates[-1].day
                current_y = seg_dates[-1].year
                current_m = seg_dates[-1].month
                
        elif tok.isdigit():
            d = int(tok)
            # 若日數字細過前一個日字，代表跨去下個月
            if d < last_d:
                if current_m == 12:
                    current_y += 1
                    current_m = 1
                else:
                    current_m += 1
                    
            last_cur = calendar.monthrange(current_y, current_m)[1]
            if d < 1 or d > last_cur:
                raise ValueError(f"日數 {d} 超出 {current_y}-{current_m}（1–{last_cur}）")
                
            out.append(date(current_y, current_m, d))
            last_d = d
            
        else:
            raise ValueError(
                f"無法解析日期：{tok!r}。"
                f"單日用空格分隔（如 12 13 14），同月範圍用 15-17，多段範圍用逗號（如 12-15,27-3）。"
            )
            
    # 去重並保留順序
    return list(dict.fromkeys(out))
