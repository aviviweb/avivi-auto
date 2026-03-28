from __future__ import annotations

import base64

import httpx
from avivi_shared.crypto import encrypt_json, fernet_from_key


def post_client_event(
    base_url: str,
    client_id: str,
    fernet_key_b64: str,
    event_type: str,
    message: str,
    minutes_saved: float = 0.0,
    meta: dict | None = None,
) -> None:
    f = fernet_from_key(base64.b64decode(fernet_key_b64.encode("ascii")))
    data = {
        "client_id": client_id,
        "event_type": event_type,
        "message": message,
        "minutes_saved": minutes_saved,
        "meta": meta or {},
    }
    raw = encrypt_json(data, f)
    url = base_url.rstrip("/") + f"/v1/clients/{client_id}/events"
    env = {"client_id": client_id, "ciphertext_b64": base64.b64encode(raw).decode("ascii")}
    with httpx.Client(timeout=20.0) as hc:
        hc.post(url, json=env)
