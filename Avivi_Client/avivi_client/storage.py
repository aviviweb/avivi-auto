from __future__ import annotations

import base64
import json
from pathlib import Path

from avivi_shared.crypto import fernet_from_machine_pepper


def _default_dir() -> Path:
    import os

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or "."
    return Path(base) / "Avivi"


class ClientCredentials:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (_default_dir() / "credentials.json")

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, client_id: str, fernet_key_b64: str, hmac_secret_b64: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "client_id": client_id,
            "fernet_key_b64": fernet_key_b64,
            "hmac_secret_b64": hmac_secret_b64,
        }
        raw = json.dumps(payload).encode("utf-8")
        f = fernet_from_machine_pepper()
        enc = f.encrypt(raw)
        self.path.write_bytes(enc)

    def load_decrypted(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            f = fernet_from_machine_pepper()
            raw = f.decrypt(self.path.read_bytes())
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None
