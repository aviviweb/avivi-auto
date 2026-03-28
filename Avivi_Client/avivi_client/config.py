from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or "."
    return Path(base) / "Avivi"


def first_run_deps_marker_path() -> Path:
    return _default_data_dir() / ".first_run_deps_done"


class ClientSettings(BaseModel):
    master_base_url: str = "http://127.0.0.1:8000"
    app_version: str = "0.1.0"
    license_status: str = "trial"
    build_channel: str = "stable"
    deps_auto_install_on_startup: bool = False
    deps_auto_install_first_run: bool = True
    deps_verify_download_sha256: bool = False
    ai_mode: str = "local_ollama"
    external_api_base: str = ""
    external_api_key: str = ""
    owner_telegram_bot_token: str = ""
    owner_telegram_chat_id: str = ""
    gateway_cache_dir: str = Field(
        default="",
        description="Session cache dir for WhatsApp gateway; empty uses ~/.openclaw/cache",
    )
    mysql_host: str = "127.0.0.1"
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""
    pg_host: str = "127.0.0.1"
    pg_user: str = ""
    pg_password: str = ""
    pg_database: str = ""

    @property
    def resolved_cache_dir(self) -> Path:
        if self.gateway_cache_dir.strip():
            return Path(self.gateway_cache_dir).expanduser()
        return Path.home() / ".openclaw" / "cache"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (_default_data_dir() / "client_settings.json")

    def load(self) -> ClientSettings:
        if not self.path.exists():
            return ClientSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return ClientSettings.model_validate(data)
        except Exception:
            return ClientSettings()

    def save(self, s: ClientSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(s.model_dump_json(indent=2), encoding="utf-8")
