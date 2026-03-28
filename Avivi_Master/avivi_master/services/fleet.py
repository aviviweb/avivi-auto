from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.models_db import AuditLogRow, ClientRecord, CommandQueueRow, MissionRow, ROIEventRow


async def get_client(session: AsyncSession, client_id: str) -> ClientRecord | None:
    r = await session.execute(select(ClientRecord).where(ClientRecord.id == client_id))
    return r.scalar_one_or_none()


async def list_clients(session: AsyncSession) -> list[ClientRecord]:
    r = await session.execute(
        select(ClientRecord).order_by(ClientRecord.last_heartbeat.desc().nulls_last())
    )
    return list(r.scalars().all())


async def touch_heartbeat(
    session: AsyncSession,
    client_id: str,
    license_status: str,
    owner_telegram_chat_id: str | None = None,
) -> None:
    vals: dict = {
        "last_heartbeat": datetime.utcnow(),
        "license_status": license_status,
    }
    if owner_telegram_chat_id is not None and str(owner_telegram_chat_id).strip():
        vals["owner_telegram_chat_id"] = str(owner_telegram_chat_id).strip()
    await session.execute(update(ClientRecord).where(ClientRecord.id == client_id).values(**vals))
    await session.commit()


async def count_pending_commands(session: AsyncSession, client_id: str) -> int:
    r = await session.execute(
        select(func.count())
        .select_from(CommandQueueRow)
        .where(CommandQueueRow.client_id == client_id, CommandQueueRow.acked.is_(False))
    )
    return int(r.scalar_one() or 0)


async def append_audit(session: AsyncSession, actor: str, action: str, detail: str) -> None:
    session.add(AuditLogRow(actor=actor, action=action, detail=detail))
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
