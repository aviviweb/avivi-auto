from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class WorkspaceConfig(BaseModel):
    """Optional absolute path override; if null, use OPENCLAW_ROOT / BUSINESS_AI_ROOT / default."""

    root: str | None = None


class GatewayConfig(BaseModel):
    command: list[str] = Field(default_factory=lambda: ["openclaw", "gateway"])
    cwd: str | None = None
    readiness_timeout_sec: int = 120
    env: dict[str, str] = Field(default_factory=dict)


class RecoveryConfig(BaseModel):
    cache_dirs: list[str] = Field(
        default_factory=lambda: [str(Path.home() / ".openclaw" / "cache")]
    )
    process_name_substrings: list[str] = Field(default_factory=lambda: ["openclaw"])
    telegram_failures_before_recovery: int = 5


class LoggingConfig(BaseModel):
    recovery_log_max_mb: float = 10.0


class DbBridgeConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 18765


class LauncherSettings(BaseModel):
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    db_bridge: DbBridgeConfig = Field(default_factory=DbBridgeConfig)
    telegram_bot_token: str = ""

    def resolved_workspace_root(self) -> Path:
        if self.workspace.root and str(self.workspace.root).strip():
            return Path(self.workspace.root).expanduser().resolve()
        from openclaw_launcher.paths import default_workspace_root

        return default_workspace_root()

    @classmethod
    def load(cls, path: Path) -> LauncherSettings:
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(mode="json"), default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )


DEFAULT_LAUNCHER_YAML = """# OpenClaw Launcher — Business AI Orchestrator workspace (Skills/Agents/Task_Logs/Backups)
# Optional: set workspace.root to override OPENCLAW_ROOT / BUSINESS_AI_ROOT / AI_MANAGER_ROOT / default %LOCALAPPDATA%/AI_Manager
workspace:
  root: null

gateway:
  command:
    - openclaw
    - gateway
  cwd: null
  readiness_timeout_sec: 120
  env: {}

recovery:
  cache_dirs:
    - ~/.openclaw/cache
  process_name_substrings:
    - openclaw
  telegram_failures_before_recovery: 5

logging:
  recovery_log_max_mb: 10

db_bridge:
  host: 127.0.0.1
  port: 18765

# Plain token optional if stored encrypted in config/launcher_secrets.enc
telegram_bot_token: ""
"""
