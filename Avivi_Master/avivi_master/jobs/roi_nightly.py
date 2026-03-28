from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.config import settings
from avivi_master.db import SessionLocal
from avivi_master.services.roi import build_nightly_summaries

log = logging.getLogger(__name__)


async def run_nightly_roi_job() -> None:
    async with SessionLocal() as session:
        summaries = await build_nightly_summaries(session)
    if not summaries:
        log.info("ROI nightly: no events today")
        return
    token = settings.master_telegram_bot_token
    if not token:
        log.info("ROI nightly: no telegram token, logging summaries")
        for s in summaries:
            log.info("ROI %s: %s hours, ~%s ILS", s["client_id"], s["hours_saved"], s["estimated_ils"])
        return
    for s in summaries:
        chat = s.get("owner_chat_id")
        if not chat:
            continue
        text = (
            f"Avivi — daily summary\nToday Avivi saved you {s['hours_saved']} work hours "
            f"and {s['estimated_ils']} ₪ (estimated value)."
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(url, json={"chat_id": int(chat), "text": text})
