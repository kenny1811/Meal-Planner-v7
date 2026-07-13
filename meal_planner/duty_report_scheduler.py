"""報更背景排程：每 15 秒 tick 一次，到報平安更時間自動經 WhatsApp 發送。

由 app.main()（真・server 進程）啟動；pytest / TestClient 唔會行 main()，
所以測試永遠唔會觸發真實發送。
"""

from __future__ import annotations

import threading
import time
import traceback

TICK_SECONDS = 15

_STARTED = False
_START_LOCK = threading.Lock()
_LAST_ERROR = ""


def start_scheduler() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_loop, name="duty-report-scheduler", daemon=True)
    thread.start()


def last_error() -> str:
    return _LAST_ERROR


def _loop() -> None:
    global _LAST_ERROR
    while True:
        try:
            from meal_planner.duty_report import process_due_slots

            process_due_slots()
            _LAST_ERROR = ""
        except Exception:  # noqa: BLE001 - scheduler must survive any tick error
            _LAST_ERROR = traceback.format_exc(limit=3)
        time.sleep(TICK_SECONDS)
