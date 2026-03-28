from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, Field


class OrchestrationRule(BaseModel):
    name: str
    profile_id: str
    agent_profile: str
    sql: str
    min_value: float = 0.0
    compare_column: str | None = None


class OrchestrationConfig(BaseModel):
    master_switch: bool = False
    poll_interval_sec: int = 60
    rules: list[OrchestrationRule] = Field(default_factory=list)


def load_orchestration(path: Path) -> OrchestrationConfig:
    if not path.exists():
        return OrchestrationConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return OrchestrationConfig.model_validate(data)


def save_orchestration(path: Path, cfg: OrchestrationConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def _first_metric(rows: list[dict], column: str | None) -> float | None:
    if not rows:
        return None
    row = rows[0]
    if column and column in row:
        v = row[column]
    else:
        v = next(iter(row.values()), None)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run_orchestration_tick(
    workspace_root: Path,
    orch: OrchestrationConfig,
    bridge_host: str,
    bridge_port: int,
) -> str | None:
    if not orch.master_switch or not orch.rules:
        return None
    base = f"http://{bridge_host}:{bridge_port}"
    active_path = workspace_root / "agents" / "active.json"
    profiles_dir = workspace_root / "agents" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30.0) as client:
        for rule in orch.rules:
            try:
                r = client.post(
                    f"{base}/query",
                    json={"profile_id": rule.profile_id, "sql": rule.sql},
                )
                if r.status_code != 200:
                    continue
                data = r.json()
                if not data.get("ok"):
                    continue
                rows = data.get("rows") or []
                metric = _first_metric(rows, rule.compare_column)
                if metric is None:
                    continue
                if metric > rule.min_value:
                    agent_file = profiles_dir / f"{rule.agent_profile}.json"
                    if not agent_file.exists():
                        agent_file.write_text(
                            json.dumps(
                                {"name": rule.agent_profile, "created_by": "launcher"},
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    payload = {
                        "active_profile": rule.agent_profile,
                        "rule": rule.name,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    active_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    return f"Switched to agent '{rule.agent_profile}' (rule: {rule.name})"
            except Exception:
                continue
    return None
