"""Best-effort local notification after meal plan versions are committed."""

from __future__ import annotations

import json
import logging
from urllib.request import Request, urlopen

_DASHBOARD_URL = "http://127.0.0.1:8788/api/meal/updated"
_LOG = logging.getLogger(__name__)


def notify_dashboard_meals(dates: list[str]) -> None:
    if not dates:
        return
    body = json.dumps({"dates": dates}).encode("utf-8")
    request = Request(
        _DASHBOARD_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=1.0) as response:
            response.read()
    except Exception as exc:
        # The plan is already saved. Dashboard's revision check will catch up.
        _LOG.warning("Dashboard meal notification failed: %s", exc)
