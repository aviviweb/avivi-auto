from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.config import settings
from avivi_master.models_db import ClientRecord, ROIEventRow


async def aggregate_today_minutes(session: AsyncSession) -> list[tuple[str, float]]:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    r = await session.execute(
        select(ROIEventRow.client_id, func.sum(ROIEventRow.minutes_saved))
        .where(ROIEventRow.created_at >= start)
        .group_by(ROIEventRow.client_id)
    )
    return [(row[0], float(row[1] or 0)) for row in r.all()]


def minutes_to_ils(minutes: float, hourly_rate: float) -> float:
    return round((minutes / 60.0) * hourly_rate, 2)


async def build_nightly_summaries(session: AsyncSession) -> list[dict]:
    rows = await aggregate_today_minutes(session)
    summaries = []
    for client_id, mins in rows:
        cr = await session.execute(select(ClientRecord).where(ClientRecord.id == client_id))
        client = cr.scalar_one_or_none()
        rate = (
            client.hourly_rate_ils
            if client and client.hourly_rate_ils is not None
            else settings.roi_hourly_rate_ils
        )
        ils = minutes_to_ils(mins, rate)
        hours = round(mins / 60.0, 2)
        summaries.append(
            {
                "client_id": client_id,
                "hostname": client.hostname if client else "",
                "minutes_saved": mins,
                "hours_saved": hours,
                "estimated_ils": ils,
                "owner_chat_id": client.owner_telegram_chat_id if client else None,
            }
        )
    return summaries
