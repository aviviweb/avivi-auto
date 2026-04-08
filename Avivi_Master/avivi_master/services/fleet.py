from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.models_db import (
    ApiKeyRow,
    AuditLogRow,
    BotRow,
    BusinessRow,
    ClientRecord,
    CommandQueueRow,
    MissionRow,
    ROIEventRow,
)


async def get_client(session: AsyncSession, client_id: str) -> ClientRecord | None:
    r = await session.execute(select(ClientRecord).where(ClientRecord.id == client_id))
    return r.scalar_one_or_none()


async def list_clients(session: AsyncSession, business_id: str | None = None) -> list[ClientRecord]:
    q = select(ClientRecord)
    if business_id is not None:
        q = q.where(ClientRecord.business_id == business_id)
    q = q.order_by(ClientRecord.last_heartbeat.desc().nulls_last())
    r = await session.execute(q)
    return list(r.scalars().all())


async def list_businesses(session: AsyncSession) -> list[BusinessRow]:
    r = await session.execute(select(BusinessRow).order_by(BusinessRow.created_at.desc()))
    return list(r.scalars().all())


async def get_business(session: AsyncSession, business_id: str) -> BusinessRow | None:
    r = await session.execute(select(BusinessRow).where(BusinessRow.id == business_id))
    return r.scalar_one_or_none()


async def create_business(session: AsyncSession, name: str) -> BusinessRow:
    row = BusinessRow(name=(name or "").strip()[:256], active=True)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def set_client_business(session: AsyncSession, client_id: str, business_id: str | None) -> bool:
    c = await get_client(session, client_id)
    if not c:
        return False
    await session.execute(
        update(ClientRecord).where(ClientRecord.id == client_id).values(business_id=business_id)
    )
    await session.commit()
    return True


async def list_bots(session: AsyncSession, business_id: str | None = None) -> list[BotRow]:
    q = select(BotRow)
    if business_id is not None:
        q = q.where(BotRow.business_id == business_id)
    q = q.order_by(BotRow.created_at.desc())
    r = await session.execute(q)
    return list(r.scalars().all())


async def create_bot(
    session: AsyncSession,
    business_id: str,
    bot_type: str,
    display_name: str,
    token_ref: str,
    enabled: bool,
    config_json: str,
) -> BotRow:
    row = BotRow(
        business_id=business_id,
        bot_type=(bot_type or "").strip()[:64],
        display_name=(display_name or "").strip()[:256],
        token_ref=(token_ref or "").strip()[:256],
        enabled=bool(enabled),
        config_json=config_json or "{}",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def set_bot_enabled(session: AsyncSession, bot_id: str, enabled: bool) -> bool:
    r = await session.execute(select(BotRow).where(BotRow.id == bot_id))
    row = r.scalar_one_or_none()
    if not row:
        return False
    await session.execute(update(BotRow).where(BotRow.id == bot_id).values(enabled=bool(enabled)))
    await session.commit()
    return True


async def list_api_keys(session: AsyncSession, business_id: str | None = None) -> list[ApiKeyRow]:
    q = select(ApiKeyRow)
    if business_id is not None:
        q = q.where(ApiKeyRow.business_id == business_id)
    q = q.order_by(ApiKeyRow.created_at.desc())
    r = await session.execute(q)
    return list(r.scalars().all())


async def touch_heartbeat(
    session: AsyncSession,
    client_id: str,
    license_status: str,
    owner_telegram_chat_id: str | None = None,
    hostname: str | None = None,
) -> None:
    vals: dict = {
        "last_heartbeat": datetime.utcnow(),
        "license_status": license_status,
    }
    if owner_telegram_chat_id is not None and str(owner_telegram_chat_id).strip():
        vals["owner_telegram_chat_id"] = str(owner_telegram_chat_id).strip()
    if hostname is not None:
        vals["hostname"] = (hostname or "")[:512]
    await session.execute(update(ClientRecord).where(ClientRecord.id == client_id).values(**vals))
    await session.commit()


async def set_agent_domain(session: AsyncSession, client_id: str, agent_domain: str) -> bool:
    c = await get_client(session, client_id)
    if not c:
        return False
    trimmed = (agent_domain or "").strip()[:256]
    await session.execute(
        update(ClientRecord).where(ClientRecord.id == client_id).values(agent_domain=trimmed)
    )
    await session.commit()
    return True


async def count_pending_commands(session: AsyncSession, client_id: str) -> int:
    r = await session.execute(
        select(func.count())
        .select_from(CommandQueueRow)
        .where(CommandQueueRow.client_id == client_id, CommandQueueRow.acked.is_(False))
    )
    return int(r.scalar_one() or 0)


async def append_audit(
    session: AsyncSession,
    actor: str,
    action: str,
    detail: str,
    business_id: str | None = None,
) -> None:
    session.add(AuditLogRow(actor=actor, action=action, detail=detail, business_id=business_id))
    await session.commit()


async def enqueue_command(session: AsyncSession, client_id: str, command_type: str, payload_json: str) -> str:
    row = CommandQueueRow(client_id=client_id, command_type=command_type, payload_json=payload_json)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row.id


async def fetch_pending_commands(session: AsyncSession, client_id: str) -> list[CommandQueueRow]:
    r = await session.execute(
        select(CommandQueueRow)
        .where(CommandQueueRow.client_id == client_id, CommandQueueRow.acked.is_(False))
        .order_by(CommandQueueRow.created_at)
    )
    return list(r.scalars().all())


async def ack_command(session: AsyncSession, command_db_id: str) -> None:
    await session.execute(update(CommandQueueRow).where(CommandQueueRow.id == command_db_id).values(acked=True))
    await session.commit()


async def add_mission_row(
    session: AsyncSession,
    client_id: str,
    mission_id: str,
    version: str,
    blob: bytes,
    signature_hex: str | None,
) -> MissionRow:
    row = MissionRow(
        client_id=client_id,
        mission_id=mission_id,
        version=version,
        encrypted_blob=blob,
        signature_hex=signature_hex,
        delivered=False,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def pending_missions(session: AsyncSession, client_id: str) -> list[MissionRow]:
    r = await session.execute(
        select(MissionRow).where(MissionRow.client_id == client_id, MissionRow.delivered.is_(False))
    )
    return list(r.scalars().all())


async def mark_mission_delivered(session: AsyncSession, mission_pk: str) -> None:
    await session.execute(update(MissionRow).where(MissionRow.id == mission_pk).values(delivered=True))
    await session.commit()


async def set_client_locked(session: AsyncSession, client_id: str, locked: bool) -> None:
    await session.execute(update(ClientRecord).where(ClientRecord.id == client_id).values(locked=locked))
    await session.commit()


async def record_roi_event(session: AsyncSession, client_id: str, event_type: str, minutes_saved: float) -> None:
    session.add(ROIEventRow(client_id=client_id, event_type=event_type, minutes_saved=minutes_saved))
    await session.commit()
