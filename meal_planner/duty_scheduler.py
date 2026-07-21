"""Report_Normal（報平安更→WhatsApp）+ OnOff_Duty（報開工/收工→Google Form）共用背景排程。

事件驅動，唔係定時 poll：
- 每輪處理完到期動作後，兩邊各自回報「下一個到期時刻」，loop 瞓到最早嗰個
  時刻正先醒——到期嗰一刻即刻射（舊制齋等 15 秒 tick，會遲 0–15 秒）。
- 相關資料一改（更表/加班表/行位表儲存、overlay/log/開關）就 notify_change()
  即刻叫醒 loop 重新計劃，所以唔使靠密密 poll 嚟捕捉改動。
- IDLE_FALLBACK_SECONDS 係保險絲：萬一有邊條 mutation path 冇 notify，
  最多都係遲呢個時間先見到改動；正常情況一日先醒幾十次，唔再係每 15 秒。

由 app.main()（真・server 進程）啟動；pytest / TestClient 唔會行 main()，
所以測試永遠唔會觸發真實發送。
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime

IDLE_FALLBACK_SECONDS = 300
MIN_SLEEP_SECONDS = 0.2

_STARTED = False
_START_LOCK = threading.Lock()
_LAST_ERROR = ""
_WAKE = threading.Event()


def notify_change() -> None:
    """資料改咗（更表/加班表/overlay/log/開關）→ 即刻叫醒 scheduler 重新計劃。"""
    _WAKE.set()


def start_scheduler() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_loop, name="duty-scheduler", daemon=True)
    thread.start()


def last_error() -> str:
    return _LAST_ERROR


def _loop() -> None:
    global _LAST_ERROR
    while True:
        _WAKE.clear()
        errors: list[str] = []
        wake_ats: list[datetime] = []
        try:
            from meal_planner.duty_report import process_due_slots  # Report_Normal

            wake_at = process_due_slots()
            if wake_at is not None:
                wake_ats.append(wake_at)
        except Exception:  # noqa: BLE001 - scheduler must survive any tick error
            errors.append(traceback.format_exc(limit=3))
        try:
            from meal_planner.duty_form import process_due_actions  # OnOff_Duty

            wake_at = process_due_actions()
            if wake_at is not None:
                wake_ats.append(wake_at)
        except Exception:  # noqa: BLE001 - 一邊死唔可以拖冧另一邊
            errors.append(traceback.format_exc(limit=3))
        _LAST_ERROR = "\n".join(errors)

        timeout = float(IDLE_FALLBACK_SECONDS)
        if wake_ats:
            next_at = min(wake_ats)
            delta = (next_at - datetime.now(next_at.tzinfo)).total_seconds()
            timeout = min(timeout, delta)
        # 瞓到下一個到期時刻／保險絲到期；期間 notify_change() 會即刻叫醒。
        _WAKE.wait(max(timeout, MIN_SLEEP_SECONDS))
