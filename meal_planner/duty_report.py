"""Report_Normal（報平安更）：由行位表推導今日報更計劃，經 WhatsApp 發送。

核心原則：報更計劃係一層獨立 overlay，只影響報更，永不修改更表／Google Calendar
（計糧用返原本更表更碼）。

- 30 小時制：00:00–05:59 屬前一日（business date = now - 6h 之日期）。
- slot 來源：當日更碼喺行位表入面 內容 含「報平安更」嘅行；(日-四)/(五六) 標記按星期過濾。
  預設時間＝行位表 + 加班表 override（開工 override →「報開工」slot、收工 override →
  「報收工」slot），panel 改時間/skip/send now 再凌駕（同 OnOff_Duty 一致嘅分工）。
- overlay：整日 stop／更碼 segments（支援中途轉更碼）／逐 slot skip、改時間、改群組。
- 對照表（更碼→WhatsApp 群組）與訊息模板存 SQLite，可喺 panel 編輯。
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from meal_planner.duty_common import GRACE_DETAIL, GRACE_MINUTES, POST_MAPPING, RETRY_SECONDS, retry_backoff_active
from meal_planner.duty_scheduler import notify_change
from meal_planner.maintenance_db import load_sheet_rows
from meal_planner.roster import code_for_date, roster_map_from_sheet_rows
from meal_planner.schedule_grid import (
    ScheduleRow,
    load_overtime_overrides_from_rows,
    load_schedule_rows_from_rows,
    rows_for_roster,
)
from meal_planner.settings import AppSettings, get_settings
from meal_planner.timeparse import (
    business_date,
    normalize_hhmm,
    slot_datetime as _slot_datetime,
    to_minutes as _parse_hhmm,
)

SAFE_KEYWORD = "報平安更"
DEFAULT_MESSAGE_TEMPLATE = "{code} SAPP1801 報平安更正常"
DEFAULT_GROUP_MAPPING: dict[str, str] = {
    "VOC": "🍀☘️VCA💎💍共同體",
    "VPP": "🍀☘️VCA💎💍共同體",
    "IFCS1": "中環IFC👜💎👞👗報更📞☎️",
    "IFCS2": "中環IFC👜💎👞👗報更📞☎️",
    "PenA": "半島🕶🛍👗👠報更群組",
    "TSB": "時代廣場👗👜🕶CHANEL",
}
EVENTS_KEEP = 50

_RE_SUN_THU = re.compile(r"[（(]\s*日-四\s*[)）]")
_RE_FRI_SAT = re.compile(r"[（(]\s*五六\s*[)）]")

_DB_LOCK = threading.Lock()
_ACTION_LOCK = threading.Lock()


def _now(settings: AppSettings) -> datetime:
    return datetime.now(ZoneInfo(settings.dates.timezone))


def weekday_allows(content: str, biz_date: date) -> bool:
    """(日-四)/(五六) 標記：唔匹配當日星期就唔算該 slot；冇標記一律算。"""
    wd = biz_date.weekday()  # Mon=0 .. Sun=6
    if _RE_SUN_THU.search(content):
        return wd in (6, 0, 1, 2, 3)
    if _RE_FRI_SAT.search(content):
        return wd in (4, 5)
    return True


# ---------------------------------------------------------------- SQLite


def _connect(settings: AppSettings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.database_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS duty_report_overlay ("
        " date_iso TEXT PRIMARY KEY,"
        " overlay_json TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS duty_report_log ("
        " date_iso TEXT NOT NULL,"
        " slot_id TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " message TEXT NOT NULL DEFAULT '',"
        " group_name TEXT NOT NULL DEFAULT '',"
        " detail TEXT NOT NULL DEFAULT '',"
        " manual INTEGER NOT NULL DEFAULT 0,"
        " recorded_at TEXT NOT NULL,"
        " PRIMARY KEY (date_iso, slot_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS duty_report_config ("
        " config_key TEXT PRIMARY KEY,"
        " value_json TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS duty_report_events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " at TEXT NOT NULL,"
        " source TEXT NOT NULL DEFAULT '',"
        " action TEXT NOT NULL,"
        " detail TEXT NOT NULL DEFAULT '')"
    )
    return conn


def load_overlay(settings: AppSettings, biz_date: date) -> dict[str, Any]:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            row = conn.execute(
                "SELECT overlay_json FROM duty_report_overlay WHERE date_iso = ?",
                (biz_date.isoformat(),),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return {}
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def save_overlay(settings: AppSettings, biz_date: date, overlay: dict[str, Any]) -> None:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "INSERT INTO duty_report_overlay (date_iso, overlay_json, updated_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(date_iso) DO UPDATE SET overlay_json = excluded.overlay_json,"
                " updated_at = excluded.updated_at",
                (biz_date.isoformat(), json.dumps(overlay, ensure_ascii=False), _now(settings).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    notify_change()


def load_config(settings: AppSettings) -> dict[str, Any]:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute("SELECT config_key, value_json FROM duty_report_config").fetchall()
        finally:
            conn.close()
    stored: dict[str, Any] = {}
    for key, value_json in rows:
        try:
            stored[key] = json.loads(value_json)
        except ValueError:
            continue
    mapping = stored.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        mapping = dict(DEFAULT_GROUP_MAPPING)
    # 固定按更碼排序：唔理邊個 client（電話 JSONObject 唔保次序）點儲，顯示一律穩定。
    mapping = dict(sorted(mapping.items(), key=lambda kv: str(kv[0]).casefold()))
    template = stored.get("message_template")
    if not isinstance(template, str) or "{code}" not in template:
        template = DEFAULT_MESSAGE_TEMPLATE
    auto_send = stored.get("auto_send")
    return {
        "mapping": {str(k): str(v) for k, v in mapping.items()},
        "message_template": template,
        "auto_send": bool(auto_send) if auto_send is not None else False,
    }


def save_config(settings: AppSettings, patch: dict[str, Any]) -> dict[str, Any]:
    current = load_config(settings)
    if "mapping" in patch and isinstance(patch["mapping"], dict):
        current["mapping"] = {
            str(k).strip(): str(v).strip()
            for k, v in patch["mapping"].items()
            if str(k).strip()
        }
    if "message_template" in patch and isinstance(patch["message_template"], str):
        if "{code}" in patch["message_template"]:
            current["message_template"] = patch["message_template"]
    if "auto_send" in patch and patch["auto_send"] is not None:
        current["auto_send"] = bool(patch["auto_send"])
    now_iso = _now(settings).isoformat()
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            for key in ("mapping", "message_template", "auto_send"):
                conn.execute(
                    "INSERT INTO duty_report_config (config_key, value_json, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(config_key) DO UPDATE SET value_json = excluded.value_json,"
                    " updated_at = excluded.updated_at",
                    (key, json.dumps(current[key], ensure_ascii=False), now_iso),
                )
            conn.commit()
        finally:
            conn.close()
    notify_change()
    return current


def load_log(settings: AppSettings, biz_date: date) -> dict[str, dict[str, Any]]:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute(
                "SELECT slot_id, status, message, group_name, detail, manual, recorded_at"
                " FROM duty_report_log WHERE date_iso = ?",
                (biz_date.isoformat(),),
            ).fetchall()
        finally:
            conn.close()
    out: dict[str, dict[str, Any]] = {}
    for slot_id, status, message, group_name, detail, manual, recorded_at in rows:
        out[slot_id] = {
            "status": status,
            "message": message,
            "group": group_name,
            "detail": detail,
            "manual": bool(manual),
            "recorded_at": recorded_at,
        }
    return out


def record_log(
    settings: AppSettings,
    biz_date: date,
    slot_id: str,
    status: str,
    *,
    message: str = "",
    group_name: str = "",
    detail: str = "",
    manual: bool = False,
) -> None:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "INSERT INTO duty_report_log"
                " (date_iso, slot_id, status, message, group_name, detail, manual, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(date_iso, slot_id) DO UPDATE SET status = excluded.status,"
                " message = excluded.message, group_name = excluded.group_name,"
                " detail = excluded.detail, manual = excluded.manual,"
                " recorded_at = excluded.recorded_at",
                (
                    biz_date.isoformat(),
                    slot_id,
                    status,
                    message,
                    group_name,
                    detail,
                    1 if manual else 0,
                    _now(settings).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    notify_change()


def record_event(settings: AppSettings, action: str, detail: str = "", *, source: str = "") -> None:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            conn.execute(
                "INSERT INTO duty_report_events (at, source, action, detail) VALUES (?, ?, ?, ?)",
                (_now(settings).isoformat(), source, action, detail),
            )
            conn.execute(
                "DELETE FROM duty_report_events WHERE id NOT IN"
                " (SELECT id FROM duty_report_events ORDER BY id DESC LIMIT ?)",
                (EVENTS_KEEP,),
            )
            conn.commit()
        finally:
            conn.close()


def load_events(settings: AppSettings, limit: int = 20) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _connect(settings)
        try:
            rows = conn.execute(
                "SELECT at, source, action, detail FROM duty_report_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    return [{"at": at, "source": source, "action": action, "detail": detail} for at, source, action, detail in rows]


# ---------------------------------------------------------------- 計劃推導（純邏輯）


def safe_slots_for_code(parsed_rows: list[ScheduleRow], code: str, biz_date: date) -> list[tuple[str, str]]:
    """該更碼當日嘅報平安更 (HH:MM, 內容)；套用生效日期版本 + 星期標記。"""
    out: list[tuple[str, str]] = []
    for row in rows_for_roster(parsed_rows, code, biz_date):
        content = row.content or ""
        if SAFE_KEYWORD not in content:
            continue
        if row.t is None:
            continue
        if not weekday_allows(content, biz_date):
            continue
        out.append((row.t.strftime("%H:%M"), content.strip()))
    out.sort(key=lambda item: _parse_hhmm(item[0]))
    return out


def normalize_segments(segments: Any) -> list[dict[str, str]]:
    """整理 segments：[{from: 'HH:MM', code: 'X'}...]，按 from 排序；無效項剔走。"""
    if not isinstance(segments, list):
        return []
    cleaned: list[dict[str, str]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        code = str(seg.get("code") or "").strip()
        from_text = normalize_hhmm(str(seg.get("from") or "00:00").strip() or "00:00")
        if not code or not from_text:
            continue
        cleaned.append({"from": from_text, "code": code})
    cleaned.sort(key=lambda seg: _parse_hhmm(seg["from"]))
    return cleaned


def compute_slots(
    parsed_rows: list[ScheduleRow],
    segments: list[dict[str, str]],
    biz_date: date,
    mapping: dict[str, str],
    template: str,
    slot_overrides: dict[str, Any],
    overtime: tuple[time | None, time | None] = (None, None),
) -> list[dict[str, Any]]:
    """由 segments（更碼時間軸）+ 加班表 + overlay 推導當日 slot 清單（未計 sent 狀態）。

    時間優先序：panel 改時間 override＞加班表（開工 override 套落有「報開工」嘅 slot、
    收工 override 套落有「報收工」嘅 slot）＞行位表原時間。slot id 一律用行位表原時間，
    唔會因 override 而變。
    """
    ot_start, ot_end = overtime
    slots: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        code = seg["code"]
        seg_from = _parse_hhmm(seg["from"])
        seg_to = _parse_hhmm(segments[i + 1]["from"]) if i + 1 < len(segments) else 10**6
        for hhmm, content in safe_slots_for_code(parsed_rows, code, biz_date):
            minutes = _parse_hhmm(hhmm)
            if not (seg_from <= minutes < seg_to):
                continue
            slot_id = f"{code}@{hhmm}"
            base_time = hhmm
            if ot_end is not None and "報收工" in content:
                base_time = ot_end.strftime("%H:%M")
            elif ot_start is not None and "報開工" in content:
                base_time = ot_start.strftime("%H:%M")
            override = slot_overrides.get(slot_id) if isinstance(slot_overrides.get(slot_id), dict) else {}
            effective_time = str(override.get("time") or base_time)
            if _parse_hhmm(effective_time) < 0:
                effective_time = base_time
            group = str(override.get("group") or mapping.get(code, ""))
            default_message = template.replace("{code}", code)
            message = str(override.get("message") or default_message)
            slots.append(
                {
                    "id": slot_id,
                    "code": code,
                    "original_time": hhmm,
                    "ot_override": base_time != hhmm,
                    "time": effective_time,
                    "content": content,
                    "group": group,
                    "message": message,
                    "default_message": default_message,
                    "skipped": bool(override.get("skip")),
                }
            )
    slots.sort(key=lambda s: (_parse_hhmm(s["time"]), s["id"]))
    return slots


def _slot_runtime_status(
    slot: dict[str, Any],
    log_entry: dict[str, Any] | None,
    mode: str,
    biz_date: date,
    now: datetime,
    tz: ZoneInfo,
) -> str:
    """sent/failed/missed（log）＞ skipped ＞ stopped ＞ due/overdue/pending（時間）。"""
    if log_entry and log_entry.get("status") in {"sent", "missed"}:
        return str(log_entry["status"])
    if slot["skipped"]:
        return "skipped"
    if mode == "stop":
        return "stopped"
    slot_dt = _slot_datetime(biz_date, slot["time"], tz)
    if now < slot_dt:
        return "pending"
    if now < slot_dt + timedelta(minutes=GRACE_MINUTES):
        # failed 但仲喺 grace window 內：當 due，俾 scheduler 重試。
        return "due"
    if log_entry and log_entry.get("status") == "failed":
        return "failed"
    return "overdue"


def build_plan(
    settings: AppSettings | None = None,
    *,
    now: datetime | None = None,
    biz_date: date | None = None,
) -> dict[str, Any]:
    """指定日（預設今日，30 小時制）報更計劃 + 每 slot 狀態。

    過去日：唯讀回顧（有 log 就顯示結果，冇就 no_record）。
    未來日：可預先set overlay；slot 全部 pending。
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.dates.timezone)
    now = now or datetime.now(tz)
    today = business_date(now)
    biz_date = biz_date or today
    relation = "today" if biz_date == today else ("past" if biz_date < today else "future")

    config = load_config(settings)
    overlay = load_overlay(settings, biz_date)
    log = load_log(settings, biz_date)

    roster_code = ""
    parsed_rows: list[ScheduleRow] = []
    overtime: tuple[time | None, time | None] = (None, None)
    data_error = ""
    try:
        sched = load_sheet_rows("schedule_grid", settings)
        parsed_rows = load_schedule_rows_from_rows(sched.get("rows") or [])
        roster_sheet = load_sheet_rows("roster", settings)
        roster_map = roster_map_from_sheet_rows(roster_sheet.get("rows") or [])
        month_map = roster_map.get((biz_date.year, biz_date.month))
        roster_code = str(code_for_date(month_map, biz_date) or "") if month_map else ""
        overtime_rows = load_sheet_rows("overtime", settings).get("rows") or []
        overtime = load_overtime_overrides_from_rows(overtime_rows).get(biz_date, (None, None))
    except Exception as e:  # noqa: BLE001 - plan must render even with data errors
        data_error = str(e)

    overlay_segments = normalize_segments(overlay.get("segments"))
    if overlay_segments:
        segments = overlay_segments
        source = "override"
    elif roster_code:
        segments = [{"from": "00:00", "code": roster_code}]
        source = "roster"
    else:
        segments = []
        source = "none"

    mode = "stop" if overlay.get("mode") == "stop" else "auto"
    slot_overrides = overlay.get("slots") if isinstance(overlay.get("slots"), dict) else {}

    slots = compute_slots(
        parsed_rows, segments, biz_date, config["mapping"], config["message_template"], slot_overrides,
        overtime=overtime,
    )
    for slot in slots:
        entry = log.get(slot["id"])
        # 已發／曾嘗試嘅 slot：顯示發送當時記錄低嘅 group／訊息，
        # 之後改對照表唔會追溯改變歷史記錄。
        if entry and entry.get("status") in {"sent", "failed", "missed"}:
            if entry.get("group"):
                slot["group"] = entry["group"]
            if entry.get("message"):
                slot["message"] = entry["message"]
        if relation == "today":
            slot["status"] = _slot_runtime_status(slot, entry, mode, biz_date, now, tz)
        elif entry and entry.get("status") in {"sent", "failed", "missed"}:
            slot["status"] = str(entry["status"])
        elif slot["skipped"]:
            slot["status"] = "skipped"
        elif mode == "stop":
            slot["status"] = "stopped"
        else:
            slot["status"] = "pending" if relation == "future" else "no_record"
        slot["sent_at"] = entry.get("recorded_at", "") if entry else ""
        slot["detail"] = entry.get("detail", "") if entry else ""
        slot["manual"] = bool(entry.get("manual")) if entry else False

    sent_count = sum(1 for s in slots if s["status"] == "sent")
    next_slot = next((s for s in slots if s["status"] in {"pending", "due"}), None)

    return {
        "known_codes": sorted(POST_MAPPING),
        "ok": True,
        "date_iso": biz_date.isoformat(),
        "today_iso": today.isoformat(),
        "relation": relation,
        "now_iso": now.isoformat(),
        "roster_code": roster_code,
        "source": source,
        "mode": mode,
        "segments": segments,
        "auto_send": config["auto_send"],
        "mapping": config["mapping"],
        "message_template": config["message_template"],
        "slots": slots,
        "sent_count": sent_count,
        "total_count": len(slots),
        "next_time": next_slot["time"] if next_slot else "",
        "data_error": data_error,
        "events": load_events(settings),
    }


# ---------------------------------------------------------------- overlay 操作


def apply_override(
    settings: AppSettings,
    *,
    mode: str | None = None,
    segments: list[dict[str, str]] | None = None,
    slot_patch: dict[str, Any] | None = None,
    source: str = "web",
    biz_date: date | None = None,
) -> dict[str, Any]:
    """套用 override（最後指令話事）；每項操作記入 events log。"""
    now = _now(settings)
    biz_date = biz_date or business_date(now)
    overlay = load_overlay(settings, biz_date)
    day_label = "今日" if biz_date == business_date(now) else biz_date.strftime("%d/%m")

    if mode is not None:
        if mode not in {"auto", "stop"}:
            raise ValueError(f"invalid mode: {mode}")
        overlay["mode"] = mode
        record_event(settings, "mode", f"{day_label}{'唔報更' if mode == 'stop' else '要報更'}", source=source)

    if segments is not None:
        cleaned = normalize_segments(segments)
        if cleaned:
            overlay["segments"] = cleaned
            desc = "、".join(
                f"{seg['code']}(由{seg['from']})" if seg["from"] != "00:00" else seg["code"]
                for seg in cleaned
            )
            record_event(settings, "segments", f"{day_label}改 {desc}", source=source)
        else:
            overlay.pop("segments", None)
            record_event(settings, "segments", f"{day_label}還原跟更表", source=source)
        # 轉更碼 = 由頭重排：舊 slot overrides 唔再對應，一併清走。
        overlay.pop("slots", None)

    if slot_patch is not None:
        slot_id = str(slot_patch.get("id") or "").strip()
        if not slot_id:
            raise ValueError("slot patch missing id")
        slots_overlay = overlay.get("slots")
        if not isinstance(slots_overlay, dict):
            slots_overlay = {}
        entry = dict(slots_overlay.get(slot_id) or {})
        parts: list[str] = []
        if "skip" in slot_patch and slot_patch["skip"] is not None:
            entry["skip"] = bool(slot_patch["skip"])
            parts.append("skip" if entry["skip"] else "unskip")
        if "time" in slot_patch and slot_patch["time"] is not None:
            raw_time = str(slot_patch["time"]).strip()
            if raw_time:
                time_text = normalize_hhmm(raw_time)
                if not time_text:
                    raise ValueError(f"睇唔明個時間：{raw_time}（可以打 09:16 / 0916 / 2416）")
                entry["time"] = time_text
                parts.append(f"time→{time_text}")
            else:
                entry.pop("time", None)
                parts.append("time→原定")
        if "group" in slot_patch and slot_patch["group"] is not None:
            group_text = str(slot_patch["group"]).strip()
            if group_text:
                entry["group"] = group_text
                parts.append("group changed")
            else:
                entry.pop("group", None)
                parts.append("group→預設")
        if "message" in slot_patch and slot_patch["message"] is not None:
            message_text = str(slot_patch["message"]).strip()
            if message_text:
                entry["message"] = message_text
                parts.append("message changed")
            else:
                entry.pop("message", None)
                parts.append("message→預設")
        entry = {k: v for k, v in entry.items() if v not in (False, "", None)} if not entry.get("skip") else entry
        if entry:
            slots_overlay[slot_id] = entry
        else:
            slots_overlay.pop(slot_id, None)
        overlay["slots"] = slots_overlay
        record_event(settings, "slot", f"{slot_id}: {'; '.join(parts) or 'no-op'}", source=source)

    save_overlay(settings, biz_date, overlay)
    return build_plan(settings, biz_date=biz_date)


# ---------------------------------------------------------------- 發送


def send_slot(
    settings: AppSettings,
    slot_id: str,
    *,
    manual: bool,
    source: str = "web",
    date_iso: str | None = None,
) -> dict[str, Any]:
    """即時發送一個 slot（手動或排程）。只限今日；成功／失敗都記入 log。"""
    from meal_planner.whatsapp_send import WhatsAppSendError, send_group_message

    with _ACTION_LOCK:
        plan = build_plan(settings)
        if date_iso and date_iso != plan["date_iso"]:
            raise ValueError("只可以即發今日（30小時制）嘅報更")
        biz_date = date.fromisoformat(plan["date_iso"])
        slot = next((s for s in plan["slots"] if s["id"] == slot_id), None)
        if slot is None:
            raise ValueError(f"slot not found: {slot_id}")
        if not manual and slot["status"] != "due":
            return plan
        if not slot["group"]:
            record_log(
                settings, biz_date, slot_id, "failed",
                message=slot["message"], detail="no group mapped", manual=manual,
            )
            return build_plan(settings)
        try:
            send_group_message(slot["group"], slot["message"])
        except WhatsAppSendError as e:
            record_log(
                settings, biz_date, slot_id, "failed",
                message=slot["message"], group_name=slot["group"], detail=str(e), manual=manual,
            )
            if manual:
                raise
            return build_plan(settings)
        record_log(
            settings, biz_date, slot_id, "sent",
            message=slot["message"], group_name=slot["group"], manual=manual,
        )
        if manual:
            record_event(settings, "send", f"{slot_id} manual send", source=source)
        return build_plan(settings)


def process_due_slots(settings: AppSettings | None = None) -> datetime | None:
    """scheduler tick：auto_send 開 + mode=auto 先發；過咗 grace 未發標 missed。

    回傳下一個會自動發嘅時刻（scheduler 瞓到啱啱嗰刻醒，準時發）；冇就 None。
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.dates.timezone)
    plan = build_plan(settings)
    biz_date = date.fromisoformat(plan["date_iso"])
    auto_ready = bool(plan["auto_send"]) and plan["mode"] != "stop"
    now = datetime.now(tz)
    next_due: datetime | None = None
    due_seen = False
    for slot in plan["slots"]:
        if slot["status"] == "overdue":
            record_log(
                settings, biz_date, slot["id"], "missed",
                message=slot["message"], group_name=slot["group"],
                detail=GRACE_DETAIL,
            )
            continue
        if slot["status"] == "pending":
            if auto_ready:
                slot_dt = _slot_datetime(biz_date, slot["time"], tz)
                if slot_dt > now and (next_due is None or slot_dt < next_due):
                    next_due = slot_dt
            continue
        if slot["status"] != "due":
            continue
        if not auto_ready:
            continue
        due_seen = True
        if slot.get("detail") and slot.get("sent_at") and retry_backoff_active(slot["sent_at"]):
            continue  # 之前失敗過：等最少 RETRY_SECONDS 先重試，唔好每 tick 狂試
        send_slot(settings, slot["id"], manual=False, source="scheduler")
    if due_seen:
        # 到期但未完成（失敗/backoff）→ 最遲 RETRY_SECONDS 後再埞一次。
        retry_at = now + timedelta(seconds=RETRY_SECONDS)
        next_due = retry_at if next_due is None else min(next_due, retry_at)
    return next_due
