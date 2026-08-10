"""Typhoon panel：打風落波嘅 what-if 模擬 —— 一次過睇齊四邊點反應。

輸入：日期 + 落波時間 + 確實 + 更碼。實際開工 ＝ max(落波 + 品牌 offset, 原定開工)；
收工唔郁（打風唔會令你早走）。四邊模擬全部係**讀**現有邏輯，唔會自己再寫一套：

- 行位表 → rows_for_roster（實際開工之前嗰啲位標「返唔到」）
- 餐單   → resolve_meal_times_display（同 planner 一模一樣嗰個 resolver）
- 報平安 → duty_report.compute_slots（連 overlay、群組、訊息）
- 開/收工 → duty_form 嗰套（加班表＞行位表）+ 同一條 form／Post

「確實」＝天文台已公布落波時間，唔係自己估。未剔＝淨係睇，唔俾套用。
套用 = 寫加班表開工時間（報平安更／餐單／日曆跟住郁）+ 重排當日報平安更；
行位表一個字都唔會郁，OnOffDuty 亦唔會 hold（開工已定、收工唔變）。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from meal_planner.maintenance_db import load_sheet_rows, roster_code_defs, roster_post_for_code
from meal_planner.roster_codes import form_key_for_code, is_work_day, typhoon_offset_minutes
from meal_planner.schedule_grid import (
    MEAL_KEYS,
    ScheduleRow,
    load_overtime_overrides_from_rows,
    load_schedule_rows_from_rows,
    report_start_end,
    resolve_meal_times_display,
    rows_for_roster,
    weekday_allows,
)
from meal_planner.settings import AppSettings, get_settings
from meal_planner.timeparse import business_date, hhmm30, minutes_30h, normalize_hhmm, parse_time

BRAND_LABEL = {"vca": "VCA", "other": "Other"}

# 天文台現正追蹤緊嘅熱帶氣旋名單（結構化 XML，唔使 scrape 版面）。
# 天氣一律跟天文台——就算出面風平浪靜，佢話 8 號就係 8 號。
TC_LIST_URL = "https://www.weather.gov.hk/wxinfo/currwx/tc_list.xml"
TC_LIST_TIMEOUT_SECONDS = 5
TC_LIST_CACHE_SECONDS = 600

_tc_cache: tuple[float, dict[str, Any]] | None = None


def current_typhoon_names(*, force: bool = False) -> dict[str, Any]:
    """天文台正追蹤嘅熱帶氣旋（中／英文名）。10 分鐘 cache，唔會每次開 panel 都拉。

    攞唔到就 names 空 + note 講明點解——唔會靜靜哋當冇風，亦唔會留住舊名扮新。
    """
    import time as _time
    import urllib.request
    import xml.etree.ElementTree as ET

    global _tc_cache
    now = _time.monotonic()
    if not force and _tc_cache is not None and now - _tc_cache[0] < TC_LIST_CACHE_SECONDS:
        return _tc_cache[1]

    result: dict[str, Any] = {"names": [], "note": "", "source": TC_LIST_URL}
    try:
        with urllib.request.urlopen(TC_LIST_URL, timeout=TC_LIST_TIMEOUT_SECONDS) as response:
            root = ET.fromstring(response.read())
    except Exception as e:  # noqa: BLE001 - 攞唔到天文台唔可以拖冧個 panel
        result["note"] = f"Could not reach the Observatory ({e.__class__.__name__}) — type the name yourself."
        return result

    for node in root.findall("TropicalCyclone"):
        chinese = (node.findtext("TropicalCycloneChineseName") or "").strip()
        english = (node.findtext("TropicalCycloneEnglishName") or "").strip()
        if chinese or english:
            result["names"].append({"zh": chinese, "en": english})
    if not result["names"]:
        result["note"] = "No tropical cyclone is being tracked right now."
    _tc_cache = (now, result)
    return result


def _hhmm(minutes: int) -> str:
    """30 小時制分鐘 → HH:MM。

    24:00–29:59 照寫 24+（同全 project 一致）。夠鐘過咗 30:00 就已經係第二個
    business day 嘅朝早——冚返落去（30:00 → 06:00、31:20 → 07:20），
    唔會出個 30:00 咁嘅無效時間。
    """
    while minutes >= 1800:
        minutes -= 1440
    # 負數 ＝ 前一日（個波尋日落、今日先返工）。冚返落 0–1439，
    # 唔冚就會出「-14:40」咁嘅廢時間；係邊一日由 `*_minutes` 嗰邊表達。
    while minutes < 0:
        minutes += 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _as_time(hhmm: str) -> time | None:
    """30 小時制文字 → 真正鐘點（27:56 → 03:56）；「屬前一日」由 business date 表達。"""
    return parse_time(hhmm)


def _fmt(value: time | None) -> str:
    return hhmm30(value) if value is not None else ""


# 內容照行位表原文——收訊息嗰邊唔使知你係打風先報，template 同平時一模一樣。
# 本身唔使報平安更嘅更（例如 PenBM）唔會因為打風就多咗要報，所以個名分開兩個。
TYPHOON_START_CONTENT = "報開工, 報平安更"
TYPHOON_START_ONLY_CONTENT = "報開工"
# `-` 開頭跟返行位表 marker 慣例：報平安更唔佔時間，前一格嘅時長跨過佢。
TYPHOON_SAFE_CONTENT = "- 報平安更"


def _grid_section(
    rows: list[ScheduleRow],
    biz_date: date,
    start_m: int,
    planned_start: str,
    actual_start: str,
    report_minutes: list[int],
    earliest_m: int | None = None,
) -> dict[str, Any]:
    """行位表：當日該更碼嘅時間軸，實際開工之前嗰啲位（連原本嗰行報開工）全部返唔到。

    遲開工就重砌條時間軸：
    - 真開工鐘點插一行「報開工, 報平安更 (typhoon)」，時長 ＝ 去下一個佔時間嘅位；
    - 4 小時規則嗰啲報平安更逐個插（原本已經有同一鐘點嘅就唔重覆插）；
    - 開工之後原定嗰啲報平安更唔再算數，標 superseded。
    原本嗰行報開工唔會改時間——佢就係你返唔到嗰個位，改咗就睇唔出遲咗幾多。
    """
    from meal_planner.duty_report import SAFE_KEYWORD

    # 返唔返到，睇嘅係「最早幾點到得」（落波 + 個 offset），唔係「幾點開工」。
    # 開工照原定（冇遲到）唔代表報開工之前嗰啲位都趕得切——09:40 落波、10:40 先到得，
    # 10:35 簽簿就真係做唔到，雖然 10:45 報開工準時。
    if earliest_m is None:
        earliest_m = start_m
    shifted = actual_start != planned_start
    report_set = set(report_minutes) if shifted else set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.t is None or not weekday_allows(row.content, biz_date):
            continue
        text = row.content.strip()
        row_hhmm = row.t.strftime("%H:%M")
        minutes = minutes_30h(row_hhmm)
        out.append(
            {
                "time": row_hhmm,
                "minutes": minutes,
                "content": text,
                "duration_min": row.duration_min,
                "is_start": "報開工" in text,
                "is_end": "報收工" in text,
                "inserted": False,
                "unreachable": minutes < earliest_m,
                # 開工之後原定嗰啲報平安更：唔喺 4 小時表入面就係俾新表取代咗。
                "superseded": (
                    shifted and SAFE_KEYWORD in text and minutes >= start_m and minutes not in report_set
                ),
            }
        )
    if out and shifted:
        taken = {r["minutes"] for r in out if SAFE_KEYWORD in r["content"]}
        # `-` 開頭係 marker（報人數、取牌…），唔佔時間，計時長要跨過佢哋。
        nxt = next(
            (r for r in out if r["minutes"] > start_m and not r["content"].startswith("-")), None
        )
        out.append(
            {
                "time": actual_start,
                "minutes": start_m,
                "content": TYPHOON_START_CONTENT if report_minutes else TYPHOON_START_ONLY_CONTENT,
                "duration_min": (nxt["minutes"] - start_m) if nxt else None,
                "is_start": True,
                "is_end": False,
                "inserted": True,
                "unreachable": False,
                "superseded": False,
            }
        )
        for m in report_minutes[1:]:
            if m in taken:
                continue  # 原本行位表已經有呢個鐘點報更（多數係收工嗰行），唔使插多次
            out.append(
                {
                    "time": _hhmm(m),
                    "minutes": m,
                    "content": TYPHOON_SAFE_CONTENT,
                    "duration_min": None,
                    "is_start": False,
                    "is_end": False,
                    "inserted": True,
                    "unreachable": False,
                    "superseded": False,
                }
            )
        out.sort(key=lambda r: (r["minutes"], 0 if r["inserted"] else 1))
        # 俾 4 小時表取代嗰啲原本報平安更：直接剷走，唔會留一行劃走嘅喺度。
        # 報更時間本身由開工時間推出嚟，遲開工之後舊時間永遠唔會再用；
        # 想查返原本點樣？行位表原檔一直喺 Maint 度，一個字都冇郁過。
        out = [row for row in out if not row["superseded"]]
    for row in out:
        row.pop("minutes", None)
        row.pop("superseded", None)
    return {"rows": out, "note": "" if out else "No Schedule Grid rows for this code today."}


# 落波距離收工唔夠 4 個鐘 → 舖頭宣佈全日唔使返（返到都做唔到嘢）。
DAY_OFF_MIN_MINUTES = 240
TYPHOON_OFF_LABEL = "颱風假"


def typhoon_off_code(settings: AppSettings) -> str:
    """更碼定義表入面「颱風假」嗰個 pattern（例如 TP）。冇定義就回 ""。

    唔寫死 "TP"——個表你改得，改咗就跟你嗰個；搵唔到就由 caller 講明，唔會靜靜哋亂填。
    """
    for item in roster_code_defs(settings):
        if TYPHOON_OFF_LABEL in item.label:
            return item.pattern.rstrip("*").strip()
    return ""


TYPHOON_SNACK_MIN_MINUTES = 20
_SNACK_SLOT_RE = re.compile(r"break|tea", re.IGNORECASE)


def typhoon_snack_slot(
    rows: list[ScheduleRow], biz_date: date, start_m: int
) -> tuple[str, str] | None:
    """飯鐘食唔到嗰陣，帶落去嘅小食擺喺邊個位：開工之後第一個**長過 20 分鐘**嘅 Break／Tea。

    回 (HH:MM, 內容)；搵唔到就 None（唔會硬塞一個時間出嚟，由 caller 講明點解）。
    通常會同早餐差 4–5 個鐘，但唔用「差幾多個鐘」做條件——實際有幾長個 break 話事。
    """
    for row in rows:
        if row.t is None or not weekday_allows(row.content, biz_date):
            continue
        content = row.content.strip()
        if not _SNACK_SLOT_RE.search(content):
            continue
        if row.duration_min is None or row.duration_min <= TYPHOON_SNACK_MIN_MINUTES:
            continue
        if minutes_30h(row.t.strftime("%H:%M")) < start_m:
            continue
        return row.t.strftime("%H:%M"), content
    return None


def _meal_section(
    settings: AppSettings,
    *,
    biz_date: date,
    roster_code: str,
    work_day: bool,
    schedule_rows: list[ScheduleRow],
    overtime_all: dict[date, tuple[time | None, time | None]],
    typhoon_overtime: dict[date, tuple[time | None, time | None]],
) -> dict[str, Any]:
    """餐單：四餐時間打風前後對照（食材唔喺呢度模擬，打風只郁時間同食唔食到）。"""
    from meal_planner.meal_schedule import first_matching_meal_rule, load_meal_time_rules_from_rows

    rules = load_meal_time_rules_from_rows(load_sheet_rows("meal_times", settings).get("rows") or [])
    rule = first_matching_meal_rule(rules, roster_code)
    if rule is None:
        return {"rows": [], "note": f"Meal Times has no rule matching {roster_code}."}
    # 非返工日跌咗落「其他」（＝返工日嗰行，時間全部靠開工／收工推算）＝ 飯時表未有呢個
    # 更碼嘅行，四餐時間會計唔出——唔可以扮冇事，出返一句俾人知。
    fallback_note = (
        f"飯時表冇「{roster_code}」嘅行，跌咗落「{rule.code_pattern}」（返工日嗰套，"
        "靠開工／收工時間推算）——非返工日冇開工時間，四餐時間會計唔出。"
        if (not work_day) and rule.code_pattern == "其他"
        else ""
    )
    primary = {
        "code_pattern": rule.code_pattern,
        "早餐": rule.breakfast,
        "午餐": rule.lunch,
        "小食": rule.snack,
        "晚餐": rule.dinner,
    }

    def resolve(overrides: dict[date, tuple[time | None, time | None]]) -> dict[str, Any]:
        return resolve_meal_times_display(
            settings,
            day=biz_date,
            roster_code=roster_code,
            primary_rule=primary,
            is_work_day=work_day,
            restaurant=None,
            schedule_rows=schedule_rows,
            overtime_overrides=overrides,
        )

    before = resolve(overtime_all)
    after = resolve(typhoon_overtime)
    skipped = after.get("_skipped") or {}
    rows = [
        {
            "meal": meal,
            "rule": primary.get(meal) or "",
            "before": before.get(meal) or "",
            "after": after.get(meal) or "",
            "skipped": skipped.get(meal, ""),
        }
        for meal in MEAL_KEYS
        if primary.get(meal)
    ]
    return {
        "rows": rows,
        "skipped_meals": [row["meal"] for row in rows if not row["after"]],
        "note": fallback_note or ("" if rows else "Meal Times has no meals for this code."),
    }


REPORT_INTERVAL_MIN = 240  # 打風日：開工報一次，之後每 4 個鐘一次


def typhoon_report_minutes(start_m: int, end_m: int | None) -> list[int]:
    """打風報更鐘點（30 小時制分鐘）：開工報一次，跟住每 4 個鐘一次。

    最後一次唔會硬跳足 4 個鐘——收工距上一次唔夠 4 個鐘，就用收工時間做最後一次。
    收工時間唔知（行位表冇報收工又冇加班表 override）就淨係報開工嗰次。
    """
    times = [start_m]
    if end_m is None or end_m <= start_m:
        return times
    while times[-1] + REPORT_INTERVAL_MIN < end_m:
        times.append(times[-1] + REPORT_INTERVAL_MIN)
    times.append(end_m)
    return times


def _report_normal_section(
    settings: AppSettings,
    *,
    biz_date: date,
    roster_code: str,
    schedule_rows: list[ScheduleRow],
    overtime: tuple[time | None, time | None],
    report_minutes: list[int],
    end_m: int | None,
    shifted: bool,
) -> dict[str, Any]:
    """報平安更：打風日改用 4 小時節奏；冇遲到就照行位表（ReportNormal 原本嗰套）。"""
    from meal_planner.duty_report import compute_slots, load_config, load_overlay, normalize_segments

    config = load_config(settings)
    overlay = load_overlay(settings, biz_date)
    segments = normalize_segments(overlay.get("segments")) or [{"from": "00:00", "code": roster_code}]
    slot_overrides = overlay.get("slots") if isinstance(overlay.get("slots"), dict) else {}
    planned = compute_slots(
        schedule_rows, segments, biz_date, config["mapping"], config["message_template"],
        slot_overrides, overtime=overtime,
    )

    group = config["mapping"].get(roster_code, "")
    message = config["message_template"].replace("{code}", roster_code)
    rows: list[dict[str, Any]] = []
    skip_slot_ids: list[str] = []
    extra_times: list[str] = []
    # 本身冇報平安更嘅更（report_minutes 空）唔會因為打風就要報——照行位表（即係冇）。
    use_typhoon = shifted and bool(report_minutes)
    if use_typhoon:
        for i, m in enumerate(report_minutes):
            if i == 0:
                content = "報開工, 報平安更"
            elif end_m is not None and m == end_m:
                content = "報收工, 報平安更"
            else:
                content = "報平安更"
            rows.append({
                "time": _hhmm(m), "minutes": m, "content": content,
                "group": group, "message": message, "skipped": False,
            })

        # 套用嗰陣要做乜：行位表原本嗰啲 slot 邊個要 skip、邊幾個鐘點要加開。
        # 報開工／報收工兩個 slot 唔使郁——加班表寫咗開工，compute_slots 自己會搬。
        start_m = report_minutes[0]  # 第一次報更就係實際開工
        report_set = set(report_minutes)
        covered: set[int] = set()
        for slot in planned:
            content = slot["content"]
            minutes = minutes_30h(slot["original_time"])
            if "報開工" in content:
                covered.add(start_m)
            elif "報收工" in content:
                covered.add(end_m if end_m is not None else minutes)
            elif minutes in report_set:
                covered.add(minutes)
            else:
                skip_slot_ids.append(slot["id"])
        extra_times = [_hhmm(m) for m in report_minutes if m not in covered]
    else:
        rows = [
            {
                "time": slot["time"],
                "minutes": minutes_30h(slot["time"]),
                "content": slot["content"],
                "group": slot["group"],
                "message": slot["message"],
                "skipped": bool(slot["skipped"]),
            }
            for slot in planned
        ]

    notes = []
    if not rows:
        notes.append(f"{roster_code} has no 報平安更 — the typhoon does not add any.")
    if use_typhoon and end_m is None:
        notes.append("No finish time — only the on-duty report is planned.")
    if overlay.get("mode") == "stop":
        notes.append("ReportNormal is stopped for this day.")
    if rows and not config["auto_send"]:
        notes.append("Auto send is off — you will send them yourself.")
    return {
        "rows": rows,
        "mode": "typhoon" if use_typhoon else "grid",
        "interval_hours": REPORT_INTERVAL_MIN // 60,
        "planned_times": [slot["time"] for slot in planned],
        "skip_slot_ids": skip_slot_ids,
        "extra_times": extra_times,
        "note": " · ".join(notes),
    }


def _overtime_section(
    settings: AppSettings,
    *,
    biz_date: date,
    ot_start: time | None,
    ot_end: time | None,
    actual_start: str,
    name: str,
    day_off: bool = False,
    shifted: bool = True,
) -> dict[str, Any]:
    """加班表：套用之後嗰行會變成點（加班表就係全系統嘅權威開工／收工來源）。"""
    note_now = ""
    try:
        payload = load_sheet_rows("overtime", settings)
        rows = payload.get("rows") or []
        header = [str(v or "").strip() for v in rows[0]] if rows else []
        if "日期" in header and "備註" in header:
            from meal_planner.schedule_grid import _to_date

            c_date, c_note = header.index("日期"), header.index("備註")
            for row in rows[1:]:
                if isinstance(row, list) and c_date < len(row) and _to_date(row[c_date]) == biz_date:
                    note_now = str(row[c_note] or "").strip() if c_note < len(row) else ""
                    break
    except Exception:  # noqa: BLE001 - 冇加班表就當空白，唔好拖冧成個 panel
        pass

    if day_off:
        # 全日唔使返：唔係加班，係唔返工——加班表嗰行整行清走，改為更碼變颱風假。
        return {
            "rows": [
                {"field": "日期", "before": biz_date.isoformat(), "after": biz_date.isoformat()},
                {"field": "開工", "before": _fmt(ot_start), "after": ""},
                {"field": "收工", "before": _fmt(ot_end), "after": ""},
                {"field": "備註", "before": note_now, "after": ""},
            ],
            "note": "全日唔使返 → Apply 清走加班表呢一行，改為將更碼設做颱風假。",
        }
    if not shifted:
        # 開工冇郁（例如個波喺開工之前已經落）＝ 冇加班，加班表一個字都唔使寫。
        return {
            "rows": [],
            "note": "報開工同報收工都冇變 — Apply 唔會寫加班表。",
        }
    return {
        "rows": [
            {"field": "日期", "before": biz_date.isoformat(), "after": biz_date.isoformat()},
            {"field": "開工", "before": _fmt(ot_start), "after": actual_start},
            {"field": "收工", "before": _fmt(ot_end), "after": _fmt(ot_end)},
            {"field": "備註", "before": note_now, "after": typhoon_overtime_note(name)},
        ],
        "note": "" if ot_start is None else "This day already has an Overtime start — Apply overwrites it.",
    }


def _gc_section(
    settings: AppSettings,
    *,
    biz_date: date,
    roster_code: str,
    typhoon_overtime: dict[date, tuple[time | None, time | None]],
    overtime_all: dict[date, tuple[time | None, time | None]],
    day_off: bool = False,
    off_code: str = "",
) -> dict[str, Any]:
    """Google Calendar：更表 event 同「起身」鬧鐘會變成幾點。

    日曆用嘅係**更時表**（計糧官方時間）+ 加班表 override，唔係行位表——
    所以呢度特登用返 resolve_shift_time，唔好攞 panel 頂嗰個開工當佢一樣。
    """

    from meal_planner.google_calendar_sync import config_from_env
    from meal_planner.schedule_grid import load_wake_alarm_overrides_from_rows
    from meal_planner.shift_time import holiday_dates_from_rows, resolve_shift_time

    def sheet(key: str) -> list[Any]:
        try:
            return load_sheet_rows(key, settings).get("rows") or []
        except Exception:  # noqa: BLE001
            return []

    payroll_rows = sheet("payroll_times")
    holidays = holiday_dates_from_rows(sheet("public_holidays"))
    before = resolve_shift_time(payroll_rows, roster_code, biz_date, holidays, overtime_all)
    after = resolve_shift_time(payroll_rows, roster_code, biz_date, holidays, typhoon_overtime)
    if before[0] is None and after[0] is None:
        return {"rows": [], "note": f"更時表 has no times for {roster_code} — nothing lands on the calendar."}

    config = config_from_env(settings)
    offset = config.wake_offset_hours
    wake_override = load_wake_alarm_overrides_from_rows(sheet("wake_alarms")).get(biz_date)

    def wake_for(start: time | None) -> str:
        if wake_override is not None:
            return _fmt(wake_override)
        if start is None:
            return ""
        return _fmt((datetime.combine(biz_date, start) - timedelta(hours=offset)).time())

    def span(pair: tuple[time | None, time | None]) -> str:
        start, end = pair
        return f"{_fmt(start)}–{_fmt(end)}" if start and end else _fmt(start) or _fmt(end)

    notes = []
    if wake_override is not None:
        notes.append("起身表 overrides the wake alarm — it does not move with the on-duty time.")

    if day_off:
        # 非返工日：日曆寫一個全日 event 落「非返工日」個 calendar（summary ＝ 更碼），
        # 更表 event 冇咗；起身鬧鐘淨係喺起身表有 override 嗰陣先會有。
        return {
            "rows": [
                {
                    "event": "起身", "calendar": "alarm", "calendar_id": config.alarm_calendar_id,
                    "before": wake_for(before[0]), "after": _fmt(wake_override) if wake_override else "",
                },
                {
                    "event": roster_code or "更表", "calendar": "更表",
                    "calendar_id": config.work_calendar_id,
                    "before": span(before), "after": "",
                },
                {
                    "event": off_code or "颱風假", "calendar": "非返工日",
                    "calendar_id": config.leave_calendar_id,
                    "before": "", "after": "all-day",
                },
            ],
            "wake_offset_hours": offset,
            "note": "全日唔使返 → 更表 event 冇咗，改為非返工日全日 event"
            + ("；起身鬧鐘跟起身表。" if wake_override else "；冇起身鬧鐘。"),
        }

    rows = [
        {
            "event": "起身",       # 寫落日曆嗰個 event summary
            "calendar": "alarm",   # 個日曆本身就係叫 alarm
            "calendar_id": config.alarm_calendar_id,
            "before": wake_for(before[0]),
            "after": wake_for(after[0]),
        },
        {
            "event": roster_code or "更表",
            "calendar": "更表",
            "calendar_id": config.work_calendar_id,
            "before": span(before),
            "after": span(after),
        },
    ]
    # 照鐘點排（起身梗係喺開工之前，除非起身表 override 咗）——同行位表一樣睇得順。
    rows.sort(key=lambda row: minutes_30h(row["after"][:5]) if row["after"][:5].count(":") else 10**6)
    return {
        "rows": rows,
        "wake_offset_hours": offset,
        "note": " · ".join(notes),
    }


def _onoffduty_section(
    settings: AppSettings,
    *,
    roster_code: str,
    planned_start: str,
    actual_start: str,
    end_text: str,
) -> dict[str, Any]:
    """報開工／報收工：邊條 form、邊個 Post、打風後幾點交。"""
    from meal_planner.duty_form import load_onoff_config

    post = roster_post_for_code(settings).get(roster_code, "")
    form_key = form_key_for_code(roster_code)
    rows = [
        {"kind": "start", "label": "On Duty", "before": planned_start, "after": actual_start},
        {"kind": "end", "label": "Off Duty", "before": end_text, "after": end_text},
    ]
    notes = []
    if not post:
        notes.append(f"No Post mapped for {roster_code}.")
    if not load_onoff_config(settings)["auto_send"]:
        notes.append("Semi mode — you will open the link and submit yourself.")
    return {
        "form": form_key,
        "form_label": "VCA form" if form_key == "vca" else "Other form",
        "post": post,
        "rows": rows,
        "note": " · ".join(notes),
    }


MAX_LOOKAHEAD_DAYS = 14


def _shift_bounds(
    settings: AppSettings,
    grid_rows: list[ScheduleRow],
    overtime_all: dict[date, tuple[time | None, time | None]],
    day: date,
    code: str,
) -> tuple[int | None, int | None]:
    """嗰日嗰個更嘅開工／收工（30 小時制分鐘）；加班表 override 行先。"""
    rows = rows_for_roster(grid_rows, code, day)
    grid_start, grid_end = report_start_end(rows, day)
    ot_start, ot_end = overtime_all.get(day, (None, None))
    start = ot_start or grid_start
    end = ot_end or grid_end
    start_m = minutes_30h(_fmt(start)) if start is not None else None
    end_m = minutes_30h(_fmt(end)) if end is not None else None
    if start_m is not None and end_m is not None and end_m < start_m:
        end_m += 1440  # 通宵更：收工 06:00 咁，30 小時制當咗第二日
    return start_m, end_m


def _affected_work_day(
    settings: AppSettings,
    signal_date: date,
    signal_m: int,
    grid_rows: list[ScheduleRow],
    overtime_all: dict[date, tuple[time | None, time | None]],
    manual_code: str = "",
) -> tuple[date, str, int] | None:
    """落波之後最近嗰個返到工嘅工作日 → (日期, 更碼, 落波時間相對嗰日嘅分鐘)。

    落波嗰日嘅更已經收咗工（例如 21:45 收工、29:00 先落波）＝ 嗰更根本返唔到，
    要睇嘅係下一個工作日。落波嗰日唔係工作日（SB 咁）都一樣行落去。
    自己揀咗更碼就當每日都返嗰個更（純模擬），唔再問更表。
    """
    from meal_planner.duty_form import roster_code_for

    defs = roster_code_defs(settings)
    if manual_code and not is_work_day(defs, manual_code):
        return signal_date, manual_code, signal_m  # 俾上層出「唔係返工日」
    for offset_days in range(MAX_LOOKAHEAD_DAYS + 1):
        day = signal_date + timedelta(days=offset_days)
        code = manual_code or roster_code_for(settings, day)
        if not code or not is_work_day(defs, code):
            continue
        signal_rel = signal_m - offset_days * 1440
        start_m, end_m = _shift_bounds(settings, grid_rows, overtime_all, day, code)
        if start_m is None:
            # 工作日但行位表冇報開工行——照返俾上層報錯，唔好靜靜哋跳去下一日
            return day, code, signal_rel
        if end_m is None or end_m > signal_rel:
            return day, code, signal_rel
    return None


def build_typhoon_plan(
    settings: AppSettings | None = None,
    *,
    biz_date: date | None = None,
    signal_time: str = "",
    roster_code: str | None = None,
    confirmed: bool = False,
    day_off_announced: bool = False,
    name: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """打風落波模擬：唔會寫任何嘢，淨係算俾你睇。"""
    settings = settings or get_settings()
    now = now or datetime.now(ZoneInfo(settings.dates.timezone))
    today = business_date(now)
    # 日期 + 落波時間係一 pair ＝ 個波幾時落。之後模擬邊日，係由呢個時刻推出嚟嘅
    # 「落波之後最近嗰個返到工嘅工作日」，唔一定係你揀嗰日。
    signal_date = biz_date or today
    manual_code = str(roster_code or "").strip()

    plan: dict[str, Any] = {
        "ok": False,
        "signal_date_iso": signal_date.isoformat(),
        "date_iso": signal_date.isoformat(),
        "today_iso": today.isoformat(),
        "relation": "today" if signal_date == today else ("past" if signal_date < today else "future"),
        "roster_code": manual_code,
        "auto_roster_code": "",
        "code_source": "manual" if manual_code else "roster",
        "known_codes": sorted(roster_post_for_code(settings)),
        "signal_time": "",
        "confirmed": bool(confirmed),
        "note": "",
    }

    signal_text = normalize_hhmm(signal_time)
    if not signal_text:
        plan["note"] = (
            "Cannot read that time — try 11:40 / 1140 / 2416." if signal_time
            else "Enter the signal-down time."
        )
        return plan
    # 落波時間一律用 30 小時制讀：打 02:56 即係 26:56（同全 project 一致，
    # 唔會有「當日清晨定係通宵更嗰段」兩個讀法要人估）。
    signal_m = minutes_30h(signal_text)
    signal_text = _hhmm(signal_m)
    plan["signal_time"] = signal_text

    grid_rows = load_schedule_rows_from_rows(load_sheet_rows("schedule_grid", settings).get("rows") or [])
    overtime_all = load_overtime_overrides_from_rows(load_sheet_rows("overtime", settings).get("rows") or [])

    affected = _affected_work_day(
        settings, signal_date, signal_m, grid_rows, overtime_all, manual_code
    )
    if affected is None:
        plan["note"] = (
            f"No roster code / work day within {MAX_LOOKAHEAD_DAYS} days after "
            f"{signal_date.isoformat()} — nothing to simulate."
        )
        return plan
    biz_date, target_code, signal_m = affected
    from meal_planner.duty_form import roster_code_for

    auto_code = roster_code_for(settings, biz_date)  # 更表本身嗰日嘅更碼（用嚟講返你改咗）
    code = manual_code or target_code
    plan["date_iso"] = biz_date.isoformat()
    plan["roster_code"] = code
    plan["auto_roster_code"] = auto_code
    plan["code_source"] = "manual" if manual_code and manual_code != auto_code else "roster"
    plan["relation"] = "today" if biz_date == today else ("past" if biz_date < today else "future")
    plan["days_after_signal"] = (biz_date - signal_date).days
    if not is_work_day(roster_code_defs(settings), code):
        plan["note"] = f"{code} is not a work day — nothing to simulate."
        return plan

    my_rows = rows_for_roster(grid_rows, code, biz_date)
    grid_start, grid_end = report_start_end(my_rows, biz_date)
    ot_start, ot_end = overtime_all.get(biz_date, (None, None))
    planned_start = ot_start or grid_start
    end = ot_end or grid_end

    if planned_start is None:
        plan["note"] = f"Schedule Grid has no 報開工 row for {code} — planned start unknown."
        return plan

    offset = typhoon_offset_minutes(code)
    planned_m = minutes_30h(_fmt(planned_start))
    end_text = _fmt(end)
    end_m = minutes_30h(end_text) if end_text else None
    # 通宵更收工 06:00 咁，30 小時制當咗係第二日（360）——同開工比就知要 +24h，
    # 否則成個更會計成「負時長」，報更節奏同全日唔使返嗰條規則都會計錯。
    if end_m is not None and end_m < planned_m:
        end_m += 1440
    earliest_m = signal_m + offset
    start_m = max(earliest_m, planned_m)
    actual_start = _hhmm(start_m)
    planned_text = _fmt(planned_start)

    typhoon_overtime = (_as_time(actual_start), ot_end)
    typhoon_all = dict(overtime_all)
    typhoon_all[biz_date] = typhoon_overtime

    from meal_planner.duty_report import safe_slots_for_code

    # 落波距離收工唔夠 4 個鐘 → **有可能**全日唔使返，但要舖頭宣佈先作實，
    # 唔會自己當咗佢。宣佈咗（剔咗 Day off）先真係唔使開工／唔使報更／唔使交 form，
    # 當日更碼變颱風假。未宣佈就照普通遲開工計——你仲係要返，只係返得短。
    day_off_possible = end_m is not None and (end_m - signal_m) < DAY_OFF_MIN_MINUTES
    day_off = bool(day_off_announced) and day_off_possible
    off_code = typhoon_off_code(settings) if day_off_possible else ""
    shifted = (not day_off) and actual_start != planned_text
    # 本身冇報平安更嘅更（例如 PenBM）打風都唔會突然要報——4 小時規則淨係套落有得報嗰啲。
    has_reports = bool(safe_slots_for_code(grid_rows, code, biz_date))
    report_minutes = typhoon_report_minutes(start_m, end_m) if shifted and has_reports else []

    plan.update(
        {
            "ok": True,
            "brand": BRAND_LABEL[form_key_for_code(code)],
            "offset_minutes": offset,
            "earliest_start": _hhmm(earliest_m),
            "earliest_minutes": earliest_m,
            "planned_start": planned_text,
            "planned_minutes": planned_m,
            "start": actual_start,
            "start_minutes": start_m,
            "signal_minutes": signal_m,
            "end_minutes": end_m,
            "end": end_text,
            "delay_minutes": 0 if day_off else max(0, start_m - planned_m),
            "start_shifted": shifted,
            "day_off": day_off,
            "day_off_possible": day_off_possible,
            "day_off_code": off_code,
            "day_off_note": (
                ""
                if not day_off_possible
                else (
                    f"落波 {signal_text} 距離收工 {end_text} 唔夠 "
                    f"{DAY_OFF_MIN_MINUTES // 60} 個鐘。"
                    + (
                        (
                            "舖頭宣佈全日唔使返。"
                            + (
                                f"套用會將當日更碼改做「{off_code}」（颱風假）。"
                                if off_code
                                else "更碼定義表冇「颱風假」，套用改唔到更碼——自己去更表改。"
                            )
                        )
                        if day_off
                        else "可能全日唔使返——等舖頭宣佈，宣佈咗就剔「Day off」；未宣佈就照返工計。"
                    )
                )
            ),
            "overtime_start": _fmt(ot_start),
            "overtime_end": _fmt(ot_end),
            "grid": _grid_section(
                my_rows, biz_date, start_m, planned_text, actual_start, report_minutes,
                earliest_m=earliest_m,
            ),
            "meals": _meal_section(
                settings,
                biz_date=biz_date,
                roster_code=code,
                work_day=True,
                schedule_rows=grid_rows,
                overtime_all=overtime_all,
                typhoon_overtime=typhoon_all,
            ),
            "report_normal": _report_normal_section(
                settings,
                biz_date=biz_date,
                roster_code=code,
                schedule_rows=grid_rows,
                overtime=(ot_start, ot_end),
                report_minutes=report_minutes,
                end_m=end_m,
                shifted=shifted,
            ),
            "overtime": _overtime_section(
                settings,
                biz_date=biz_date,
                ot_start=ot_start,
                ot_end=ot_end,
                actual_start=actual_start,
                name=name,
                day_off=day_off,
                shifted=shifted,
            ),
            "gc": _gc_section(
                settings,
                biz_date=biz_date,
                roster_code=code,
                typhoon_overtime=typhoon_all,
                overtime_all=overtime_all,
                day_off=day_off,
                off_code=off_code,
            ),
            "onoffduty": _onoffduty_section(
                settings,
                roster_code=code,
                planned_start=planned_text,
                actual_start=actual_start,
                end_text=end_text,
            ),
        }
    )
    if day_off:
        # 全日唔使返：冇嘢要做，各段一律出空 + 講明點解（唔好留返一堆做唔到嘅嘢喺度）。
        note = plan["day_off_note"]
        plan["grid"] = {"rows": [], "note": "全日唔使返 —— 冇行位要行。"}
        plan["report_normal"] = {
            "rows": [], "mode": "off", "interval_hours": REPORT_INTERVAL_MIN // 60,
            "planned_times": plan["report_normal"].get("planned_times") or [],
            "skip_slot_ids": [], "extra_times": [], "note": "全日唔使返 —— 冇更要報。",
        }
        plan["onoffduty"]["rows"] = []
        plan["onoffduty"]["form"] = ""
        plan["onoffduty"]["form_label"] = ""
        plan["onoffduty"]["post"] = ""
        plan["onoffduty"]["note"] = "全日唔使返 —— 冇 form 要交。"
        # 餐單唔係「冇」——係變咗非返工日嗰套飯時（更碼用颱風假嗰個），照計照出。
        plan["meals"] = _meal_section(
            settings,
            biz_date=biz_date,
            roster_code=off_code or code,
            work_day=False,
            schedule_rows=grid_rows,
            overtime_all=overtime_all,
            typhoon_overtime=overtime_all,
        )
        plan["meals"]["note"] = (
            plan["meals"]["note"] or f"全日唔使返 —— 跟非返工日（{off_code or code}）嘅飯時。"
        )

    plan["applied"] = _applied_state(settings, biz_date, actual_start, ot_start)
    plan["can_apply"] = bool(confirmed) and plan["relation"] != "past"
    if not confirmed:
        plan["apply_blocked"] = "Tick Confirmed first — the signal-down time must be announced."
    elif plan["relation"] == "past":
        plan["apply_blocked"] = "Past days cannot be applied."
    else:
        plan["apply_blocked"] = ""
    return plan


def _applied_state(
    settings: AppSettings, biz_date: date, actual_start: str, ot_start: time | None
) -> dict[str, Any]:
    """而家真系統嘅狀態：加班表寫咗未、兩張卡 hold 住未。"""
    from meal_planner.duty_form import load_onoff_log

    log = load_onoff_log(settings, biz_date)
    return {
        "overtime_start": _fmt(ot_start),
        "overtime_matches": _fmt(ot_start) == actual_start,
        "hold_start": (log.get("start") or {}).get("status") == "hold",
        "hold_end": (log.get("end") or {}).get("status") == "hold",
    }


TYPHOON_NOTE_PREFIX = "颱風"


def typhoon_day_note(settings: AppSettings, biz_date: date) -> str:
    """加班表嗰日嘅備註——打風日先會以「颱風」開頭（Apply 寫落去嗰個）。冇就回 ""。

    「呢日係咪打風日」唔另開一張表記——加班表本身已經係權威嘅當日開工來源，
    備註就係個 marker，睇得到、改得到、刪咗即刻返正常。
    """
    try:
        payload = load_sheet_rows("overtime", settings)
    except Exception:  # noqa: BLE001 - 冇加班表 = 冇打風日，唔可以拖冧個 export
        return ""
    rows = payload.get("rows") or [] if isinstance(payload, dict) else []
    if not rows:
        return ""
    header = [str(v or "").strip() for v in rows[0]]
    if "日期" not in header or "備註" not in header:
        return ""
    c_date, c_note = header.index("日期"), header.index("備註")
    from meal_planner.schedule_grid import _to_date

    for row in rows[1:]:
        if not isinstance(row, list) or c_date >= len(row) or _to_date(row[c_date]) != biz_date:
            continue
        note = str(row[c_note] or "").strip() if c_note < len(row) else ""
        return note if note.startswith(TYPHOON_NOTE_PREFIX) else ""
    return ""


def typhoon_grid_rows(
    settings: AppSettings, biz_date: date, roster_code: str
) -> list[dict[str, Any]] | None:
    """打風日推落電話嗰份行位表；唔係打風日（或者冇遲開工）就 None。

    返唔到嘅位同俾 4 小時表取代咗嘅報平安更 → `disabled`（＝電話嗰粒 off button），
    真開工同 4 小時報更 → 新增嘅行。行位表 sheet 本身照樣一個字都唔郁。
    """
    if not typhoon_day_note(settings, biz_date) or not roster_code:
        return None

    from meal_planner.duty_report import safe_slots_for_code

    grid_rows = load_schedule_rows_from_rows(load_sheet_rows("schedule_grid", settings).get("rows") or [])
    my_rows = rows_for_roster(grid_rows, roster_code, biz_date)
    grid_start, grid_end = report_start_end(my_rows, biz_date)
    overtime = load_overtime_overrides_from_rows(load_sheet_rows("overtime", settings).get("rows") or [])
    ot_start, ot_end = overtime.get(biz_date, (None, None))
    if ot_start is None or grid_start is None:
        return None

    start_m = minutes_30h(_fmt(ot_start))
    planned_text = _fmt(grid_start)
    if start_m == minutes_30h(planned_text):
        return None  # 加班表寫住開工，但同行位表一樣——即係冇遲開工，唔使改

    end = ot_end or grid_end
    end_m = minutes_30h(_fmt(end)) if end is not None else None
    report_minutes = (
        typhoon_report_minutes(start_m, end_m)
        if safe_slots_for_code(grid_rows, roster_code, biz_date)
        else []
    )
    section = _grid_section(my_rows, biz_date, start_m, planned_text, _hhmm(start_m), report_minutes)
    # 俾取代嗰啲喺 _grid_section 已經剷咗；返唔到嘅位就照推但 disabled——
    # 嗰啲係「錯過咗」，唔係「俾人取代」，見到先知原本幾點開工、遲咗幾多。
    return [
        {
            "time": row["time"],
            "content": row["content"],
            "duration_min": row["duration_min"],
            "disabled": bool(row["unreachable"]),
        }
        for row in section["rows"]
    ]


def build_typhoon_meal_plan(
    settings: AppSettings | None = None,
    *,
    biz_date: date,
    signal_time: str,
    roster_code: str | None = None,
    day_off_announced: bool = False,
    reroll_nonce: int = 0,
) -> dict[str, Any]:
    """當日餐單重新計一次（打風開工時間 + 帶落去嗰餐小食）——用返 planner 同一支筆。

    唔會寫任何嘢；出嚟嘅 payload 同 `/api/preview` 一模一樣（headers / nutrient_keys /
    days），所以前端可以照用餐單頁個 renderer，唔使另寫一套。
    """
    import dataclasses

    from meal_planner.indicators import DayIndicatorProfile
    from meal_planner.meal_schedule import build_day_meal_plan, build_meal_planning_cache
    from meal_planner.nutrition_db import load_target_rows
    from meal_planner.preview import DayPreview, _calc_day_summary, _serialize_profile
    from meal_planner.indicators import NUTRIENT_KEYS

    settings = settings or get_settings()
    plan = build_typhoon_plan(
        settings, biz_date=biz_date, signal_time=signal_time, roster_code=roster_code,
        day_off_announced=day_off_announced,
    )
    if not plan["ok"]:
        raise ValueError(plan["note"] or "Nothing to compute.")

    # 個波今日落、但要返嘅係聽日嗰更：餐單要跟返 plan 揀咗嘅返工日，
    # 唔係你喺格仔入面打嗰日（否則行位表出聽日、餐單出今日，兩邊唔對數）。
    biz_date = date.fromisoformat(plan["date_iso"])

    day_off = bool(plan.get("day_off"))
    code = (plan.get("day_off_code") or plan["roster_code"]) if day_off else plan["roster_code"]
    start_m = minutes_30h(plan["start"])
    grid_rows = load_schedule_rows_from_rows(load_sheet_rows("schedule_grid", settings).get("rows") or [])
    my_rows = rows_for_roster(grid_rows, code, biz_date)

    # 飯鐘食唔到先至要帶小食；搵開工後第一個長過 20 分鐘嘅 Break／Tea。
    dropped = [meal for meal in MEAL_KEYS if meal in (plan["meals"].get("skipped_meals") or [])]
    overrides: dict[str, str] = {}
    snack_note = ""
    if day_off:
        snack_note = f"全日唔使返 —— 跟非返工日（{code}）嘅飯時同指標。"
    elif plan["start_shifted"] and dropped:
        slot = typhoon_snack_slot(my_rows, biz_date, start_m)
        if slot is None:
            snack_note = (
                f"{'、'.join(dropped)} 冇得食，但開工之後搵唔到長過 "
                f"{TYPHOON_SNACK_MIN_MINUTES} 分鐘嘅 Break／Tea——自己搵位食。"
            )
        else:
            overrides["小食"] = slot[0]
            snack_note = f"{'、'.join(dropped)} 冇得食 → 帶小食，喺 {slot[0]}「{slot[1]}」食。"

    overtime_all = load_overtime_overrides_from_rows(load_sheet_rows("overtime", settings).get("rows") or [])
    ot_start, ot_end = overtime_all.get(biz_date, (None, None))
    typhoon_all = dict(overtime_all)
    typhoon_all[biz_date] = (_as_time(plan["start"]), ot_end)

    # 全日唔使返：唔套打風開工（根本冇開工），指標用非返工日嗰行。
    cache = dataclasses.replace(
        build_meal_planning_cache(settings),
        overtime_overrides=overtime_all if day_off else typhoon_all,
    )
    headers, work_vals, nonwork_vals = load_target_rows(settings)
    nutrients = DayIndicatorProfile.from_row_cells(list(nonwork_vals if day_off else work_vals))

    meal_plan = build_day_meal_plan(
        settings, code, not day_off, biz_date,
        indicators=nutrients, cache=cache, meal_time_overrides=overrides or None,
        reroll_nonce=reroll_nonce,
    )
    meal_plan["summary"] = _calc_day_summary(meal_plan, nutrients, settings)
    if snack_note:
        meal_plan["typhoon_note"] = snack_note

    day = DayPreview(
        date=biz_date, roster_code=code, is_work_day=not day_off,
        indicator_profile="nonworkday" if day_off else "workday",
    )
    return {
        "headers": [str(h) if h is not None else None for h in headers],
        "indicator_rows": {
            "workday": [str(v) if v is not None else "" for v in work_vals],
            "nonworkday": [str(v) if v is not None else "" for v in nonwork_vals],
        },
        "nutrient_keys": list(NUTRIENT_KEYS),
        "days": [day.to_dict(_serialize_profile(nutrients), meal_plan=meal_plan)],
        "snack_note": snack_note,
        "snack_time": overrides.get("小食", ""),
        "start": plan["start"],
    }


def _push_phone_schedule_grid(target_date: date) -> dict[str, Any]:
    """叫電話即刻重新匯入行位表——唔 push 就要等聽日 05:00，打風當日太遲。

    電話係自己 pull /export-all，而 export-all 有佢自己揀日子嘅邏輯（今日未收工就今日，
    否則下一個返工日）。撞唔啱你 Apply 嗰日就要講明——電話攞到嘅唔係打風嗰日。
    """
    from meal_planner.phone_push import push_schedule_grid

    try:
        result = push_schedule_grid()
    except Exception as e:  # noqa: BLE001 - 電話推唔到唔應該令加班表／報更白做
        return {"status": "error", "detail": str(e)}
    plan_date = str(result.get("plan_date") or "")
    if result.get("status") == "ok" and plan_date and plan_date != target_date.isoformat():
        result["status"] = "other_day"
        result["detail"] = (
            f"電話攞咗 {plan_date} 嘅行位表，唔係打風嗰日（{target_date.isoformat()}）——"
            "電話出邊日由 export-all 決定。"
        )
    return result


def _sync_google_calendar(settings: AppSettings) -> dict[str, Any]:
    """Apply 之後即刻同步日曆。

    日曆本身只喺「儲存更表」嗰陣自動 sync，改加班表／改更碼都唔會觸發——
    所以打風套用完要自己叫一次，否則個日曆一直停喺舊時間。
    冇開 sync／登入唔到都唔可以拖冧成個 Apply，出返個 status 就算。
    """
    from meal_planner.google_calendar_sync import (
        google_calendar_auth_status,
        sync_roster_to_google_calendar,
    )

    try:
        rows = load_sheet_rows("roster", settings).get("rows") or []
        result = sync_roster_to_google_calendar(rows, settings)
    except Exception as e:  # noqa: BLE001 - 日曆失敗唔應該令加班表／報更白做
        result = {"status": "error", "detail": str(e)}
    if result.get("status") in {"error", "not_authenticated"}:
        # token 過期／未登入係最常見嘅原因——分開講明，前端就可以彈窗叫你登入，
        # 唔會俾人以為「同步咗」。
        try:
            auth = google_calendar_auth_status(settings)
        except Exception:  # noqa: BLE001
            auth = {"authenticated": False, "status": "auth status unavailable"}
        if not auth.get("authenticated"):
            return {
                "status": "needs_login",
                "detail": str(result.get("detail") or auth.get("status") or "Google Calendar not authenticated"),
            }
    return result


def typhoon_overtime_note(name: str) -> str:
    """加班表個「備註」欄寫乜：`颱風` + 個名（冇名就淨係 `颱風`）。"""
    return f"颱風{str(name or '').strip()}"


def apply_typhoon(
    settings: AppSettings | None = None,
    *,
    biz_date: date | None = None,
    signal_time: str = "",
    roster_code: str | None = None,
    day_off_announced: bool = False,
    name: str = "",
) -> dict[str, Any]:
    """套用模擬結果落真系統——**行位表一個字都唔會郁**。

    1. 加班表寫開工時間（備註＝颱風＋個名）：報平安更／餐單／Google Calendar 全部跟住郁；
    2. ReportNormal 當日 overlay：原本行位表嗰啲中途報平安更 skip 咗，4 小時規則嗰啲加開
       （報開工／報收工兩個 slot 唔使郁——加班表寫咗開工，compute_slots 自己會搬）。

    **唔會 hold OnOffDuty**：開工時間落波之後已經確定咗（就係寫入加班表嗰個），收工又唔變，
    冇嘢等緊，兩張卡照夠鐘自動交。真開工／收工同計劃唔同先自己去 OnOffDuty 撳 Send now。

    行位表係「由生效日期起一直用」嘅版本表，寫一份打風版落去會連之後所有日子都變埋，
    所以打風一律行 per-date overlay，第二日自動返正常。
    """
    from meal_planner.duty_form import set_roster_code, set_time_override
    from meal_planner.duty_report import apply_override, save_overlay

    settings = settings or get_settings()
    plan = build_typhoon_plan(
        settings, biz_date=biz_date, signal_time=signal_time, roster_code=roster_code,
        confirmed=True, day_off_announced=day_off_announced, name=name,
    )
    if not plan["ok"]:
        raise ValueError(plan["note"] or "Nothing to apply.")
    if plan["relation"] == "past":
        raise ValueError("Past days cannot be applied.")

    target_date = date.fromisoformat(plan["date_iso"])

    if plan["day_off"]:
        # 全日唔使返：唔係遲開工，係當日根本唔返工——改更表更碼做颱風假，
        # 之後報更／餐單／日曆／電話全部自己跟住變（同你手動改更碼一模一樣）。
        # 順手清走之前可能已經套用過嘅打風開工時間同報更 overlay。
        if not plan["day_off_code"]:
            raise ValueError(plan["day_off_note"])
        set_time_override(settings, target_date, start="", end="")
        save_overlay(settings, target_date, {})
        set_roster_code(settings, target_date, plan["day_off_code"])
        result = build_typhoon_plan(
            settings, biz_date=biz_date, signal_time=signal_time,
            roster_code=roster_code, confirmed=True, day_off_announced=True, name=name,
        )
        result["apply_result"] = {
            "day_off": True,
            "roster_code": plan["day_off_code"],
            "note": plan["day_off_note"],
            "google_calendar": _sync_google_calendar(settings),
            "phone_push": _push_phone_schedule_grid(target_date),
        }
        return result

    # 開工冇郁（個波喺開工之前已經落）＝ 冇嘢好加，唔好無端端寫多行加班表。
    wrote_overtime = bool(plan["start_shifted"])
    if wrote_overtime:
        set_time_override(settings, target_date, start=plan["start"], note=typhoon_overtime_note(name))

    report = plan["report_normal"]
    # hidden（唔係 skip）：舊報更時間當日根本唔存在，ReportNormal 都唔應該見到佢哋。
    for slot_id in report.get("skip_slot_ids") or []:
        apply_override(
            settings, slot_patch={"id": slot_id, "hidden": True}, source="typhoon", biz_date=target_date
        )
    extra_times = report.get("extra_times") or []
    if extra_times:
        apply_override(
            settings,
            extra_slots=[{"time": t, "code": plan["roster_code"]} for t in extra_times],
            source="typhoon",
            biz_date=target_date,
        )

    result = build_typhoon_plan(
        settings, biz_date=biz_date, signal_time=signal_time, roster_code=roster_code,
        confirmed=True, day_off_announced=day_off_announced, name=name,
    )
    result["apply_result"] = {
        "overtime_start": plan["start"] if wrote_overtime else "",
        "overtime_note": typhoon_overtime_note(name) if wrote_overtime else "報開工同報收工都冇變，冇寫加班表",
        "reports_added": extra_times,
        "reports_skipped": len(report.get("skip_slot_ids") or []),
        "google_calendar": _sync_google_calendar(settings),
        "phone_push": _push_phone_schedule_grid(target_date),
    }
    return result
