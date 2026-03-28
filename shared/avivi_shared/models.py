from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AIProfile(str, Enum):
    local_ollama = "local_ollama"
    remote_relay = "remote_relay"
    external_api = "external_api"


class HeartbeatPayload(BaseModel):
    client_id: str
    hostname: str
    app_version: str
    license_status: str = "trial"
    build_channel: str = "stable"
    owner_telegram_chat_id: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    ts: datetime | None = None


class EnrollRequest(BaseModel):
    hostname: str
    app_version: str
    owner_telegram_chat_id: str | None = None


class EnrollResponse(BaseModel):
    client_id: str
    fernet_key_b64: str
    hmac_secret_b64: str


class MissionPersona(BaseModel):
    name: str
    system_prompt: str


class MissionDbScope(BaseModel):
    allowed_tables: list[str] = Field(default_factory=list)
    read_only: bool = True


class MissionChannels(BaseModel):
    whatsapp: bool = True
    telegram_owner: bool = True


class MissionTriggers(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    cron_expressions: list[str] = Field(default_factory=list)


class MissionSensitiveActions(BaseModel):
    patterns: list[str] = Field(default_factory=list)
    require_hitl: bool = True


class OwnerCommandDef(BaseModel):
    command_id: str
    label: str
    callback_data: str | None = None


class MissionV1(BaseModel):
    schema_version: str = "1"
    mission_id: str
    version: str
    persona: MissionPersona
    db_scope: MissionDbScope = Field(default_factory=MissionDbScope)
    triggers: MissionTriggers = Field(default_factory=MissionTriggers)
    sensitive_actions: MissionSensitiveActions = Field(default_factory=MissionSensitiveActions)
    channels: MissionChannels = Field(default_factory=MissionChannels)
    model_profile: AIProfile = AIProfile.local_ollama
    owner_commands: list[OwnerCommandDef] = Field(default_factory=list)


class RemoteCommandType(str, Enum):
    lock_system = "lock_system"
    restart_gateway = "restart_gateway"
    push_mission = "push_mission"


class RemoteCommand(BaseModel):
    id: str
    type: RemoteCommandType
    payload: dict[str, Any] = Field(default_factory=dict)


class ClientEventPayload(BaseModel):
    client_id: str
    event_type: str
    message: str
    meta: dict[str, Any] = Field(default_factory=dict)
