from __future__ import annotations

import time

import httpx


def check_telegram_bot(
    token: str, timeout: float = 10.0
) -> tuple[bool, str, int | None]:
    """Returns (ok, detail, latency_ms_or_none)."""
    if not token.strip():
        return False, "No bot token configured", None
    url = f"https://api.telegram.org/bot{token.strip()}/getMe"
    try:
        t0 = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            ms = int((time.perf_counter() - t0) * 1000)
            data = r.json()
            if data.get("ok") and data.get("result"):
                u = data["result"].get("username", "?")
                return True, f"@{u}", ms
            return False, data.get("description", r.text)[:200], ms
    except Exception as e:
        return False, str(e)[:200], None
