from __future__ import annotations

import httpx

from avivi_client.services.crypto_util import encrypt_blob


def poll_commands(base_url: str, client_id: str, fernet_key_b64: str) -> list[dict]:
    ct = encrypt_blob(client_id, fernet_key_b64)
    url = base_url.rstrip("/") + "/v1/commands/poll"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params={"client_id": client_id, "ciphertext_b64": ct})
        r.raise_for_status()
        return r.json()


def ack_command(base_url: str, client_id: str, command_id: str, fernet_key_b64: str) -> None:
    ct = encrypt_blob(client_id, fernet_key_b64, {"command_id": command_id})
    url = base_url.rstrip("/") + "/v1/commands/ack"
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            url, json={"client_id": client_id, "command_id": command_id, "ciphertext_b64": ct}
        )
        r.raise_for_status()
