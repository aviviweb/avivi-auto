from __future__ import annotations

from pathlib import Path

from openclaw_launcher.services.openclaw_config import (
    register_context_files_in_openclaw_config,
    register_skill_bundle_in_openclaw_config,
)
from openclaw_launcher.services.skill_generator import generate_task_manager_skill_bundle


def ensure_task_manager_skill_registered(workspace_root: Path) -> None:
    """Idempotent: (re)write task skill artifacts and register in openclaw.json + behavior context."""
    paths = generate_task_manager_skill_bundle(workspace_root)
    register_skill_bundle_in_openclaw_config(paths, "business_task_manager")
    behavior = workspace_root / "Task_Logs" / "orchestrator_behavior.md"
    if behavior.exists():
        register_context_files_in_openclaw_config([behavior])
