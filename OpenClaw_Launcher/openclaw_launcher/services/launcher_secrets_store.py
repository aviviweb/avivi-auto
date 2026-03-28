from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def _launcher_fernet() -> Fernet:
    raw = hashlib.sha256(
        (os.environ.get("COMPUTERNAME", "pc") + "|openclaw-launcher-secrets-v1").encode()
    ).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


class LauncherSecretsStore:
    """Encrypt Telegram token (and optional keys) at rest under workspace config/."""

    def __init__(self, workspace_root: Path) -> None:
        self.path = workspace_root / "config" / "launcher_secrets.enc"
        self._fernet = _launcher_fernet()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = self._fernet.decrypt(self.path.read_bytes())
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (InvalidToken, json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._fernet.encrypt(json.dumps(data, separators=(",", ":")).encode("utf-8"))
        self.path.write_bytes(blob)

    def get_telegram_bot_token(self) -> str:
        return str(self._load().get("telegram_bot_token") or "")

    def set_telegram_bot_token(self, token: str) -> None:
        data = self._load()
        data["telegram_bot_token"] = token.strip()
        self._save(data)
