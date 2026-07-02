"""Google Calendar sync plan for saved roster rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from meal_planner.maintenance_db import load_sheet_rows
from meal_planner.meal_schedule import roster_matches_rule
from meal_planner.roster import is_work_day, last_day_of_month, parse_roster_line, roster_for_month
from meal_planner.schedule_grid import load_overtime_overrides_from_rows, load_wake_alarm_overrides_from_rows
from meal_planner.settings import AppSettings


GC_ACCOUNT_EMAIL = "kenny1811@gmail.com"
WORK_CALENDAR_ID = "om2jpr2m3g1qfb4q54v92l21g4@group.calendar.google.com"
ALARM_CALENDAR_ID = "vauo4el6f4vh20fjvm7fjlsfc0@group.calendar.google.com"
OLD_LEAVE_CALENDAR_ID = "lb8dr22puf0b3krrov8oti3r4c@group.calendar.google.com"
NONWORK_CALENDAR_ID = ""
SYNC_SOURCE = "meal_planner_roster"
DEFAULT_TIME_ZONE = "Asia/Hong_Kong"
ALARM_EVENT_DURATION = timedelta(hours=1, minutes=45)


@dataclass(frozen=True)
class ShiftRule:
    code_pattern: str
    start: time
    end: time
    priority: float


@dataclass(frozen=True)
class CalendarEventPlan:
    kind: str
    calendar_id: str
    roster_date: date
    roster_code: str
    start_at: datetime
    end_at: datetime
    summary: str
    description: str
    all_day: bool = False


@dataclass(frozen=True)
class RosterCalendarPlan:
    work_events: list[CalendarEventPlan]
    alarm_events: list[CalendarEventPlan]
    leave_events: list[CalendarEventPlan]
    skipped: list[dict[str, str]]
    roster_dates: set[date]
    time_min: datetime | None
    time_max: datetime | None


@dataclass(frozen=True)
class GoogleCalendarSyncConfig:
    enabled: bool
    dry_run: bool
    time_zone: str
    account_email: str
    work_calendar_id: str
    alarm_calendar_id: str
    leave_calendar_id: str
    backup_dir: Path
    service_account_file: Path | None
    oauth_client_file: Path | None
    oauth_token_file: Path | None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "on"}


def config_from_env(settings: AppSettings) -> GoogleCalendarSyncConfig:
    from meal_planner.storage import load_google_calendar_sync_settings

    saved = load_google_calendar_sync_settings()
    backup_dir_raw = os.environ.get("MENU_GOOGLE_CALENDAR_BACKUP_DIR")
    backup_dir = Path(backup_dir_raw).expanduser() if backup_dir_raw else settings.data_folder / "google_calendar_backups"
    service_account_raw = str(saved.get("service_account_file") or "").strip()
    oauth_client_raw = str(saved.get("client_secret_file") or "").strip()
    oauth_token_raw = str(saved.get("token_file") or "").strip()
    nonwork_calendar_raw = str(
        saved.get("nonwork_calendar_id")
        or os.environ.get("MENU_GOOGLE_CALENDAR_NONWORK_ID")
        or ""
    ).strip()
    if nonwork_calendar_raw == OLD_LEAVE_CALENDAR_ID:
        nonwork_calendar_raw = ""
    return GoogleCalendarSyncConfig(
        enabled=bool(saved.get("enabled")),
        dry_run=not bool(saved.get("write")),
        time_zone=os.environ.get("MENU_GOOGLE_CALENDAR_TIME_ZONE", DEFAULT_TIME_ZONE),
        account_email=os.environ.get("MENU_GOOGLE_CALENDAR_ACCOUNT", GC_ACCOUNT_EMAIL),
        work_calendar_id=os.environ.get("MENU_GOOGLE_CALENDAR_WORK_ID", WORK_CALENDAR_ID),
        alarm_calendar_id=os.environ.get("MENU_GOOGLE_CALENDAR_ALARM_ID", ALARM_CALENDAR_ID),
        leave_calendar_id=nonwork_calendar_raw,
        backup_dir=backup_dir,
        service_account_file=Path(service_account_raw).expanduser() if service_account_raw else None,
        oauth_client_file=Path(oauth_client_raw).expanduser() if oauth_client_raw else None,
        oauth_token_file=Path(oauth_token_raw).expanduser() if oauth_token_raw else settings.data_folder / "google_calendar_token.json",
    )


def _roster_cell_texts(rows: list[list[Any]]) -> list[str | None]:
    out: list[str | None] = []
    for row in rows:
        if isinstance(row, list) and row:
            out.append(None if row[0] is None else str(row[0]))
    return out


_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
_COMPACT_TIME_RE = re.compile(r"^\s*(\d{1,2})(\d{2})\s*$")


def _normal_time(value: Any) -> time | None:
    if isinstance(value, time):
        return time(value.hour, value.minute)
    if isinstance(value, datetime):
        return time(value.hour, value.minute)
    raw = str(value or "")
    match = _TIME_RE.match(raw) or _COMPACT_TIME_RE.match(raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _time_label(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def payroll_shift_rules(rows: list[list[Any]]) -> list[ShiftRule]:
    rules: list[ShiftRule] = []
    for row in (rows or [])[1:]:
        if not isinstance(row, list):
            continue
        pattern = str((row[0] if len(row) > 0 else "") or "").strip()
        start = _normal_time(row[1] if len(row) > 1 else None)
        end = _normal_time(row[2] if len(row) > 2 else None)
        if not pattern or start is None or end is None:
            continue
        try:
            priority = float(row[4] if len(row) > 4 else 0)
        except (TypeError, ValueError):
            priority = 0
        rules.append(ShiftRule(pattern, start, end, priority))
    return sorted(rules, key=lambda x: x.priority, reverse=True)


def shift_rule_for_code(rules: list[ShiftRule], roster_code: str) -> ShiftRule | None:
    for rule in rules:
        if roster_matches_rule(rule.code_pattern, roster_code):
            return rule
    return None


def _combine(day: date, value: time, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, value.hour, value.minute, tzinfo=tz)


def _combine_alarm(day: date, wake: time, start_time: time, tz: ZoneInfo) -> datetime:
    alarm_at = _combine(day, wake, tz)
    if wake > start_time:
        alarm_at -= timedelta(days=1)
    return alarm_at


def build_roster_calendar_plan(
    roster_rows: list[list[Any]],
    payroll_rows: list[list[Any]],
    overtime_rows: list[list[Any]] | None = None,
    wake_alarm_rows: list[list[Any]] | None = None,
    *,
    work_calendar_id: str = WORK_CALENDAR_ID,
    alarm_calendar_id: str = ALARM_CALENDAR_ID,
    leave_calendar_id: str = NONWORK_CALENDAR_ID,
    time_zone: str = DEFAULT_TIME_ZONE,
    from_date: date | None = None,
) -> RosterCalendarPlan:
    tz = ZoneInfo(time_zone)
    roster_map = roster_for_month(_roster_cell_texts(roster_rows))
    shift_rules = payroll_shift_rules(payroll_rows)
    overtime_by_date = load_overtime_overrides_from_rows(overtime_rows or [])
    wake_alarm_by_date = load_wake_alarm_overrides_from_rows(wake_alarm_rows or [])
    work_events: list[CalendarEventPlan] = []
    alarm_events: list[CalendarEventPlan] = []
    leave_events: list[CalendarEventPlan] = []
    skipped: list[dict[str, str]] = []
    roster_dates: set[date] = set()

    for (_, _), month in sorted(roster_map.items()):
        for day, code in sorted(month.day_to_code.items()):
            try:
                roster_day = date(month.year, month.month, day)
            except ValueError:
                skipped.append({"date": f"{month.year:04d}-{month.month:02d}-{day:02d}", "code": code, "reason": "invalid_date"})
                continue
            if from_date is not None and roster_day < from_date:
                skipped.append({"date": roster_day.isoformat(), "code": code, "reason": "before_sync_start"})
                continue
            roster_dates.add(roster_day)
            if not is_work_day(code):
                leave_start = datetime(roster_day.year, roster_day.month, roster_day.day, tzinfo=tz)
                leave_events.append(
                    CalendarEventPlan(
                        kind="leave",
                        calendar_id=leave_calendar_id,
                        roster_date=roster_day,
                        roster_code=code,
                        start_at=leave_start,
                        end_at=leave_start + timedelta(days=1),
                        summary=code,
                        description=f"更碼: {code}\nGenerated by Meal Planner roster sync.",
                        all_day=True,
                    )
                )
                wake_time = wake_alarm_by_date.get(roster_day)
                if wake_time:
                    alarm_start = _combine(roster_day, wake_time, tz)
                    alarm_events.append(
                        CalendarEventPlan(
                            kind="alarm",
                            calendar_id=alarm_calendar_id,
                            roster_date=roster_day,
                            roster_code=code,
                            start_at=alarm_start,
                            end_at=alarm_start + ALARM_EVENT_DURATION,
                            summary="起身",
                            description="起身",
                        )
                    )
                continue
            rule = shift_rule_for_code(shift_rules, code)
            if rule is None:
                skipped.append({"date": roster_day.isoformat(), "code": code, "reason": "missing_shift_time"})
                continue

            overtime_start, overtime_end = overtime_by_date.get(roster_day, (None, None))
            start_time = overtime_start or rule.start
            end_time = overtime_end or rule.end
            start_at = _combine(roster_day, start_time, tz)
            end_at = _combine(roster_day, end_time, tz)
            if end_at <= start_at:
                end_at += timedelta(days=1)
            start_label = _time_label(start_time)
            end_label = _time_label(end_time)
            summary = code
            description = f"更碼: {code}\n更時: {start_label}-{end_label}\nGenerated by Meal Planner roster sync."
            work_events.append(
                CalendarEventPlan(
                    kind="work",
                    calendar_id=work_calendar_id,
                    roster_date=roster_day,
                    roster_code=code,
                    start_at=start_at,
                    end_at=end_at,
                    summary=summary,
                    description=description,
                )
            )

            wake_time = wake_alarm_by_date.get(roster_day)
            alarm_start = _combine_alarm(roster_day, wake_time, start_time, tz) if wake_time else start_at - timedelta(hours=3)
            alarm_events.append(
                CalendarEventPlan(
                    kind="alarm",
                    calendar_id=alarm_calendar_id,
                    roster_date=roster_day,
                    roster_code=code,
                    start_at=alarm_start,
                    end_at=alarm_start + ALARM_EVENT_DURATION,
                    summary="起身",
                    description="起身",
                )
            )

    all_events = work_events + alarm_events + leave_events
    time_min = min((event.start_at for event in all_events), default=None)
    time_max = max((event.end_at for event in all_events), default=None)
    if time_min is not None:
        time_min = time_min.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_max is not None:
        time_max = (time_max + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return RosterCalendarPlan(work_events, alarm_events, leave_events, skipped, roster_dates, time_min, time_max)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def event_body(event: CalendarEventPlan, time_zone: str) -> dict[str, Any]:
    if event.all_day:
        return {
            "summary": event.summary,
            "description": event.description,
            "start": {"date": event.start_at.date().isoformat()},
            "end": {"date": event.end_at.date().isoformat()},
            "extendedProperties": {
                "private": {
                    "source": SYNC_SOURCE,
                    "kind": event.kind,
                    "roster_date": event.roster_date.isoformat(),
                    "roster_code": event.roster_code,
                }
            },
        }
    return {
        "summary": event.summary,
        "description": event.description,
        "start": {"dateTime": _iso(event.start_at), "timeZone": time_zone},
        "end": {"dateTime": _iso(event.end_at), "timeZone": time_zone},
        "extendedProperties": {
            "private": {
                "source": SYNC_SOURCE,
                "kind": event.kind,
                "roster_date": event.roster_date.isoformat(),
                "roster_code": event.roster_code,
            }
        },
    }


def _load_service_account_credentials(path: Path) -> Any:
    from google.oauth2 import service_account

    scopes = ["https://www.googleapis.com/auth/calendar"]
    return service_account.Credentials.from_service_account_file(str(path), scopes=scopes)


def _load_oauth_credentials(client_file: Path, token_file: Path | None) -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = ["https://www.googleapis.com/auth/calendar"]
    creds = None
    if token_file and token_file.is_file():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes)
        creds = flow.run_local_server(port=0)
        if token_file:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_google_calendar_service(config: GoogleCalendarSyncConfig) -> Any:
    from googleapiclient.discovery import build

    if config.service_account_file:
        credentials = _load_service_account_credentials(config.service_account_file)
    elif config.oauth_client_file:
        credentials = _load_oauth_credentials(config.oauth_client_file, config.oauth_token_file)
    else:
        raise RuntimeError("Google Calendar sync enabled but no credential file is configured.")
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def google_calendar_auth_status(settings: AppSettings, config: GoogleCalendarSyncConfig | None = None) -> dict[str, Any]:
    config = config or config_from_env(settings)
    if config.service_account_file:
        exists = config.service_account_file.is_file()
        return {
            "authenticated": exists,
            "auth_type": "service_account",
            "status": "connected" if exists else "missing_service_account",
            "service_account_file": str(config.service_account_file),
            "token_file": str(config.oauth_token_file) if config.oauth_token_file else "",
        }
    if not config.oauth_client_file:
        return {"authenticated": False, "auth_type": "oauth", "status": "missing_client_secret", "token_file": ""}
    if not config.oauth_client_file.is_file():
        return {
            "authenticated": False,
            "auth_type": "oauth",
            "status": "missing_client_secret",
            "client_secret_file": str(config.oauth_client_file),
            "token_file": str(config.oauth_token_file) if config.oauth_token_file else "",
        }
    token_exists = bool(config.oauth_token_file and config.oauth_token_file.is_file())
    return {
        "authenticated": token_exists,
        "auth_type": "oauth",
        "status": "connected" if token_exists else "missing_token",
        "client_secret_file": str(config.oauth_client_file),
        "token_file": str(config.oauth_token_file) if config.oauth_token_file else "",
    }


def authorize_google_calendar(settings: AppSettings) -> dict[str, Any]:
    config = config_from_env(settings)
    if config.service_account_file:
        service = build_google_calendar_service(config)
        service.calendarList().list(maxResults=1).execute()
        return {
            "status": "connected",
            "auth_type": "service_account",
            "token_file": str(config.oauth_token_file) if config.oauth_token_file else "",
        }
    if not config.oauth_client_file:
        raise RuntimeError("請先設定 Google OAuth client secret JSON 路徑。")
    if not config.oauth_client_file.is_file():
        raise RuntimeError(f"搵唔到 Google OAuth client secret JSON: {config.oauth_client_file}")
    if config.oauth_token_file is None:
        raise RuntimeError("Google OAuth token path is missing.")
    config.oauth_token_file.parent.mkdir(parents=True, exist_ok=True)
    _load_oauth_credentials(config.oauth_client_file, config.oauth_token_file)
    service = build_google_calendar_service(config)
    service.calendarList().list(maxResults=1).execute()
    return {
        "status": "connected",
        "auth_type": "oauth",
        "token_file": str(config.oauth_token_file),
    }


def _list_events(service: Any, calendar_id: str, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=_iso(time_min),
                timeMax=_iso(time_max),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return events


def _event_roster_date(event: dict[str, Any]) -> str | None:
    props = (event.get("extendedProperties") or {}).get("private") or {}
    value = props.get("roster_date")
    if value:
        return str(value)
    start = event.get("start") or {}
    raw = start.get("dateTime") or start.get("date")
    if not raw:
        return None
    return str(raw)[:10]


def _event_summary(event: dict[str, Any]) -> str:
    return str(event.get("summary") or "").strip()


def _last_prefixed_calendar_event(events: list[dict[str, Any]], prefix: str) -> dict[str, str] | None:
    matches: list[dict[str, str]] = []
    for event in events:
        summary = _event_summary(event)
        if not summary.startswith(prefix):
            continue
        day = _event_roster_date(event)
        if not day:
            continue
        matches.append({"date": day, "code": summary})
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item["date"], item["code"]))[-1]


def _same_calendar_marker(a: dict[str, str] | None, b: dict[str, str] | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return a.get("date") == b.get("date") and a.get("code") == b.get("code")


def check_nonwork_calendar_consistency(
    roster_text: str,
    settings: AppSettings,
    *,
    service: Any | None = None,
    config: GoogleCalendarSyncConfig | None = None,
) -> dict[str, Any]:
    month = parse_roster_line(roster_text)
    if month is None:
        return {"status": "invalid_roster", "complete": False, "warnings": []}
    last_day = last_day_of_month(month.year, month.month)
    missing = [day for day in range(1, last_day + 1) if day not in month.day_to_code]
    if missing:
        return {
            "status": "incomplete",
            "complete": False,
            "year": month.year,
            "month": month.month,
            "missing_days": missing,
            "warnings": [],
        }

    config = config or config_from_env(settings)
    if not config.leave_calendar_id:
        return {
            "status": "missing_nonwork_calendar",
            "complete": True,
            "year": month.year,
            "month": month.month,
            "warnings": ["未設定非返工日日曆"],
        }
    auth_status = google_calendar_auth_status(settings, config)
    if not auth_status.get("authenticated"):
        return {
            "status": "not_authenticated",
            "complete": True,
            "year": month.year,
            "month": month.month,
            "warnings": ["Google Calendar 未登入"],
        }

    tz = ZoneInfo(config.time_zone)
    time_min = datetime(month.year, month.month, 1, tzinfo=tz)
    time_max = (datetime(month.year, month.month, last_day, tzinfo=tz) + timedelta(days=1))
    service = service or build_google_calendar_service(config)
    old_events = _list_events(service, OLD_LEAVE_CALENDAR_ID, time_min, time_max)
    nonwork_events = _list_events(service, config.leave_calendar_id, time_min, time_max)

    items: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for prefix in ("SH", "WL"):
        old_last = _last_prefixed_calendar_event(old_events, prefix)
        nonwork_last = _last_prefixed_calendar_event(nonwork_events, prefix)
        consistent = _same_calendar_marker(old_last, nonwork_last)
        items[prefix] = {
            "old_leave": old_last,
            "nonwork": nonwork_last,
            "consistent": consistent,
        }
        if not consistent:
            def marker(value: dict[str, str] | None) -> str:
                if not value:
                    return "無"
                return f"{value.get('date', '')} {value.get('code', '')}".strip()

            warnings.append(
                f"最後{prefix}不一致：大假 {marker(old_last)}；非返工日 {marker(nonwork_last)}"
            )
    return {
        "status": "ok" if not warnings else "mismatch",
        "complete": True,
        "year": month.year,
        "month": month.month,
        "items": items,
        "warnings": warnings,
    }


def _event_start_value(event: dict[str, Any]) -> str | None:
    start = event.get("start") or {}
    raw = start.get("dateTime") or start.get("date")
    return str(raw) if raw else None


def _event_end_value(event: dict[str, Any]) -> str | None:
    end = event.get("end") or {}
    raw = end.get("dateTime") or end.get("date")
    return str(raw) if raw else None


def _planned_start_value(event: CalendarEventPlan) -> str:
    if event.all_day:
        return event.start_at.date().isoformat()
    return _iso(event.start_at)


def _planned_end_value(event: CalendarEventPlan) -> str:
    if event.all_day:
        return event.end_at.date().isoformat()
    return _iso(event.end_at)


def _body_start_value(body: dict[str, Any]) -> str | None:
    start = body.get("start") or {}
    raw = start.get("dateTime") or start.get("date")
    return str(raw) if raw else None


def _body_end_value(body: dict[str, Any]) -> str | None:
    end = body.get("end") or {}
    raw = end.get("dateTime") or end.get("date")
    return str(raw) if raw else None


def _starts_equal(existing: str | None, planned: str) -> bool:
    if existing is None:
        return False
    return existing == planned or existing.startswith(planned) or planned.startswith(existing)


def _normal_description(value: Any) -> str:
    return str(value or "").strip()


def _event_matches_body(existing: dict[str, Any], body: dict[str, Any]) -> bool:
    body_private = ((body.get("extendedProperties") or {}).get("private") or {})
    existing_private = ((existing.get("extendedProperties") or {}).get("private") or {})
    return (
        str(existing.get("summary") or "").strip() == str(body.get("summary") or "").strip()
        and _starts_equal(_event_start_value(existing), _body_start_value(body) or "")
        and _starts_equal(_event_end_value(existing), _body_end_value(body) or "")
        and _normal_description(existing.get("description")) == _normal_description(body.get("description"))
        and all(str(existing_private.get(k) or "") == str(v or "") for k, v in body_private.items())
    )


def _events_match_plan(existing: dict[str, Any], planned: CalendarEventPlan) -> bool:
    return (
        str(existing.get("summary") or "").strip() == planned.summary
        and _starts_equal(_event_start_value(existing), _planned_start_value(planned))
        and _starts_equal(_event_end_value(existing), _planned_end_value(planned))
    )


def _is_managed_event(event: dict[str, Any], kind: str) -> bool:
    props = (event.get("extendedProperties") or {}).get("private") or {}
    return props.get("source") == SYNC_SOURCE and props.get("kind") == kind


def _backup_events(
    service: Any,
    config: GoogleCalendarSyncConfig,
    plan: RosterCalendarPlan,
) -> tuple[Path | None, dict[str, list[dict[str, Any]]]]:
    if plan.time_min is None or plan.time_max is None:
        calendars = {config.work_calendar_id: [], config.alarm_calendar_id: []}
        if config.leave_calendar_id:
            calendars[config.leave_calendar_id] = []
        return None, calendars
    backup = {
        config.work_calendar_id: _list_events(service, config.work_calendar_id, plan.time_min, plan.time_max),
        config.alarm_calendar_id: _list_events(service, config.alarm_calendar_id, plan.time_min, plan.time_max),
    }
    if config.leave_calendar_id:
        backup[config.leave_calendar_id] = _list_events(service, config.leave_calendar_id, plan.time_min, plan.time_max)
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo(config.time_zone)).strftime("%Y%m%d_%H%M%S")
    path = config.backup_dir / f"google-calendar-roster-sync-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "account_email": config.account_email,
                "time_min": _iso(plan.time_min),
                "time_max": _iso(plan.time_max),
                "calendars": backup,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path, backup


def _upsert_events(
    service: Any,
    calendar_id: str,
    kind: str,
    planned: list[CalendarEventPlan],
    existing: list[dict[str, Any]],
    time_zone: str,
    *,
    authoritative_dates: set[str] | None = None,
    adopt_unmanaged: bool = False,
) -> dict[str, int]:
    managed_by_date = {
        _event_roster_date(event): event
        for event in existing
        if _is_managed_event(event, kind) and _event_roster_date(event)
    }
    unmanaged_by_date: dict[str, list[dict[str, Any]]] = {}
    for event in existing:
        key = _event_roster_date(event)
        if key and not _is_managed_event(event, kind):
            unmanaged_by_date.setdefault(key, []).append(event)

    counts = {"created": 0, "updated": 0, "skipped_ambiguous": 0, "skipped_unmanaged": 0, "deleted": 0}
    planned_dates = {event.roster_date.isoformat() for event in planned}
    for event in planned:
        key = event.roster_date.isoformat()
        body = event_body(event, time_zone)
        target = managed_by_date.get(key)
        same_day = unmanaged_by_date.get(key, [])
        if target is None and adopt_unmanaged and same_day:
            if len(same_day) == 1:
                target = same_day[0]
            else:
                counts["skipped_ambiguous"] += 1
                continue
        if target:
            if not _event_matches_body(target, body):
                service.events().update(calendarId=calendar_id, eventId=target["id"], body=body).execute()
                counts["updated"] += 1
        else:
            if same_day:
                if len(same_day) > 1:
                    counts["skipped_ambiguous"] += 1
                else:
                    counts["skipped_unmanaged"] += 1
                continue
            service.events().insert(calendarId=calendar_id, body=body).execute()
            counts["created"] += 1

    for key, event in managed_by_date.items():
        if key not in planned_dates and (authoritative_dates is None or key in authoritative_dates):
            service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
            counts["deleted"] += 1
    if adopt_unmanaged and authoritative_dates is not None:
        for key, events in unmanaged_by_date.items():
            if key in planned_dates or key not in authoritative_dates:
                continue
            for event in events:
                service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
                counts["deleted"] += 1
    return counts


def sync_roster_to_google_calendar(
    roster_rows: list[list[Any]],
    settings: AppSettings,
    *,
    service: Any | None = None,
    config: GoogleCalendarSyncConfig | None = None,
) -> dict[str, Any]:
    config = config or config_from_env(settings)
    if not config.enabled:
        return {
            "status": "disabled",
            "enabled": False,
            "dry_run": True,
            "account_email": config.account_email,
            "work_calendar_id": config.work_calendar_id,
            "alarm_calendar_id": config.alarm_calendar_id,
            "leave_calendar_id": config.leave_calendar_id,
        }
    if not config.dry_run:
        auth_status = google_calendar_auth_status(settings, config)
        if not auth_status.get("authenticated"):
            return {
                "status": "not_authenticated",
                "enabled": config.enabled,
                "dry_run": True,
                "account_email": config.account_email,
                "work_calendar_id": config.work_calendar_id,
                "alarm_calendar_id": config.alarm_calendar_id,
                "leave_calendar_id": config.leave_calendar_id,
                "auth": auth_status,
            }

    payroll_payload = load_sheet_rows("payroll_times", settings)
    payroll_rows = payroll_payload.get("rows", []) if isinstance(payroll_payload, dict) else []
    overtime_payload = load_sheet_rows("overtime", settings)
    overtime_rows = overtime_payload.get("rows", []) if isinstance(overtime_payload, dict) else []
    wake_alarm_payload = load_sheet_rows("wake_alarms", settings)
    wake_alarm_rows = wake_alarm_payload.get("rows", []) if isinstance(wake_alarm_payload, dict) else []
    plan = build_roster_calendar_plan(
        roster_rows,
        payroll_rows if isinstance(payroll_rows, list) else [],
        overtime_rows if isinstance(overtime_rows, list) else [],
        wake_alarm_rows if isinstance(wake_alarm_rows, list) else [],
        work_calendar_id=config.work_calendar_id,
        alarm_calendar_id=config.alarm_calendar_id,
        leave_calendar_id=config.leave_calendar_id,
        time_zone=config.time_zone,
        from_date=datetime.now(ZoneInfo(config.time_zone)).date(),
    )
    result: dict[str, Any] = {
        "enabled": config.enabled,
        "dry_run": config.dry_run or not config.enabled,
        "account_email": config.account_email,
        "work_calendar_id": config.work_calendar_id,
        "alarm_calendar_id": config.alarm_calendar_id,
        "leave_calendar_id": config.leave_calendar_id,
        "work_events": len(plan.work_events),
        "alarm_events": len(plan.alarm_events),
        "leave_events": len(plan.leave_events),
        "skipped": plan.skipped,
        "time_min": _iso(plan.time_min) if plan.time_min else None,
        "time_max": _iso(plan.time_max) if plan.time_max else None,
    }
    if config.dry_run:
        result["status"] = "dry_run"
        return result
    if plan.time_min is None or plan.time_max is None:
        result["status"] = "empty"
        return result

    service = service or build_google_calendar_service(config)
    backup_path, backup = _backup_events(service, config, plan)
    result["backup_path"] = str(backup_path) if backup_path else None
    work_counts = _upsert_events(
        service,
        config.work_calendar_id,
        "work",
        plan.work_events,
        backup.get(config.work_calendar_id, []),
        config.time_zone,
        authoritative_dates={day.isoformat() for day in plan.roster_dates},
        adopt_unmanaged=True,
    )
    alarm_counts = _upsert_events(
        service,
        config.alarm_calendar_id,
        "alarm",
        plan.alarm_events,
        backup.get(config.alarm_calendar_id, []),
        config.time_zone,
        authoritative_dates={day.isoformat() for day in plan.roster_dates},
        adopt_unmanaged=True,
    )
    if config.leave_calendar_id:
        leave_counts = _upsert_events(
            service,
            config.leave_calendar_id,
            "leave",
            plan.leave_events,
            backup.get(config.leave_calendar_id, []),
            config.time_zone,
            authoritative_dates={day.isoformat() for day in plan.roster_dates},
            adopt_unmanaged=True,
        )
    else:
        leave_counts = {"created": 0, "updated": 0, "skipped_ambiguous": 0, "skipped_unmanaged": 0, "deleted": 0, "disabled": 1}
    result["status"] = "synced"
    result["work"] = work_counts
    result["alarm"] = alarm_counts
    result["leave"] = leave_counts
    return result
