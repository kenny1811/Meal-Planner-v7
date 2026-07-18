"""報開工／報收工：由更碼推導今日 Google Form 打卡計劃 + 砌預填連結。

同 duty_report（報平安更 WhatsApp）係兩件事：
- 報平安更 → 行位表「報平安更」rows（duty_report.py）。
- 報開工／報收工 → 呢度，時間來源係 **更時表（payroll_times）**，唔係行位表。

核心：
- 揀 form：更碼 V*/Lecole* → VCA form；其餘 → 其他 form。
- 時間：更時表按「適用日」揀行（先睇公眾假期，否則星期幾；同碼多行揀優先序最細），
  再俾加班表按日期 override。同 Google Calendar 返工 event 一致嘅算法（但呢個識睇適用日）。
- 一日兩個 action：開工（填開工時間、收工留空）、收工（開工留空、填收工時間），各自獨立提交。
- 交法：預設出預填連結（手機一 tap → 自己撳提交）；可選全自動 POST（auto_send）。
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote_plus

from meal_planner.google_calendar_sync import _normal_time, _roster_cell_texts
from meal_planner.maintenance_db import load_sheet_rows
from meal_planner.roster import code_for_date, roster_for_month
from meal_planner.schedule_grid import (
    grid_row_matches_roster,
    load_overtime_overrides_from_rows,
    _to_date,
)
from meal_planner.settings import AppSettings, get_settings

STAFF_NUMBER = "SAPP1801"

# Mon=0 .. Sun=6 → 更時表「適用日」用嘅星期字。
_WEEKDAY_CHAR = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}


@dataclass(frozen=True)
class FormDef:
    key: str
    form_id: str
    entry_staff: str
    entry_post: str
    entry_date: str
    entry_start: str
    entry_end: str


# 兩條 form 嘅 entry ID（由 FB_PUBLIC_LOAD_DATA_ 抽出，實測預填成功）。
FORMS: dict[str, FormDef] = {
    "vca": FormDef(
        key="vca",
        form_id="1FAIpQLScGe1cY_IyPDZN36WoStc8qdMpCFXxrdY3JkixwC40MNG_FdA",
        entry_staff="entry.1878309037",
        entry_post="entry.1418219702",
        entry_date="entry.1854192389",
        entry_start="entry.1680978220",
        entry_end="entry.512352697",
    ),
    "other": FormDef(
        key="other",
        form_id="1FAIpQLSfhFP9FctJE1JVh6Firf5Z1f4atfaPupwyT16aT0IG9y2mGGQ",
        entry_staff="entry.1153045476",
        entry_post="entry.1691801130",
        entry_date="entry.925214547",
        entry_start="entry.1468530577",
        entry_end="entry.1870240075",
    ),
}

# 更碼 → Post 崗位（用戶 15/07/2026 確認）。決定用邊條 form 亦睇 key 屬邊個 form。
POST_MAPPING: dict[str, tuple[str, str]] = {
    # key: 更碼 -> (form_key, Post option text)
    "Lecole": ("vca", "L'ECOLE 珠寶學院"),
    "Lecole Event": ("vca", "L'ECOLE-event 珠寶學院"),
    "VCRA": ("vca", "V-CR/A 廣東道"),
    "VCRB": ("vca", "V-CR/B 廣東道"),
    "VLG": ("vca", "V-LG 利園"),
    "VOC": ("vca", "V-OC 海港"),
    "VPP": ("vca", "V-PP 金鐘太古廣場"),
    "EleA": ("other", "ELEA - Chanel  圓方"),
    "EleB": ("other", "ELEB - Chanel 圓方"),
    "EleC1": ("other", "ELEC - Chanel  圓方"),
    "EleC2": ("other", "ELEC - Chanel  圓方"),
    "EleD": ("other", "ELED - Chanel  圓方"),
    "EleM": ("other", "ELEM - Chanel  圓方"),
    "IFCA1": ("other", "A1 - IFC 時裝"),
    "IFCA2": ("other", "A2 - IFC 時裝"),
    "IFCB1": ("other", "B1 - IFC 時裝"),
    "IFCB2": ("other", "B2 - IFC 時裝"),
    "IFCFJ1": ("other", "FJ-1 - IFC 珠寶"),
    "IFCFJ2": ("other", "FJ-2 - IFC 珠寶"),
    "IFCM1": ("other", "M1 - IFC 飯更"),
    "IFCM2": ("other", "M2 - IFC ＆ OES 飯更"),
    "IFCS1": ("other", "S1 - IFC 鞋店"),
    "IFCS2": ("other", "S2 - IFC 鞋店"),
    "OES1": ("other", "OES-1- 交易廣場"),
    "OES2": ("other", "OES-2 - 交易廣場"),
    "PenA": ("other", "PENA - 半島時裝"),
    "PenB": ("other", "PENB - 半島時裝"),
    "PenBB": ("other", "PENB - 半島時裝"),
    "PenBM": ("other", "PENB - 半島時裝"),
    "PenC": ("other", "PENC - 半島時裝"),
    "PenC頂位": ("other", "PENC - 半島時裝"),
    "PenFJ": ("other", "PEN-FJ - 半島珠寶"),
    "PenM": ("other", "PENM -  半島時裝"),
    "TSA": ("other", "TSA - Chanel 時代"),
    "TSB": ("other", "TSB - Chanel 時代"),
    "TSM": ("other", "TSM - Chanel 時代"),
}


_DB_LOCK = threading.Lock()
GRACE_MINUTES = 15


def _connect(settings: AppSettings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.database_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS onoffduty_log ("
        " date_iso TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " time_text TEXT NOT NULL DEFAULT '',"
        " source TEXT NOT NULL DEFAULT '',"
        " recorded_at TEXT NOT NULL,"
        " PRIMARY KEY (date_iso, kind))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS onoffduty_config ("
        " config_key TEXT PRIMARY KEY,"
        " value_json TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    try:
        conn.execute("ALTER TABLE onoffduty_log ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 已有 detail 欄
    return conn


def load_onoff_config(settings: AppSettings) -> dict[str, Any]:
    import json

    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute("SELECT config_key, value_json FROM onoffduty_config").fetchall()
        finally:
            conn.close()
    stored: dict[str, Any] = {}
    for key, value_json in rows:
        try:
            stored[key] = json.loads(value_json)
        except ValueError:
            continue
    auto_send = stored.get("auto_send")
    return {"auto_send": bool(auto_send) if auto_send is not None else False}


def save_onoff_config(settings: AppSettings, patch: dict[str, Any]) -> dict[str, Any]:
    import json
    from zoneinfo import ZoneInfo

    current = load_onoff_config(settings)
    if "auto_send" in patch and patch["auto_send"] is not None:
        current["auto_send"] = bool(patch["auto_send"])
    now_iso = datetime.now(ZoneInfo(settings.dates.timezone)).isoformat()
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "INSERT INTO onoffduty_config (config_key, value_json, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(config_key) DO UPDATE SET value_json = excluded.value_json,"
                " updated_at = excluded.updated_at",
                ("auto_send", json.dumps(current["auto_send"]), now_iso),
            )
            conn.commit()
        finally:
            conn.close()
    return current


def record_onoff_log(
    settings: AppSettings,
    biz_date: date,
    kind: str,
    status: str,
    *,
    time_text: str = "",
    source: str = "web",
    detail: str = "",
) -> None:
    """記低邊日邊個 action（start/end）做咗咩（opened/sent/failed/missed）。同一 (日, action) 最新覆蓋。"""
    from zoneinfo import ZoneInfo

    now_iso = datetime.now(ZoneInfo(settings.dates.timezone)).isoformat()
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "INSERT INTO onoffduty_log (date_iso, kind, status, time_text, source, recorded_at, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(date_iso, kind) DO UPDATE SET status = excluded.status,"
                " time_text = excluded.time_text, source = excluded.source,"
                " recorded_at = excluded.recorded_at, detail = excluded.detail",
                (biz_date.isoformat(), kind, status, time_text, source, now_iso, detail),
            )
            conn.commit()
        finally:
            conn.close()


def load_onoff_log(settings: AppSettings, biz_date: date) -> dict[str, dict[str, Any]]:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute(
                "SELECT kind, status, time_text, source, recorded_at, detail"
                " FROM onoffduty_log WHERE date_iso = ?",
                (biz_date.isoformat(),),
            ).fetchall()
        finally:
            conn.close()
    return {
        kind: {
            "status": status,
            "time_text": time_text,
            "source": source,
            "recorded_at": recorded_at,
            "detail": detail,
        }
        for kind, status, time_text, source, recorded_at, detail in rows
    }


def _holiday_dates(settings: AppSettings) -> set[date]:
    payload = load_sheet_rows("public_holidays", settings)
    rows = payload.get("rows") or [] if isinstance(payload, dict) else []
    out: set[date] = set()
    for row in rows[1:]:
        if not isinstance(row, list) or not row:
            continue
        d = _to_date(row[0])
        if d is not None:
            out.add(d)
    return out


def _applicable_token(biz_date: date, holidays: set[date]) -> tuple[bool, str]:
    """回傳 (係咪公眾假期, 今日星期字)。"""
    is_holiday = biz_date in holidays
    return is_holiday, _WEEKDAY_CHAR[biz_date.weekday()]


def resolve_shift_time(
    payroll_rows: list[list[Any]],
    roster_code: str,
    biz_date: date,
    holidays: set[date],
    overtime_by_date: dict[date, tuple[time | None, time | None]],
) -> tuple[time | None, time | None]:
    """更時表按適用日揀開工/收工，再套加班表 override。攞唔到回 (None, None)。"""
    is_holiday, weekday_char = _applicable_token(biz_date, holidays)
    cands: list[tuple[time, time, str, float]] = []
    for row in (payroll_rows or [])[1:]:
        if not isinstance(row, list) or not row:
            continue
        code = str(row[0] or "").strip()
        if not grid_row_matches_roster(code, roster_code):
            continue
        start = _normal_time(row[1] if len(row) > 1 else None)
        end = _normal_time(row[2] if len(row) > 2 else None)
        if start is None or end is None:
            continue
        applies_day = str(row[3] or "").strip() if len(row) > 3 else ""
        try:
            priority = float(row[4]) if len(row) > 4 and str(row[4]).strip() else 99.0
        except (TypeError, ValueError):
            priority = 99.0
        cands.append((start, end, applies_day, priority))

    if not cands:
        return None, None

    def applies(applies_day: str) -> bool:
        if applies_day in ("", "每日"):
            return True
        if is_holiday:
            return applies_day == "公眾假期"
        return applies_day != "公眾假期" and weekday_char in applies_day

    matched = [c for c in cands if applies(c[2])]
    if not matched:
        # 冇啱今日適用日嘅行（例：假期但該碼冇公眾假期行）→ 退返每日行，
        # 再唔係就用晒所有行（單行碼）由優先序決定。
        matched = [c for c in cands if c[2] in ("", "每日")] or cands

    start, end, _, _ = min(matched, key=lambda c: c[3])
    ot_start, ot_end = overtime_by_date.get(biz_date, (None, None))
    return (ot_start or start, ot_end or end)


def _fmt_mmdd(d: date) -> str:
    return f"{d.month}/{d.day}"


def build_prefill_url(
    form: FormDef,
    post: str,
    biz_date: date,
    *,
    start: time | None,
    end: time | None,
) -> str:
    """砌 Google Form 預填連結。start/end 有邊個就填邊個（另一個留空）。"""
    params = [
        "usp=pp_url",
        f"{form.entry_staff}={quote_plus(STAFF_NUMBER)}",
        f"{form.entry_post}={quote_plus(post)}",
        f"{form.entry_date}_month={biz_date.month}",
        f"{form.entry_date}_day={biz_date.day}",
    ]
    if start is not None:
        params.append(f"{form.entry_start}_hour={start.hour}")
        params.append(f"{form.entry_start}_minute={start.minute}")
    if end is not None:
        params.append(f"{form.entry_end}_hour={end.hour}")
        params.append(f"{form.entry_end}_minute={end.minute}")
    return f"https://docs.google.com/forms/d/e/{form.form_id}/viewform?" + "&".join(params)


def clear_onoff_log_entry(settings: AppSettings, biz_date: date, kind: str) -> None:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "DELETE FROM onoffduty_log WHERE date_iso = ? AND kind = ?",
                (biz_date.isoformat(), kind),
            )
            conn.commit()
        finally:
            conn.close()


def set_time_override(
    settings: AppSettings,
    biz_date: date,
    *,
    start: str | None = None,
    end: str | None = None,
    note: str | None = None,
) -> None:
    """現場改開工/收工：直接 upsert 入加班表（權威來源）——報更、計糧、日曆、餐單全部跟住變。

    start/end：None=唔郁；""=清走該格（兩格都空成行刪走，還原跟更時表）；"21:30"/"2130"=設定。
    改完如果該格原本標咗 missed 而新時間重新趕得切，會清返個 log 俾 scheduler 重新處理。
    """
    from meal_planner.duty_report import _slot_datetime, normalize_hhmm
    from meal_planner.maintenance_db import save_sheet_rows
    from zoneinfo import ZoneInfo

    payload = load_sheet_rows("overtime", settings)
    rows = [list(r) if isinstance(r, list) else [] for r in (payload.get("rows") or [])]
    if not rows:
        rows = [["日期", "開工", "收工", "備註"]]
    header = [str(v or "").strip() for v in rows[0]]
    if "日期" not in header or "開工" not in header or "收工" not in header:
        raise ValueError("加班表欄位唔齊（要有 日期/開工/收工）")
    c_date, c_start, c_end = header.index("日期"), header.index("開工"), header.index("收工")
    c_note = header.index("備註") if "備註" in header else None

    def norm(text: str | None) -> str | None:
        if text is None:
            return None
        token = str(text).strip()
        if not token:
            return ""
        value = normalize_hhmm(token)
        if not value:
            raise ValueError(f"睇唔明個時間：{text}（可以打 21:30 / 2130）")
        return value.replace(":", "")  # 跟加班表現有 compact 格式

    start_value, end_value = norm(start), norm(end)

    target: list[Any] | None = None
    for row in rows[1:]:
        if c_date < len(row) and _to_date(row[c_date]) == biz_date:
            target = row
            break
    if target is None:
        width = max(len(header), c_start + 1, c_end + 1, (c_note + 1) if c_note is not None else 0)
        target = ["" for _ in range(width)]
        target[c_date] = biz_date.isoformat()
        rows.append(target)

    def ensure(row: list[Any], idx: int) -> None:
        while len(row) <= idx:
            row.append("")

    ensure(target, max(c_start, c_end))
    if start_value is not None:
        target[c_start] = start_value
    if end_value is not None:
        target[c_end] = end_value
    if note is not None and str(note).strip() and c_note is not None:
        ensure(target, c_note)
        target[c_note] = str(note).strip()

    if not str(target[c_start] or "").strip() and not str(target[c_end] or "").strip():
        rows = [rows[0]] + [r for r in rows[1:] if r is not target]
    save_sheet_rows("overtime", rows, settings)

    # missed 重新武裝：新時間仲趕得切（未過 grace）就清 log，俾 scheduler／狀態重新計。
    tz = ZoneInfo(settings.dates.timezone)
    now = datetime.now(tz)
    plan = build_day_plan(settings, biz_date=biz_date)
    for action in plan.get("actions") or []:
        if action.get("status") != "missed" or not action.get("time"):
            continue
        slot_dt = _slot_datetime(biz_date, str(action["time"]), tz)
        if now < slot_dt + timedelta(minutes=GRACE_MINUTES):
            clear_onoff_log_entry(settings, biz_date, str(action["kind"]))


def submit_form(
    form: FormDef,
    post: str,
    biz_date: date,
    *,
    start: time | None,
    end: time | None,
    timeout_seconds: float = 20.0,
) -> None:
    """直接 POST 去 Google Form formResponse（唔使登入）。start/end 有邊個交邊個。"""
    from urllib import parse, request as urlrequest

    data: dict[str, str] = {
        form.entry_staff: STAFF_NUMBER,
        form.entry_post: post,
        f"{form.entry_date}_month": str(biz_date.month),
        f"{form.entry_date}_day": str(biz_date.day),
    }
    if start is not None:
        data[f"{form.entry_start}_hour"] = str(start.hour)
        data[f"{form.entry_start}_minute"] = str(start.minute)
    if end is not None:
        data[f"{form.entry_end}_hour"] = str(end.hour)
        data[f"{form.entry_end}_minute"] = str(end.minute)
    body = parse.urlencode(data).encode("utf-8")
    url = f"https://docs.google.com/forms/d/e/{form.form_id}/formResponse"
    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
        if resp.status != 200:
            raise RuntimeError(f"formResponse HTTP {resp.status}")


def _minutes_30h(hhmm: str) -> int:
    """'HH:MM' → 分鐘（30 小時制：00:00–05:59 當 24:00–29:59）。"""
    hour, minute = hhmm.split(":", 1)
    value = int(hour) * 60 + int(minute)
    return value + 1440 if int(hour) < 6 else value


def _round_to_5min(value: datetime) -> time:
    """報更時間以 5 分鐘為單位四捨五入（:32→:30、:33→:35；小時進位照計）。"""
    total = value.hour * 60 + value.minute
    rounded = ((total + 2) // 5) * 5
    return time((rounded // 60) % 24, rounded % 60)


# 寫加班表條件（兩個都要中）：
# ① 超出更時表窗口——早過標準開工 或 遲過標準收工（唔理超幾多分鐘）；
# ② 總工時 > 10.25 小時。
OVERTIME_MIN_TOTAL_MINUTES = int(10.25 * 60)  # 615


def _find_report_off_slot(settings: AppSettings) -> dict[str, Any] | None:
    """今日 ReportNormal（報平安更）slots 入面，內容含「報收工」嘅最後一個。"""
    from meal_planner.duty_report import build_plan as build_report_normal_plan

    plan = build_report_normal_plan(settings)
    slots = [s for s in plan.get("slots") or [] if "報收工" in str(s.get("content") or "")]
    return slots[-1] if slots else None


def late_off_hold(settings: AppSettings, hold: bool) -> dict[str, Any]:
    """遲收工 hold：一個掣兩邊——OnOffDuty end 唔自動交唔標 missed；
    ReportNormal 嘅「報收工」slot skip 埋（唔會夠鐘自動出 WhatsApp）。"""
    from zoneinfo import ZoneInfo

    from meal_planner.duty_report import apply_override, business_date

    now = datetime.now(ZoneInfo(settings.dates.timezone))
    biz_date = business_date(now)
    plan = build_day_plan(settings, biz_date=biz_date)
    end_action = next((a for a in plan.get("actions") or [] if a.get("kind") == "end"), None)
    if end_action is None:
        raise ValueError("今日冇報收工")
    if hold:
        if end_action.get("status") == "sent":
            raise ValueError("報收工已經交咗，唔使 hold")
        record_onoff_log(
            settings, biz_date, "end", "hold",
            time_text=str(end_action.get("time") or ""), source="lateoff",
            detail="waiting real off-duty",
        )
    elif end_action.get("status") == "hold":
        clear_onoff_log_entry(settings, biz_date, "end")

    slot = _find_report_off_slot(settings)
    if slot is not None and slot.get("status") not in {"sent"}:
        apply_override(
            settings,
            slot_patch={"id": slot["id"], "skip": hold},
            source="onoffduty-lateoff",
            biz_date=biz_date,
        )
    return build_day_plan(settings, biz_date=biz_date)


def late_off_send_now(settings: AppSettings, *, note: str = "") -> dict[str, Any]:
    """真收工齊發：用「而家」做實際收工時間——
    1) 遲 ≥15 分鐘先寫加班表（否則唔算 OT，加班表唔記）；
    2) 報收工 form 即交（實際時間）；
    3) ReportNormal「報收工」slot 即發 WhatsApp。"""
    from zoneinfo import ZoneInfo

    from meal_planner.duty_report import business_date, send_slot

    tz = ZoneInfo(settings.dates.timezone)
    now = datetime.now(tz)
    biz_date = business_date(now)
    plan = build_day_plan(settings, biz_date=biz_date)
    end_action = next((a for a in plan.get("actions") or [] if a.get("kind") == "end"), None)
    if end_action is None or not plan.get("form") or not plan.get("post"):
        raise ValueError("今日冇報收工／未有 Post 對照")
    if end_action.get("status") == "sent":
        raise ValueError("報收工已經交咗")

    # 實際收工時間：5 分鐘為單位四捨五入（:32→:30、:33→:35）。
    actual_time = _round_to_5min(now)
    actual_text = actual_time.strftime("%H:%M")

    # 寫加班表條件（兩個都要中）：
    # 1) 超出更時表窗口：實際開工早過標準開工 或 實際收工遲過標準收工（唔理超幾多分鐘）；
    # 2) 總工時（實際開工→實際收工）> 10.25 小時。實際開工=plan start（已含加班表 override）。
    payroll_rows = load_sheet_rows("payroll_times", settings).get("rows") or []
    holidays = _holiday_dates(settings)
    std_start, std_end = resolve_shift_time(payroll_rows, plan["roster_code"], biz_date, holidays, {})
    overtime_written = False
    start_text = str(plan.get("start") or "")
    if std_start is not None and std_end is not None and start_text:
        early_start = _minutes_30h(start_text) < _minutes_30h(std_start.strftime("%H:%M"))
        late_end = _minutes_30h(actual_text) > _minutes_30h(std_end.strftime("%H:%M"))
        total_minutes = _minutes_30h(actual_text) - _minutes_30h(start_text)
        if (early_start or late_end) and total_minutes > OVERTIME_MIN_TOTAL_MINUTES:
            set_time_override(settings, biz_date, end=actual_text, note=note or "現場真收工")
            overtime_written = True

    form = FORMS[str(plan["form"])]
    submit_form(form, str(plan["post"]), biz_date, start=None, end=actual_time)
    record_onoff_log(
        settings, biz_date, "end", "sent",
        time_text=actual_text, source="lateoff",
        detail="real off-duty" + (" +OT" if overtime_written else ""),
    )

    whatsapp = "no slot"
    slot = _find_report_off_slot(settings)
    if slot is not None:
        if slot.get("status") == "sent":
            whatsapp = "already sent"
        else:
            try:
                send_slot(settings, str(slot["id"]), manual=True, source="onoffduty-lateoff")
                whatsapp = "sent"
            except Exception as e:  # noqa: BLE001 - form 交咗就唔好冧，WhatsApp 可以去 ReportNormal 度 retry
                whatsapp = f"failed: {e}"

    result_plan = build_day_plan(settings, biz_date=biz_date)
    result_plan["lateoff_result"] = {
        "actual": actual_text,
        "overtime_written": overtime_written,
        "whatsapp": whatsapp,
    }
    return result_plan


def process_due_actions(settings: AppSettings | None = None) -> None:
    """scheduler tick：auto_send 開先自動交；過咗 grace 未交標 missed（只限今日）。

    有「opened」記錄嗰個 action 唔會自動交——當你已經自己開 form 交咗，防止交兩次。
    """
    from zoneinfo import ZoneInfo

    from meal_planner.duty_report import _slot_datetime, business_date

    settings = settings or get_settings()
    tz = ZoneInfo(settings.dates.timezone)
    now = datetime.now(tz)
    biz_date = business_date(now)
    plan = build_day_plan(settings, biz_date=biz_date)
    actions = plan.get("actions") or []
    if not actions:
        return
    config = load_onoff_config(settings)
    log = load_onoff_log(settings, biz_date)
    form_key = plan.get("form")
    post = str(plan.get("post") or "")
    form = FORMS.get(str(form_key)) if form_key else None

    for action in actions:
        kind = str(action.get("kind") or "")
        time_text = str(action.get("time") or "")
        if not kind or not time_text:
            continue
        entry = log.get(kind) or {}
        status = str(entry.get("status") or "")
        if status in {"sent", "opened", "missed", "hold"}:
            continue  # 已交／已自己開 form／已標 missed／hold 緊等真收工
        slot_dt = _slot_datetime(biz_date, time_text, tz)
        if now < slot_dt:
            continue
        if now >= slot_dt + timedelta(minutes=GRACE_MINUTES):
            record_onoff_log(
                settings, biz_date, kind, "missed",
                time_text=time_text, source="scheduler",
                detail=f"passed grace window ({GRACE_MINUTES} min)",
            )
            continue
        if not config["auto_send"] or form is None or not post:
            continue
        if status == "failed":
            # 之前失敗過：等最少 60 秒先重試，唔好每 tick 狂試。
            try:
                last = datetime.fromisoformat(str(entry.get("recorded_at") or ""))
                if (now - last).total_seconds() < 60:
                    continue
            except ValueError:
                pass
        hhmm = time_text.split(":")
        value = time(int(hhmm[0]), int(hhmm[1]))
        try:
            submit_form(
                form, post, biz_date,
                start=value if kind == "start" else None,
                end=value if kind == "end" else None,
            )
        except Exception as e:  # noqa: BLE001 - 任何錯都記 failed，等下一 tick 重試
            record_onoff_log(
                settings, biz_date, kind, "failed",
                time_text=time_text, source="scheduler", detail=str(e),
            )
            continue
        record_onoff_log(settings, biz_date, kind, "sent", time_text=time_text, source="scheduler")


def roster_code_for(settings: AppSettings, biz_date: date) -> str:
    roster_payload = load_sheet_rows("roster", settings)
    rows = roster_payload.get("rows") or [] if isinstance(roster_payload, dict) else []
    roster_map = roster_for_month(_roster_cell_texts(rows))
    month_map = roster_map.get((biz_date.year, biz_date.month))
    return str(code_for_date(month_map, biz_date) or "") if month_map else ""


def build_day_plan(settings: AppSettings | None = None, *, biz_date: date | None = None) -> dict[str, Any]:
    """指定日（預設今日 30 小時制）嘅報開工／報收工計劃 + 兩條預填連結。"""
    from meal_planner.duty_report import business_date  # 共用 30 小時制

    settings = settings or get_settings()
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.dates.timezone))
    today = business_date(now)
    biz_date = biz_date or today

    roster_code = roster_code_for(settings, biz_date)
    result: dict[str, Any] = {
        "date_iso": biz_date.isoformat(),
        "today_iso": today.isoformat(),
        "relation": "today" if biz_date == today else ("past" if biz_date < today else "future"),
        "staff_number": STAFF_NUMBER,
        "roster_code": roster_code,
        "actions": [],
        "note": "",
    }
    if not roster_code:
        result["note"] = "當日冇更碼"
        return result

    mapping = POST_MAPPING.get(roster_code)
    if mapping is None:
        result["note"] = f"更碼 {roster_code} 未有 Post 對照（未 map 或非返工更）"
        return result
    form_key, post = mapping
    form = FORMS[form_key]

    payroll_rows = (load_sheet_rows("payroll_times", settings).get("rows") or [])
    holidays = _holiday_dates(settings)
    overtime_rows = load_sheet_rows("overtime", settings).get("rows") or []
    overtime_by_date = load_overtime_overrides_from_rows(overtime_rows)
    start, end = resolve_shift_time(payroll_rows, roster_code, biz_date, holidays, overtime_by_date)

    ot_start, ot_end = overtime_by_date.get(biz_date, (None, None))
    result["form"] = form.key
    result["post"] = post
    result["start"] = start.strftime("%H:%M") if start else ""
    result["end"] = end.strftime("%H:%M") if end else ""
    result["start_override"] = ot_start is not None
    result["end_override"] = ot_end is not None
    if start is None and end is None:
        result["note"] = f"更碼 {roster_code} 喺更時表搵唔到時間"
        return result

    log = load_onoff_log(settings, biz_date)
    result["actions"] = [
        {
            "kind": "start",
            "label": "On Duty",
            "time": start.strftime("%H:%M") if start else "",
            "url": build_prefill_url(form, post, biz_date, start=start, end=None),
        },
        {
            "kind": "end",
            "label": "Off Duty",
            "time": end.strftime("%H:%M") if end else "",
            "url": build_prefill_url(form, post, biz_date, start=None, end=end),
        },
    ]
    for action in result["actions"]:
        entry = log.get(action["kind"]) or {}
        action["status"] = str(entry.get("status") or "")
        action["logged_at"] = str(entry.get("recorded_at") or "")
        action["log_source"] = str(entry.get("source") or "")
        action["detail"] = str(entry.get("detail") or "")
    result["auto_send"] = load_onoff_config(settings)["auto_send"]
    return result
