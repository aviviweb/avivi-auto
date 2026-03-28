from __future__ import annotations

import httpx

from avivi_client.config import ClientSettings
from avivi_shared.models import EnrollRequest, EnrollResponse


def enroll_sync(base_url: str, settings: ClientSettings) -> EnrollResponse:
    url = base_url.rstrip("/") + "/v1/enroll"
    oc = (settings.owner_telegram_chat_id or "").strip() or None
    body = EnrollRequest(
        hostname=__import__("socket").gethostname(),
        app_version=settings.app_version,
        owner_telegram_chat_id=oc,
    )
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json=body.model_dump())
        r.raise_for_status()
        return EnrollResponse.model_validate(r.json())
