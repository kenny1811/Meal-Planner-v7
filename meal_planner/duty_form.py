"""OnOff_Duty（報開工／報收工）：由更碼推導今日 Google Form 打卡計劃 + 砌預填連結。

同 Report_Normal（報平安更 WhatsApp，duty_report.py）係兩件事：
- Report_Normal → 行位表「報平安更」rows。
- OnOff_Duty → 呢度，行位表「報開工／報收工」rows。

核心：
- 揀 form：更碼 V*/Lecole* → VCA form；其餘 → 其他 form。
- 時間：加班表 override＞**行位表**「報開工／報收工」行（當日實際時間軸）；
  更時表（計糧官方時間）唔會出現喺 Form，淨係做遲收工寫加班表嘅標準窗口。
  hold / send now 先會再改變（send now 用「而家」做實際開工／收工）。
- 一日兩個 action：開工（填開工時間、收工留空）、收工（開工留空、填收工時間），各自獨立提交。
  兩個 action 都有 hold / send now：打風唔知幾點開工，就 hold 住開工，真開工先撳 send now。
- 交法：夠鐘就自動 POST 去 Google Form，冇半自動模式——開唔開過預填連結都唔影響。
  預填連結照出（想自己開嚟睇／改都得），開過只會喺 history 留一行記錄。
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote_plus

from meal_planner.duty_common import (
    GRACE_DETAIL,
    GRACE_MINUTES,
    RETRY_SECONDS,
    retry_backoff_active,
)
from meal_planner.duty_report import apply_override, build_plan as build_report_normal_plan, send_slot
from meal_planner.duty_scheduler import notify_change
from meal_planner.maintenance_db import load_sheet_rows, roster_post_for_code, save_sheet_rows
from meal_planner.roster import code_for_date, roster_map_from_sheet_rows
from meal_planner.roster_codes import form_key_for_code
from meal_planner.schedule_grid import (
    load_overtime_overrides_from_rows,
    load_schedule_rows_from_rows,
    report_start_end,
    rows_for_roster,
    _to_date,
)
from meal_planner.settings import AppSettings, get_settings
from meal_planner.shift_time import holiday_dates_from_rows, resolve_shift_time
from meal_planner.timeparse import (
    business_date,
    minutes_30h as _minutes_30h,
    hhmm30,
    normalize_hhmm,
    slot_datetime as _slot_datetime,
)

STAFF_NUMBER = "SAPP1801"


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

_DB_LOCK = threading.Lock()


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
    # onoffduty_log 一日一個 action 得一行（＝而家個狀態），改時間會蓋走上一個。
    # history 係 append-only：交過、hold 過、重新武裝過，全部留底，永遠唔 delete。
    # 「今朝到底交咗未」呢類問題就係靠佢答。
    conn.execute(
        "CREATE TABLE IF NOT EXISTS onoffduty_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " date_iso TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " time_text TEXT NOT NULL DEFAULT '',"
        " source TEXT NOT NULL DEFAULT '',"
        " detail TEXT NOT NULL DEFAULT '',"
        " recorded_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_onoffduty_history_day"
        " ON onoffduty_history (date_iso, kind, id)"
    )
    try:
        conn.execute("ALTER TABLE onoffduty_log ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 已有 detail 欄
    return conn


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
    """記低邊日邊個 action（start/end）做咗咩（sent/failed/missed/hold…）。

    onoffduty_log 同一 (日, action) 最新覆蓋（＝而家個狀態）；同時 append 一行落
    onoffduty_history，永遠唔會俾之後嘅改動洗走。
    """
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
            _append_history(conn, biz_date, kind, status, time_text, source, detail, now_iso)
            conn.commit()
        finally:
            conn.close()
    notify_change()


def _append_history(
    conn: sqlite3.Connection,
    biz_date: date,
    kind: str,
    status: str,
    time_text: str,
    source: str,
    detail: str,
    now_iso: str,
) -> None:
    conn.execute(
        "INSERT INTO onoffduty_history"
        " (date_iso, kind, status, time_text, source, detail, recorded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (biz_date.isoformat(), kind, status, time_text, source, detail, now_iso),
    )


def record_onoff_open(
    settings: AppSettings,
    biz_date: date,
    kind: str,
    *,
    time_text: str = "",
    source: str = "web",
) -> None:
    """開過預填連結：淨係 append 一行 history 做記錄。

    **唔會**掂 onoffduty_log 個狀態——夠鐘照自動交，個卡亦唔會扮咗「已交」。
    """
    from zoneinfo import ZoneInfo

    now_iso = datetime.now(ZoneInfo(settings.dates.timezone)).isoformat()
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            _append_history(conn, biz_date, kind, "opened", time_text, source, "", now_iso)
            conn.commit()
        finally:
            conn.close()


def load_onoff_history(settings: AppSettings, biz_date: date) -> dict[str, list[dict[str, Any]]]:
    """當日每個 action 嘅完整經過（由舊到新）。append-only，唔會少過真實發生過嘅嘢。"""
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute(
                "SELECT kind, status, time_text, source, detail, recorded_at"
                " FROM onoffduty_history WHERE date_iso = ? ORDER BY id",
                (biz_date.isoformat(),),
            ).fetchall()
        finally:
            conn.close()
    out: dict[str, list[dict[str, Any]]] = {}
    for kind, status, time_text, source, detail, recorded_at in rows:
        out.setdefault(kind, []).append(
            {
                "status": status,
                "time_text": time_text,
                "source": source,
                "detail": detail,
                "recorded_at": recorded_at,
            }
        )
    return out


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
    return holiday_dates_from_rows(rows)


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


def clear_onoff_log_entry(
    settings: AppSettings,
    biz_date: date,
    kind: str,
    *,
    status: str = "cleared",
    time_text: str = "",
    source: str = "web",
    detail: str = "",
) -> None:
    """清走「而家個狀態」（重新武裝／resume），但 history 一定會 append 一行講明點解。

    交過就係交過 —— 之前嗰個 sent 永遠留喺 history，唔會因為改時間而消失。
    """
    from zoneinfo import ZoneInfo

    now_iso = datetime.now(ZoneInfo(settings.dates.timezone)).isoformat()
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "DELETE FROM onoffduty_log WHERE date_iso = ? AND kind = ?",
                (biz_date.isoformat(), kind),
            )
            _append_history(conn, biz_date, kind, status, time_text, source, detail, now_iso)
            conn.commit()
        finally:
            conn.close()
    notify_change()


def set_time_override(
    settings: AppSettings,
    biz_date: date,
    *,
    start: str | None = None,
    end: str | None = None,
    note: str | None = None,
    rearm: bool = True,
) -> None:
    """現場改開工/收工：直接 upsert 入加班表（權威來源）——報更、計糧、日曆、餐單全部跟住變。

    start/end：None=唔郁；""=清走該格（兩格都空成行刪走，還原跟更時表）；"21:30"/"2130"=設定。
    改完會重新武裝（見 _rearm_missed_actions）：新時間仲未到就當件事未發生，
    舊 log（missed／sent／hold…）清走，scheduler 照新時間再交。
    rearm=False：件事已經即場做咗（send now），唔使叫 scheduler 補做。
    """
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
    if rearm:
        _rearm_missed_actions(settings, biz_date)


def _rearm_missed_actions(settings: AppSettings, biz_date: date) -> None:
    """改完時間／更碼 = 重新武裝：件事改咗去一個仲未過（未過 grace）嘅時間，
    即係當佢**未發生**——清走舊 log，俾 scheduler 照新時間重新交。

    包括之前已經 sent 嗰啲（例如打風日 auto 早咗交、跟住現場改真開工時間），
    亦包括 hold（改到實際時間就當 resume，連 ReportNormal 對應 slot 一齊放返）。
    只郁時間真係變咗嘅 action——log 記低嗰個時間仲啱嘅就唔掂。
    """
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.dates.timezone)
    now = datetime.now(tz)
    log = load_onoff_log(settings, biz_date)
    plan = build_day_plan(settings, biz_date=biz_date)
    for action in plan.get("actions") or []:
        kind, time_text = str(action.get("kind") or ""), str(action.get("time") or "")
        entry = log.get(kind) or {}
        if not kind or not time_text or not entry:
            continue
        if str(entry.get("time_text") or "") == time_text:
            continue  # 呢個 action 個時間冇變過
        slot_dt = _slot_datetime(biz_date, time_text, tz)
        if now >= slot_dt + timedelta(minutes=GRACE_MINUTES):
            continue
        old_status = str(entry.get("status") or "")
        old_time = str(entry.get("time_text") or "") or "—"
        clear_onoff_log_entry(
            settings, biz_date, kind, status="rearmed",
            time_text=time_text, source="rearm",
            detail=f"時間 {old_time} → {time_text}（之前：{old_status or '冇記錄'}），照新時間重新等",
        )
        if old_status == "hold" and biz_date == business_date(now):
            slot = _find_report_slot(settings, kind)
            if slot is not None and slot.get("status") != "sent":
                apply_override(
                    settings,
                    slot_patch={"id": slot["id"], "skip": False},
                    source="onoffduty-holdsend",
                    biz_date=biz_date,
                )


def _replace_code_in_cell(cell_text: str, day: int, new_code: str) -> str | None:
    """更表單格 token 手術：只換指定日嘅更碼，其餘一 byte 不動。搵唔到該日回 None。

    掃法同 roster.parse_roster_line 一致（日 token = 1–31 純數字，更碼可含空格）。
    """
    import re as _re

    from meal_planner.roster import _MONTH_HEAD_RE

    if cell_text is None:
        return None
    text = str(cell_text)
    m = _MONTH_HEAD_RE.match(text.strip())
    if not m:
        return None
    tokens = [(t.start(), t.end(), t.group()) for t in _re.finditer(r"\S+", text)]
    # 跳過月份 head 佔用嘅 tokens（head 一定喺最前）。
    head_end = text.find(m.group(0)) + len(m.group(0))
    idx = 0
    while idx < len(tokens) and tokens[idx][0] < head_end:
        idx += 1

    def is_day_token(value: str) -> bool:
        return value.isdigit() and 1 <= int(value) <= 31

    while idx < len(tokens):
        d_tok = tokens[idx][2]
        if not is_day_token(d_tok):
            break
        idx += 1
        code_span: tuple[int, int] | None = None
        while idx < len(tokens) and not is_day_token(tokens[idx][2]):
            start_pos, end_pos, _ = tokens[idx]
            code_span = (code_span[0] if code_span else start_pos, end_pos)
            idx += 1
        if code_span is None:
            break
        if int(d_tok) == day:
            return text[: code_span[0]] + new_code + text[code_span[1] :]
    return None


def set_roster_code(settings: AppSettings, biz_date: date, code: str) -> None:
    """現場轉更：直接改更表（權威來源）——報開工/收工、報平安更、日曆、餐單全部跟住變。

    改完新更時間如果仲未到，會清返舊 log 俾 scheduler 照新時間重新交
    （同 set_time_override 一樣嘅重新武裝邏輯）。
    """
    from meal_planner.roster import parse_roster_line

    new_code = " ".join(str(code or "").split())
    if not new_code:
        raise ValueError("更碼唔可以留空")

    payload = load_sheet_rows("roster", settings)
    rows = [list(r) if isinstance(r, list) else [] for r in (payload.get("rows") or [])]
    replaced = False
    for row in rows:
        if not row or row[0] is None:
            continue
        rm = parse_roster_line(str(row[0]))
        if rm is None or (rm.year, rm.month) != (biz_date.year, biz_date.month):
            continue
        new_cell = _replace_code_in_cell(str(row[0]), biz_date.day, new_code)
        if new_cell is None:
            raise ValueError(f"更表 {rm.year}年{rm.month}月 行搵唔到 {biz_date.day} 日")
        row[0] = new_cell
        replaced = True
        break
    if not replaced:
        raise ValueError(f"更表搵唔到 {biz_date.year}年{biz_date.month}月")
    save_sheet_rows("roster", rows, settings)
    _rearm_missed_actions(settings, biz_date)


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


def _round_to_5min(value: datetime) -> time:
    """報更時間以 5 分鐘為單位四捨五入（:32→:30、:33→:35；小時進位照計）。"""
    total = value.hour * 60 + value.minute
    rounded = ((total + 2) // 5) * 5
    return time((rounded // 60) % 24, rounded % 60)


# 寫加班表條件（兩個都要中）：
# ① 超出更時表窗口——早過標準開工 或 遲過標準收工（唔理超幾多分鐘）；
# ② 總工時 > 10.25 小時。
OVERTIME_MIN_TOTAL_MINUTES = int(10.25 * 60)  # 615


ACTION_LABEL = {"start": "報開工", "end": "報收工"}


def _standard_shift_time(
    settings: AppSettings, roster_code: str, biz_date: date
) -> tuple[time | None, time | None]:
    """更時表（計糧官方時間）按適用日 resolve —— **唔套**加班表 override。"""
    payroll_rows = load_sheet_rows("payroll_times", settings).get("rows") or []
    return resolve_shift_time(payroll_rows, roster_code, biz_date, _holiday_dates(settings), {})


def pick_report_slot(slots: list[dict[str, Any]] | None, kind: str) -> dict[str, Any] | None:
    """ReportNormal slots 入面，內容含「報開工」／「報收工」嗰個。

    開工攞最早嗰個、收工攞最後嗰個（一日只會有一次真開工／真收工）。
    """
    keyword = ACTION_LABEL[kind]
    hits = [s for s in slots or [] if keyword in str(s.get("content") or "")]
    if not hits:
        return None
    return hits[0] if kind == "start" else hits[-1]


def _find_report_slot(settings: AppSettings, kind: str) -> dict[str, Any] | None:
    return pick_report_slot(build_report_normal_plan(settings).get("slots"), kind)


def _today_action(settings: AppSettings, kind: str) -> tuple[date, dict[str, Any], dict[str, Any]]:
    from zoneinfo import ZoneInfo

    if kind not in ACTION_LABEL:
        raise ValueError(f"唔認得嘅 action：{kind}")
    biz_date = business_date(datetime.now(ZoneInfo(settings.dates.timezone)))
    plan = build_day_plan(settings, biz_date=biz_date)
    action = next((a for a in plan.get("actions") or [] if a.get("kind") == kind), None)
    if action is None:
        raise ValueError(f"今日冇{ACTION_LABEL[kind]}")
    return biz_date, plan, action


def duty_hold(settings: AppSettings, kind: str, hold: bool) -> dict[str, Any]:
    """Hold／resume 一個 action：一個掣兩邊——OnOffDuty 嗰格唔自動交唔標 missed；
    ReportNormal 對應嘅「報開工／報收工」slot skip 埋（唔會夠鐘自動出 WhatsApp）。

    打風未定幾點開工、或者未走得（遲收工），就 hold 住，真發生嗰陣先撳 send now。
    """
    biz_date, _plan, action = _today_action(settings, kind)
    if hold:
        if action.get("status") == "sent":
            raise ValueError(f"{ACTION_LABEL[kind]}已經交咗，唔使 hold")
        record_onoff_log(
            settings, biz_date, kind, "hold",
            time_text=str(action.get("time") or ""), source="holdsend",
            detail=f"waiting real {'on' if kind == 'start' else 'off'}-duty",
        )
    elif action.get("status") == "hold":
        clear_onoff_log_entry(
            settings, biz_date, kind, status="resumed",
            time_text=str(action.get("time") or ""), source="holdsend",
            detail="放返 hold，照原定時間等",
        )

    slot = _find_report_slot(settings, kind)
    if slot is not None and slot.get("status") not in {"sent"}:
        apply_override(
            settings,
            slot_patch={"id": slot["id"], "skip": hold},
            source="onoffduty-holdsend",
            biz_date=biz_date,
        )
    return build_day_plan(settings, biz_date=biz_date)


def _needs_overtime_row(
    settings: AppSettings,
    biz_date: date,
    plan: dict[str, Any],
    kind: str,
    actual_text: str,
) -> bool:
    """Send now 之後寫唔寫加班表（權威實際時間）。淨係判斷，唔郁資料。

    - 開工：實際開工同預設（加班表 override＞更時表）唔同就寫——打風遲開工咁樣，
      報平安更 slots／餐單／日曆要跟住郁。
    - 收工：兩個條件都要中先寫——① 超出更時表窗口（實際開工早過標準開工 或
      實際收工遲過標準收工）；② 總工時 > 10.25 小時。唔算 OT 就唔好污染加班表。
    """
    if kind == "start":
        return actual_text != str(plan.get("start") or "")

    std_start, std_end = _standard_shift_time(settings, str(plan.get("roster_code") or ""), biz_date)
    start_text = str(plan.get("start") or "")
    if std_start is None or std_end is None or not start_text:
        return False
    early_start = _minutes_30h(start_text) < _minutes_30h(std_start.strftime("%H:%M"))
    late_end = _minutes_30h(actual_text) > _minutes_30h(std_end.strftime("%H:%M"))
    total_minutes = _minutes_30h(actual_text) - _minutes_30h(start_text)
    return (early_start or late_end) and total_minutes > OVERTIME_MIN_TOTAL_MINUTES


def duty_send_now(settings: AppSettings, kind: str, *, note: str = "") -> dict[str, Any]:
    """真開工／真收工齊發：用「而家」做實際時間。

    **呢個動作直接取代排程嗰次**，唔會叫醒 scheduler 幫手做——以前係寫加班表 →
    重新武裝（清走 hold）→ notify，結果 scheduler 即刻醒，同 send now 各自交一次，
    form 同 WhatsApp 都出咗雙份。而家次序係：

    1) 先交 form + 記 sent —— 由呢一刻起 scheduler 問 history 就知交咗，唔會再交；
    2) 之後先寫加班表（唔重新武裝：件事已經做完，唔使 scheduler 補做）；
    3) ReportNormal 對應 slot 由我哋自己發（hold 期間 slot 仲係 skip，scheduler 唔會插隊），
       發完先放返 skip。
    """
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.dates.timezone))
    biz_date, plan, action = _today_action(settings, kind)
    if not plan.get("form") or not plan.get("post"):
        raise ValueError("未有 Post 對照")
    if action.get("status") == "sent":
        raise ValueError(f"{ACTION_LABEL[kind]}已經交咗")

    # 實際時間：5 分鐘為單位四捨五入（:32→:30、:33→:35）。
    actual_time = _round_to_5min(now)
    actual_text = hhmm30(actual_time)
    overtime_written = _needs_overtime_row(settings, biz_date, plan, kind, actual_text)

    form = FORMS[str(plan["form"])]
    submit_form(
        form, str(plan["post"]), biz_date,
        start=actual_time if kind == "start" else None,
        end=actual_time if kind == "end" else None,
    )
    record_onoff_log(
        settings, biz_date, kind, "sent",
        time_text=actual_text, source="holdsend",
        detail=f"real {'on' if kind == 'start' else 'off'}-duty" + (" +OT" if overtime_written else ""),
    )
    if overtime_written:
        set_time_override(
            settings, biz_date,
            start=actual_text if kind == "start" else None,
            end=actual_text if kind == "end" else None,
            note=note or ("現場真開工" if kind == "start" else "現場真收工"),
            rearm=False,
        )

    whatsapp = "no slot"
    slot = _find_report_slot(settings, kind)
    if slot is not None:
        if slot.get("status") == "sent":
            whatsapp = "already sent"
        else:
            try:
                send_slot(settings, str(slot["id"]), manual=True, source="onoffduty-holdsend")
                whatsapp = "sent"
            except Exception as e:  # noqa: BLE001 - form 交咗就唔好冧，WhatsApp 可以去 ReportNormal 度 retry
                whatsapp = f"failed: {e}"
        if slot.get("skipped"):
            # hold 期間 skip 咗；發完先放返（呢刻已經 sent，scheduler 唔會再發一次）。
            apply_override(
                settings,
                slot_patch={"id": slot["id"], "skip": False},
                source="onoffduty-holdsend",
                biz_date=biz_date,
            )

    result_plan = build_day_plan(settings, biz_date=biz_date)
    result_plan["sendnow_result"] = {
        "kind": kind,
        "actual": actual_text,
        "overtime_written": overtime_written,
        "whatsapp": whatsapp,
    }
    return result_plan


def _logged(history_rows: list[dict[str, Any]], status: str, time_text: str) -> bool:
    """history 入面有冇「呢個時間」嘅呢個狀態（append-only，唔會俾之後嘅改動洗走）。

    睇 history 唔睇最新個 status：發送／missed 呢啲事實唔應該俾之後嘅改動蓋走。
    對埋時間：改咗開工時間（rearm）＝另一件事，舊時間發過唔算數。
    """
    return any(
        str(row.get("status") or "") == status and str(row.get("time_text") or "") == time_text
        for row in history_rows
    )


def _action_done(status: str, history_rows: list[dict[str, Any]], time_text: str) -> bool:
    """呢個 action 仲使唔使 scheduler 出手？

    - status sent／hold＝而家已經交咗／等緊真開工收工（send now 用「而家」個時間交，
      同排程時間唔同都當交咗——rearm 先會清走呢個狀態，嗰陣就真係要再交）；
    - 其餘問 history（append-only）：交過／標過 missed 就唔好因為之後嘅改動再做一次。
    開過預填連結唔會入 log，所以完全唔影響。
    """
    return (
        status in {"hold", "sent"}
        or _logged(history_rows, "sent", time_text)
        or _logged(history_rows, "missed", time_text)
    )


def process_due_actions(settings: AppSettings | None = None) -> datetime | None:
    """scheduler tick：夠鐘就自動交；過咗 grace 未交標 missed（只限今日）。

    冇半自動模式——開唔開過預填連結都唔影響，照交。
    回傳下一個會自動交嘅時刻（scheduler 瞓到啱啱嗰刻醒，準時交）；冇就 None。
    """
    from zoneinfo import ZoneInfo

    settings = settings or get_settings()
    tz = ZoneInfo(settings.dates.timezone)
    now = datetime.now(tz)
    biz_date = business_date(now)
    plan = build_day_plan(settings, biz_date=biz_date)
    actions = plan.get("actions") or []
    if not actions:
        return None
    log = load_onoff_log(settings, biz_date)
    history = load_onoff_history(settings, biz_date)
    form_key = plan.get("form")
    post = str(plan.get("post") or "")
    form = FORMS.get(str(form_key)) if form_key else None
    auto_ready = form is not None and bool(post)

    next_due: datetime | None = None
    due_seen = False
    for action in actions:
        kind = str(action.get("kind") or "")
        time_text = str(action.get("time") or "")  # 實際時間（加班表＞行位表報開工/報收工）
        if not kind or not time_text:
            continue
        entry = log.get(kind) or {}
        status = str(entry.get("status") or "")
        if _action_done(status, history.get(kind) or [], time_text):
            continue  # 已交／已標 missed／hold 緊等真開工收工
        slot_dt = _slot_datetime(biz_date, time_text, tz)
        if now < slot_dt:
            if auto_ready and (next_due is None or slot_dt < next_due):
                next_due = slot_dt
            continue
        if now >= slot_dt + timedelta(minutes=GRACE_MINUTES):
            record_onoff_log(
                settings, biz_date, kind, "missed",
                time_text=time_text, source="scheduler",
                detail=GRACE_DETAIL,
            )
            continue
        if not auto_ready:
            continue
        due_seen = True
        if status == "failed" and retry_backoff_active(entry.get("recorded_at"), now):
            continue  # 之前失敗過：等最少 RETRY_SECONDS 先重試，唔好每 tick 狂試
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
    if due_seen:
        # 到期但未完成（失敗/backoff）→ 最遲 RETRY_SECONDS 後再試一次。
        retry_at = now + timedelta(seconds=RETRY_SECONDS)
        next_due = retry_at if next_due is None else min(next_due, retry_at)
    return next_due


def roster_code_for(settings: AppSettings, biz_date: date) -> str:
    roster_payload = load_sheet_rows("roster", settings)
    rows = roster_payload.get("rows") or [] if isinstance(roster_payload, dict) else []
    roster_map = roster_map_from_sheet_rows(rows)
    month_map = roster_map.get((biz_date.year, biz_date.month))
    return str(code_for_date(month_map, biz_date) or "") if month_map else ""


def _time_from_hhmm30(text: str) -> time | None:
    """30 小時制 "25:30" → time(1, 30)；"21:50" → time(21, 50)。睇唔明回 None。"""
    parts = str(text or "").split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return time(int(parts[0]) % 24, int(parts[1]))


def build_day_plan(settings: AppSettings | None = None, *, biz_date: date | None = None) -> dict[str, Any]:
    """指定日（預設今日 30 小時制）嘅報開工／報收工計劃 + 兩條預填連結。"""

    settings = settings or get_settings()
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.dates.timezone))
    today = business_date(now)
    biz_date = biz_date or today

    roster_code = roster_code_for(settings, biz_date)
    code_posts = roster_post_for_code(settings)
    result: dict[str, Any] = {
        "date_iso": biz_date.isoformat(),
        "today_iso": today.isoformat(),
        "relation": "today" if biz_date == today else ("past" if biz_date < today else "future"),
        "staff_number": STAFF_NUMBER,
        "roster_code": roster_code,
        "known_codes": sorted(code_posts),
        "actions": [],
        "note": "",
    }
    if not roster_code:
        result["note"] = "當日冇更碼"
        return result

    post = code_posts.get(roster_code)
    if post is None:
        result["note"] = f"更碼 {roster_code} 未有 Post 對照（未 map 或非返工更）"
        return result
    form = FORMS[form_key_for_code(roster_code)]

    # 時間：加班表 override＞行位表「報開工／報收工」行（當日實際時間軸）。
    # Form 內容同自動發射都係呢個時間（hold / send now 先會再改變）。
    # 更時表（計糧官方時間）淨係用嚟做遲收工寫加班表嘅標準窗口，唔會出現喺 Form。
    grid_rows = load_schedule_rows_from_rows(load_sheet_rows("schedule_grid", settings).get("rows") or [])
    grid_start, grid_end = report_start_end(rows_for_roster(grid_rows, roster_code, biz_date), biz_date)
    std_start, std_end = _standard_shift_time(settings, roster_code, biz_date)
    overtime_rows = load_sheet_rows("overtime", settings).get("rows") or []
    ot_start, ot_end = load_overtime_overrides_from_rows(overtime_rows).get(biz_date, (None, None))
    start = ot_start if ot_start is not None else grid_start
    end = ot_end if ot_end is not None else grid_end

    result["form"] = form.key
    result["post"] = post
    result["start"] = hhmm30(start) if start else ""
    result["end"] = hhmm30(end) if end else ""
    result["std_start"] = hhmm30(std_start) if std_start else ""
    result["std_end"] = hhmm30(std_end) if std_end else ""
    result["start_override"] = ot_start is not None
    result["end_override"] = ot_end is not None
    if start is None and end is None:
        result["note"] = f"更碼 {roster_code} 喺行位表搵唔到「報開工/報收工」行（亦冇加班表 override）"
        return result

    log = load_onoff_log(settings, biz_date)
    history = load_onoff_history(settings, biz_date)
    result["actions"] = [
        {
            "kind": "start",
            "label": "On Duty",
            "time": hhmm30(start) if start else "",
            "url": build_prefill_url(form, post, biz_date, start=start, end=None),
        },
        {
            "kind": "end",
            "label": "Off Duty",
            "time": hhmm30(end) if end else "",
            "url": build_prefill_url(form, post, biz_date, start=None, end=end),
        },
    ]
    for action in result["actions"]:
        entry = log.get(action["kind"]) or {}
        action["status"] = str(entry.get("status") or "")
        action["logged_at"] = str(entry.get("recorded_at") or "")
        action["log_source"] = str(entry.get("source") or "")
        action["detail"] = str(entry.get("detail") or "")
        # Send now 用「而家」交咗＝呢個 action 就係喺嗰刻做咗，實際時間直接取代排程時間
        # （唔關加班表事——加班表淨係話俾其他嘢知當日個時間軸點變）。
        sent_text = str(entry.get("time_text") or "") if action["status"] == "sent" else ""
        sent_time = _time_from_hhmm30(sent_text) if sent_text else None
        if sent_time is not None:
            action["time"] = sent_text
            action["url"] = build_prefill_url(
                form, post, biz_date,
                start=sent_time if action["kind"] == "start" else None,
                end=sent_time if action["kind"] == "end" else None,
            )
        # 完整經過（append-only）：交過幾多次、hold 過、重新武裝過，全部見得到。
        action["history"] = history.get(action["kind"], [])
    return result
