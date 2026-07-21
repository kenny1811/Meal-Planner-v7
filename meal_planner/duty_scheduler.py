"""Report_Normal（報平安更→WhatsApp）+ OnOff_Duty（報開工/收工→Google Form）共用背景排程。

準時發送：每個 tick 處理完到期動作後，兩邊各自回報「下一個到期時刻」，
loop 瞓到最早嗰個時刻正先醒（上限 TICK_SECONDS——更表/加班表/開關隨時會改，
唔可以瞓死），所以到期嗰一刻即刻射，唔會似舊制咁齋等 15 秒 tick、遲最多 15 秒。

由 app.main()（真・server 進程）啟動；pytest / TestClient 唔會行 main()，
所以測試永遠唔會觸發真實發送。
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime

TICK_SECONDS = 15
MIN_SLEEP_SECONDS = 0.2

_STARTED = False
_START_LOCK = threading.Lock()
_LAST_ERROR = ""


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

        sleep_seconds = float(TICK_SECONDS)
        if wake_ats:
            next_at = min(wake_ats)
            delta = (next_at - datetime.now(next_at.tzinfo)).total_seconds()
            sleep_seconds = min(sleep_seconds, delta)
        time.sleep(max(sleep_seconds, MIN_SLEEP_SECONDS))
