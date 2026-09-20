"""電腦 → 電話 push：叫電話即刻重新匯入行位表。

電話平時係自己 pull（每日 05:00 / 05:30 撳 /export-all），所以打風改咗當日行位表之後，
唔 push 就要等聽日、或者人手撳一下 Import。呢度加返一條主動嘅路：Apply 完即刻叫電話重跑
匯入，電話跟住照樣自己 pull /export-all（同一份 parsing 邏輯，唔會兩邊 drift），
排完鬧鐘再通知手錶——一 push 電腦／電話／手錶三邊齊。

電話冇固定 IP，所以唔喺 config 寫死：電話每次打上電腦都會帶 `X-Alarm-Client: phone`，
我哋記低嗰個來源 IP。未見過電話就直接講「未知電話位置」，唔會靜靜哋當推咗。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from meal_planner.storage import load_phone_endpoint, save_phone_endpoint

PHONE_PORT = 8765
PUSH_PATH = "/push/schedule-grid"
PUSH_TIMEOUT_S = 25.0
CLIENT_HEADER = "x-alarm-client"
CLIENT_HEADER_VALUE = "phone"


TOKEN_HEADER = "X-Alarm-Token"
CAPTURE_PATH = "/capture/watch"


def remember_phone_host(host: str | None, token: str | None = None) -> None:
    """電話打上嚟嗰陣叫一次；IP 同 token 都冇變就唔使再寫 DB。

    token 係電話 8765 嘅門匙（電話自己生成，每次打上嚟都帶住）；電腦 push／截圖要帶返去。
    """
    clean = (host or "").strip()
    if not clean or clean in {"127.0.0.1", "::1", "localhost"}:
        return
    clean_token = (token or "").strip()
    current = load_phone_endpoint()
    if current.get("host") == clean and (not clean_token or current.get("token") == clean_token):
        return
    save_phone_endpoint({
        "host": clean,
        "seen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token": clean_token or str(current.get("token") or ""),
    })


def phone_endpoint() -> dict[str, Any]:
    endpoint = load_phone_endpoint()
    host = str(endpoint.get("host") or "").strip()
    return {
        "host": host,
        "seen_at": str(endpoint.get("seen_at") or ""),
        "url": f"http://{host}:{PHONE_PORT}{PUSH_PATH}" if host else "",
        "has_token": bool(endpoint.get("token")),
    }


def _phone_headers() -> dict[str, str]:
    token = str(load_phone_endpoint().get("token") or "")
    return {TOKEN_HEADER: token} if token else {}


def capture_watch(timeout: float = 30.0) -> tuple[int, bytes, str]:
    """經電話攞手錶截圖（電話做中繼）。回傳 (HTTP status, body, content-type)。"""
    host = phone_endpoint()["host"]
    if not host:
        return 503, "電腦未見過電話上嚟，冇位置可以攞截圖。".encode("utf-8"), "text/plain; charset=utf-8"
    request = urllib.request.Request(f"http://{host}:{PHONE_PORT}{CAPTURE_PATH}", headers=_phone_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "image/png")
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else str(e).encode("utf-8")), "text/plain; charset=utf-8"
    except Exception as e:  # noqa: BLE001
        return 503, str(e).encode("utf-8"), "text/plain; charset=utf-8"


def push_schedule_grid(timeout: float = PUSH_TIMEOUT_S) -> dict[str, Any]:
    """回傳 {status, detail, ...}；status 係 ok / unknown_phone / error。"""
    endpoint = phone_endpoint()
    if not endpoint["url"]:
        return {
            "status": "unknown_phone",
            "detail": "電腦未見過電話上嚟（電話 app 未開過、或者未連到電腦），冇位置可以 push。",
        }
    request = urllib.request.Request(endpoint["url"], data=b"", method="POST", headers=_phone_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # 電話收到但匯入唔成功
        detail = e.read().decode("utf-8", "replace") if e.fp else str(e)
        return {"status": "error", "detail": detail.strip() or f"HTTP {e.code}", "host": endpoint["host"]}
    except Exception as e:  # noqa: BLE001 - 電話唔喺網／app 冇開
        return {"status": "error", "detail": str(e), "host": endpoint["host"]}
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        data = {}
    return {
        "status": "ok" if data.get("ok") else "error",
        "detail": str(data.get("message") or body.strip()),
        "host": endpoint["host"],
        "alarm_count": data.get("alarm_count"),
        "plan_date": data.get("plan_date"),
        "roster_code": data.get("roster_code"),
    }
