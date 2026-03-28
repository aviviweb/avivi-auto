from __future__ import annotations

import os
from pathlib import Path


def default_workspace_root() -> Path:
    """
    Resolve workspace root (Business AI / AI_Manager layout).
    Priority: OPENCLAW_ROOT > BUSINESS_AI_ROOT > AI_MANAGER_ROOT > %LOCALAPPDATA%/AI_Manager
    (Legacy: set OPENCLAW_ROOT or BUSINESS_AI_ROOT for older Business_AI paths.)
    """
    for key in ("OPENCLAW_ROOT", "BUSINESS_AI_ROOT", "AI_MANAGER_ROOT"):
        env = os.environ.get(key, "").strip()
        if env:
            return Path(env).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or "."
    return Path(base) / "AI_Manager"


def workspace_paths(root: Path | None = None) -> dict[str, Path]:
    r = root or default_workspace_root()
    skills = r / "Skills"
    agents = r / "Agents"
    return {
        "root": r,
        "skills": skills,
        "skills_finance": skills / "Finance",
        "skills_sales": skills / "Sales",
        "skills_support": skills / "Support",
        "skills_ops": skills / "Operations",
        "skills_templates": skills / "_templates",
        "agents": agents,
        "agents_profiles": agents / "profiles",
        "backups": r / "Backups",
        "task_logs": r / "Task_Logs",
        "logs": r / "logs",
        "database_mappings": r / "database_mappings",
        "config": r / "config",
    }
