from __future__ import annotations

from typing import Any

import httpx

from avivi_client.config import ClientSettings
from avivi_client.services.crypto_util import encrypt_blob


def chat_completion(
    settings: ClientSettings,
    client_id: str,
    fernet_key_b64: str,
    model: str,
    messages: list[dict[str, Any]],
    ai_mode_override: str | None = None,
) -> dict[str, Any]:
    mode = (ai_mode_override or settings.ai_mode or "local_ollama").strip()
    if mode == "local_ollama":
        url = "http://127.0.0.1:11434/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    if settings.ai_mode == "remote_relay":
        base = settings.master_base_url.rstrip("/")
        enc = encrypt_blob(client_id, fernet_key_b64)
        url = base + "/v1/relay/ollama/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                url,
                json=payload,
                headers={"X-Client-Id": client_id, "X-Auth-Ciphertext": enc},
            )
            r.raise_for_status()
            return r.json()
    if mode == "external_api" and settings.external_api_base:
        url = settings.external_api_base.rstrip("/") + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.external_api_key}"}
        body = {"model": model, "messages": messages}
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
    raise ValueError(f"Unsupported AI mode: {mode}")
