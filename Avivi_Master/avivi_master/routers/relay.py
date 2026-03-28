from __future__ import annotations

import base64
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.config import settings
from avivi_master.db import get_session
from avivi_master.models_db import UsageRecord
from avivi_master.services import fleet
from avivi_shared.crypto import decrypt_json, fernet_from_key

router = APIRouter(prefix="/v1/relay", tags=["relay"])


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False


@router.post("/ollama/chat")
async def relay_chat(
    request: Request,
    body: OllamaChatRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Authenticated relay: client sends X-Client-Id + encrypted envelope in body extension or headers."""
    client_id = request.headers.get("X-Client-Id", "")
    enc = request.headers.get("X-Auth-Ciphertext", "")
    if not client_id or not enc:
        raise HTTPException(status_code=401, detail="Missing client auth headers")
    client = await fleet.get_client(session, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client")
    fernet = fernet_from_key(base64.b64decode(client.fernet_key_b64.encode("ascii")))
    try:
        raw = base64.b64decode(enc)
        data = decrypt_json(raw, fernet)
    except Exception:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    if data.get("client_id") != client_id:
        raise HTTPException(status_code=400, detail="client_id mismatch")

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {"model": body.model, "messages": body.messages, "stream": False}
    async with httpx.AsyncClient(timeout=120.0) as client_http:
        r = await client_http.post(url, json=payload)
        r.raise_for_status()
        out = r.json()

    # crude token estimate for billing
    prompt_chars = sum(len(str(m.get("content", ""))) for m in body.messages)
    completion = out.get("message", {}).get("content", "") or ""
    pt = max(1, prompt_chars // 4)
    ct = max(1, len(completion) // 4)
    session.add(
        UsageRecord(client_id=client_id, model=body.model, prompt_tokens=pt, completion_tokens=ct)
    )
    await session.commit()
    return out
