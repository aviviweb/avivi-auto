from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import yaml
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel

try:
    from avivi_shared.crypto import decrypt_json as _shared_decrypt_json
    from avivi_shared.crypto import encrypt_json as _shared_encrypt_json

    _HAS_SHARED_CRYPTO = True
except ImportError:
    _shared_decrypt_json = None  # type: ignore[assignment]
    _shared_encrypt_json = None  # type: ignore[assignment]
    _HAS_SHARED_CRYPTO = False


class DbProfile(BaseModel):
    id: str
    engine: str  # postgresql, mysql, mongodb, mssql
    host: str = "127.0.0.1"
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    ssl: bool = False
    read_only: bool = True


def _machine_fernet() -> Fernet:
    """Derive a stable Fernet key from machine identity (cryptography.fernet)."""
    import hashlib
    import os

    material = hashlib.sha256(
        (os.environ.get("COMPUTERNAME", "pc") + "|openclaw-launcher-db-secrets-v1").encode()
    ).digest()
    key = base64.urlsafe_b64encode(material)
    return Fernet(key)


class DbProfilesStore:
    """Meta in profiles_meta.yaml; encrypted secrets in profiles.secrets.enc (JSON)."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.meta_path = workspace_root / "database_mappings" / "profiles_meta.yaml"
        self.secrets_path = workspace_root / "database_mappings" / "profiles.secrets.enc"
        self._fernet = _machine_fernet()

    def _load_secrets(self) -> dict[str, dict[str, Any]]:
        if not self.secrets_path.exists():
            return {}
        raw = self.secrets_path.read_bytes()
        if _HAS_SHARED_CRYPTO and _shared_decrypt_json is not None:
            try:
                out = _shared_decrypt_json(raw, self._fernet)
                if isinstance(out, dict):
                    return out  # type: ignore[return-value]
            except (InvalidToken, TypeError, ValueError, OSError):
                pass
        try:
            plain = self._fernet.decrypt(raw)
            return json.loads(plain.decode("utf-8"))
        except Exception:
            return {}

    def _save_secrets(self, data: dict[str, dict[str, Any]]) -> None:
        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_SHARED_CRYPTO and _shared_encrypt_json is not None:
            blob = _shared_encrypt_json(data, self._fernet)
        else:
            blob = self._fernet.encrypt(json.dumps(data, separators=(",", ":")).encode("utf-8"))
        self.secrets_path.write_bytes(blob)

    def list_profiles(self) -> list[dict[str, Any]]:
        if not self.meta_path.exists():
            return []
        doc = yaml.safe_load(self.meta_path.read_text(encoding="utf-8")) or {}
        return list(doc.get("profiles") or [])

    def save_profile(self, profile: DbProfile) -> None:
        secrets = self._load_secrets()
        secrets[profile.id] = {
            "password": profile.password,
            "user": profile.user,
        }
        self._save_secrets(secrets)

        rows = self.list_profiles()
        others = [r for r in rows if r.get("id") != profile.id]
        others.append(
            {
                "id": profile.id,
                "engine": profile.engine,
                "host": profile.host,
                "port": profile.port,
                "database": profile.database,
                "ssl": profile.ssl,
                "read_only": profile.read_only,
            }
        )
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            yaml.safe_dump({"profiles": others}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def get_full_profile(self, profile_id: str) -> DbProfile | None:
        rows = self.list_profiles()
        meta = next((r for r in rows if r.get("id") == profile_id), None)
        if not meta:
            return None
        secrets = self._load_secrets().get(profile_id, {})
        return DbProfile(
            id=profile_id,
            engine=meta.get("engine", "postgresql"),
            host=meta.get("host", "127.0.0.1"),
            port=int(meta.get("port", 5432)),
            user=secrets.get("user", ""),
            password=secrets.get("password", ""),
            database=meta.get("database", ""),
            ssl=bool(meta.get("ssl", False)),
            read_only=bool(meta.get("read_only", True)),
        )

    def delete_profile(self, profile_id: str) -> None:
        secrets = self._load_secrets()
        secrets.pop(profile_id, None)
        self._save_secrets(secrets)
        rows = [r for r in self.list_profiles() if r.get("id") != profile_id]
        self.meta_path.write_text(
            yaml.safe_dump({"profiles": rows}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
