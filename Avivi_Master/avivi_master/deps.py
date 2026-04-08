from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.config import settings
from avivi_master.db import get_session
from avivi_master.models_db import ApiKeyRow


@dataclass(frozen=True)
class AdminContext:
    role: str  # super_admin|business_admin
    business_id: str | None
    api_key_id: str | None = None
    label: str = ""


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def require_admin(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> AdminContext:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin API key")

    # Backward compatible: allow a single super-admin key from env.
    if settings.admin_api_key and hmac.compare_digest(x_api_key, settings.admin_api_key):
        return AdminContext(role="super_admin", business_id=None, api_key_id=None, label="env")

    key_hash = _sha256_hex(x_api_key)
    r = await session.execute(
        select(ApiKeyRow).where(ApiKeyRow.key_hash_hex == key_hash, ApiKeyRow.enabled.is_(True))
    )
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")

    await session.execute(
        update(ApiKeyRow)
        .where(ApiKeyRow.id == row.id)
        .values(last_used_at=datetime.utcnow())
    )
    await session.commit()

    return AdminContext(role=row.role, business_id=row.business_id, api_key_id=row.id, label=row.label)
