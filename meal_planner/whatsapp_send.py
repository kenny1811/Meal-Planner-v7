"""經 CDP 控制專用 Chrome（--remote-debugging-port=9222）嘅 WhatsApp Web 發送群組訊息。

專用 profile：C:\\Users\\Kenny\\ChromeWhatsApp（桌面捷徑「WhatsApp報更 (Chrome)」啟動）。
send 前必檢查訊息框 aria-label 含目標群組名，防止 send 錯 chat。
"""

from __future__ import annotations

import json
import threading
import urllib.request
from typing import Any

CDP_URL = "http://127.0.0.1:9222"

_SEARCH_SELECTOR = 'input[aria-label="Search or start a new chat"]'
_COMPOSER_SELECTOR = 'div[role="textbox"][data-tab="10"]'

_SEND_LOCK = threading.Lock()


class WhatsAppSendError(RuntimeError):
    pass


def cdp_health() -> dict[str, Any]:
    """唔使 playwright：直接問 CDP json 端點，check Chrome + WhatsApp tab 喺唔喺度。"""
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json", timeout=3) as r:
            pages = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - health check swallows all transport errors
        return {"cdp": False, "whatsapp": False, "detail": str(e)}
    whatsapp = any(
        p.get("type") == "page" and "web.whatsapp.com" in (p.get("url") or "")
        for p in pages
    )
    return {"cdp": True, "whatsapp": whatsapp, "detail": ""}


def send_group_message(group_name: str, message: str) -> None:
    """搜尋群組名 → 開 chat → 驗證訊息框屬於該群組 → send。可由多執行緒呼叫（有鎖）。"""
    if not group_name.strip():
        raise WhatsAppSendError("Target group name is empty")
    if not message.strip():
        raise WhatsAppSendError("Message is empty")
    with _SEND_LOCK:
        _send(group_name, message)


def _send(group_name: str, message: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise WhatsAppSendError(f"playwright not installed: {e}") from e

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            raise WhatsAppSendError(
                f"Cannot connect to Chrome CDP at {CDP_URL} — is the WhatsApp報更 Chrome running? ({e})"
            ) from e
        context = browser.contexts[0] if browser.contexts else None
        page = next(
            (pg for pg in (context.pages if context else []) if "web.whatsapp.com" in pg.url),
            None,
        )
        if page is None:
            raise WhatsAppSendError("WhatsApp Web tab not found in the dedicated Chrome")

        search = page.locator(_SEARCH_SELECTOR)
        try:
            search.wait_for(state="visible", timeout=20000)
        except Exception as e:
            raise WhatsAppSendError(f"WhatsApp search box not found (not logged in?): {e}") from e
        search.click()
        search.fill("")
        search.fill(group_name)
        page.wait_for_timeout(1500)

        result = page.locator(f'span[title="{group_name}"]').first
        try:
            result.wait_for(timeout=8000)
        except Exception as e:
            page.keyboard.press("Escape")
            raise WhatsAppSendError(f"Group not found in search results: {group_name} ({e})") from e
        result.click()
        page.wait_for_timeout(800)

        composer = page.locator(_COMPOSER_SELECTOR).first
        try:
            composer.wait_for(timeout=8000)
        except Exception as e:
            raise WhatsAppSendError(f"Message composer not found: {e}") from e
        label = composer.get_attribute("aria-label") or ""
        if group_name not in label:
            raise WhatsAppSendError(f"Wrong chat open (composer label: {label!r}), aborted send")
        composer.click()
        page.keyboard.insert_text(message)
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
