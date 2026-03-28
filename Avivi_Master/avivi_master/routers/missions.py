from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.deps import require_admin
from avivi_master.services import fleet
from avivi_shared.crypto import verify_hmac_sha256

router = APIRouter(prefix="/v1/missions", tags=["missions"])


class MissionPushBody(BaseModel):
    client_id: str
    mission_id: str
    version: str
    encrypted_blob_b64: str
    signature_hex: str | None = None


@router.post("/push", dependencies=[Depends(require_admin)])
async def push_mission(body: MissionPushBody, session: AsyncSession = Depends(get_session)) -> dict:
    client = await fleet.get_client(session, body.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    blob = base64.b64decode(body.encrypted_blob_b64)
    if body.signature_hex:
        secret = base64.b64decode(client.hmac_secret_b64.encode("ascii"))
        if not verify_hmac_sha256(secret, blob, body.signature_hex):
            raise HTTPException(status_code=400, detail="Bad signature")
    await fleet.add_mission_row(
        session,
        body.client_id,
        body.mission_id,
        body.version,
        blob,
        body.signature_hex,
    )
    await fleet.append_audit(session, "admin", "push_mission", f"{body.client_id} {body.mission_id}")
    return {"ok": True}


class PendingMissionOut(BaseModel):
    id: str
    mission_id: str
    version: str
    encrypted_blob_b64: str
    signature_hex: str | None = None


@router.get("/pending", response_model=list[PendingMissionOut])
async def pending_missions(
    client_id: str,
    ciphertext_b64: str,
    session: AsyncSession = Depends(get_session),
) -> list[PendingMissionOut]:
    """Client polls with encrypted proof of possession (minimal: same as heartbeat payload)."""
    import base64 as b64

    from avivi_shared.crypto import decrypt_json, fernet_from_key

    client = await fleet.get_client(session, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(b64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = b64.b64decode(ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    if data.get("client_id") != client_id:
        raise HTTPException(status_code=400, detail="client_id mismatch")
    rows = await fleet.pending_missions(session, client_id)
    return [
        PendingMissionOut(
            id=r.id,
            mission_id=r.mission_id,
            version=r.version,
            encrypted_blob_b64=b64.b64encode(r.encrypted_blob).decode("ascii"),
            signature_hex=r.signature_hex,
        )
        for r in rows
    ]


class AckBody(BaseModel):
    client_id: str
    mission_pk: str
    ciphertext_b64: str


@router.post("/ack")
async def ack_mission(body: AckBody, session: AsyncSession = Depends(get_session)) -> dict:
    import base64 as b64

    from avivi_shared.crypto import decrypt_json, fernet_from_key

    client = await fleet.get_client(session, body.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(b64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = b64.b64decode(body.ciphertext_b64)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    if data.get("client_id") != body.client_id or data.get("mission_pk") != body.mission_pk:
        raise HTTPException(status_code=400, detail="Mismatch")
    await fleet.mark_mission_delivered(session, body.mission_pk)
    return {"ok": True}
