from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.services import fleet
from avivi_shared.crypto import decrypt_json, fernet_from_key
from avivi_shared.models import HeartbeatPayload

router = APIRouter(prefix="/v1", tags=["heartbeat"])


class EncryptedEnvelope(BaseModel):
    client_id: str
    ciphertext_b64: str


@router.post("/heartbeat")
async def heartbeat(
    body: EncryptedEnvelope,
    session: AsyncSession = Depends(get_session),
) -> dict:
    client = await fleet.get_client(session, body.client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown client")
    fernet = fernet_from_key(base64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = base64.b64decode(body.ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decrypt failed")
    payload = HeartbeatPayload.model_validate(data)
    if payload.client_id != body.client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id mismatch")
    await fleet.touch_heartbeat(
        session,
        body.client_id,
        payload.license_status,
        owner_telegram_chat_id=payload.owner_telegram_chat_id,
        hostname=payload.hostname,
    )
    pending = await fleet.count_pending_commands(session, body.client_id)
    row = await fleet.get_client(session, body.client_id)
    domain = (row.agent_domain or "").strip() if row else ""
    business_id = row.business_id if row else None
    business_name = ""
    if business_id:
        b = await fleet.get_business(session, business_id)
        business_name = (b.name or "").strip() if b else ""
    if client.locked:
        return {
            "ok": True,
            "locked": True,
            "server_time": datetime.utcnow().isoformat() + "Z",
            "pending_commands": pending,
            "agent_domain": domain,
            "business_id": business_id,
            "business_name": business_name,
        }
    return {
        "ok": True,
        "locked": False,
        "server_time": datetime.utcnow().isoformat() + "Z",
        "pending_commands": pending,
        "agent_domain": domain,
        "business_id": business_id,
        "business_name": business_name,
    }
