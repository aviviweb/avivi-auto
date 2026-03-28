from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.deps import require_admin
from avivi_master.services import fleet
from avivi_shared.crypto import decrypt_json, fernet_from_key

router = APIRouter(prefix="/v1/commands", tags=["commands"])


class AdminEnqueueBody(BaseModel):
    client_id: str
    command_type: str
    payload: dict = {}


@router.post("/enqueue", dependencies=[Depends(require_admin)])
async def enqueue(body: AdminEnqueueBody, session: AsyncSession = Depends(get_session)) -> dict:
    cid = await fleet.enqueue_command(
        session, body.client_id, body.command_type, json.dumps(body.payload, separators=(",", ":"))
    )
    await fleet.append_audit(session, "admin", "enqueue_command", f"{body.client_id} {body.command_type}")
    return {"id": cid}


@router.get("/poll")
async def poll_commands(
    client_id: str,
    ciphertext_b64: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    client = await fleet.get_client(session, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(base64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = base64.b64decode(ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    if data.get("client_id") != client_id:
        raise HTTPException(status_code=400, detail="client_id mismatch")
    rows = await fleet.fetch_pending_commands(session, client_id)
    return [
        {
            "id": r.id,
            "type": r.command_type,
            "payload": json.loads(r.payload_json or "{}"),
            "created_at": r.created_at.isoformat() + "Z",
        }
        for r in rows
    ]


class AckCommandBody(BaseModel):
    client_id: str
    command_id: str
    ciphertext_b64: str


@router.post("/ack")
async def ack_command(body: AckCommandBody, session: AsyncSession = Depends(get_session)) -> dict:
    client = await fleet.get_client(session, body.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(base64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = base64.b64decode(body.ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    if data.get("client_id") != body.client_id or data.get("command_id") != body.command_id:
        raise HTTPException(status_code=400, detail="Mismatch")
    await fleet.ack_command(session, body.command_id)
    return {"ok": True}
