from __future__ import annotations

import base64
from pathlib import Path

import httpx
from avivi_shared.crypto import decrypt_json, fernet_from_key, verify_hmac_sha256
from avivi_shared.models import MissionV1

from avivi_client.services.crypto_util import encrypt_blob


def fetch_pending(base_url: str, client_id: str, fernet_key_b64: str) -> list[dict]:
    ct = encrypt_blob(client_id, fernet_key_b64)
    url = base_url.rstrip("/") + "/v1/missions/pending"
    with httpx.Client(timeout=30.0) as hc:
        r = hc.get(url, params={"client_id": client_id, "ciphertext_b64": ct})
        r.raise_for_status()
        return r.json()


def ack_mission(
    base_url: str, client_id: str, mission_pk: str, fernet_key_b64: str
) -> None:
    ct = encrypt_blob(client_id, fernet_key_b64, {"mission_pk": mission_pk})
    url = base_url.rstrip("/") + "/v1/missions/ack"
    with httpx.Client(timeout=30.0) as hc:
        r = hc.post(url, json={"client_id": client_id, "mission_pk": mission_pk, "ciphertext_b64": ct})
        r.raise_for_status()


def apply_mission_blob(
    blob_b64: str,
    fernet_key_b64: str,
    hmac_secret_b64: str | None,
    signature_hex: str | None,
    dest_dir: Path,
) -> MissionV1:
    raw = base64.b64decode(blob_b64)
    if signature_hex and hmac_secret_b64:
        secret = base64.b64decode(hmac_secret_b64.encode("ascii"))
        if not verify_hmac_sha256(secret, raw, signature_hex):
            raise ValueError("Invalid mission HMAC")
    f = fernet_from_key(base64.b64decode(fernet_key_b64.encode("ascii")))
    data = decrypt_json(raw, f)
    m = MissionV1.model_validate(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{m.mission_id}_{m.version}.enc"
    out.write_bytes(raw)
    return m
