from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.models_db import ClientRecord
from avivi_master.services.client_crypto import new_enroll_bundle
from avivi_shared.models import EnrollRequest, EnrollResponse

router = APIRouter(prefix="/v1", tags=["enroll"])


@router.post("/enroll", response_model=EnrollResponse)
async def enroll(body: EnrollRequest, session: AsyncSession = Depends(get_session)) -> EnrollResponse:
    resp = new_enroll_bundle()
    row = ClientRecord(
        id=resp.client_id,
        hostname=body.hostname,
        app_version=body.app_version,
        fernet_key_b64=resp.fernet_key_b64,
        hmac_secret_b64=resp.hmac_secret_b64,
        owner_telegram_chat_id=(body.owner_telegram_chat_id or "").strip() or None,
    )
    session.add(row)
    await session.commit()
    return resp
