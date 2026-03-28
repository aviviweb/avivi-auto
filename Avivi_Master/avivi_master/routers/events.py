from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.services import fleet
from avivi_shared.crypto import decrypt_json, fernet_from_key

router = APIRouter(prefix="/v1/clients", tags=["events"])


class ClientEventBody(BaseModel):
    client_id: str
    ciphertext_b64: str


@router.post("/{client_id}/events")
async def post_event(
    client_id: str,
    body: ClientEventBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.client_id != client_id:
        raise HTTPException(status_code=400, detail="client_id mismatch")
    client = await fleet.get_client(session, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(base64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = base64.b64decode(body.ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    event_type = data.get("event_type", "unknown")
    minutes = float(data.get("minutes_saved", 0) or 0)
    await fleet.record_roi_event(session, client_id, event_type, minutes)
    await fleet.append_audit(session, client_id, "client_event", str(data.get("message", ""))[:500])
    return {"ok": True}
