from __future__ import annotations

from pathlib import Path

from openclaw_launcher.config_model import DEFAULT_LAUNCHER_YAML
from openclaw_launcher.paths import workspace_paths


DEFAULT_ORCHESTRATION_YAML = """# Master switch and DB-driven agent rules
master_switch: false
poll_interval_sec: 60
rules:
  - name: new_leads_sales
    profile_id: default_pg
    agent_profile: sales_agent
    sql: "SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema = 'public' LIMIT 1"
    min_value: 0
"""

DEFAULT_ACTIVE_JSON = """{
  "active_profile": "default",
  "updated_at": null,
  "notes": "Updated by OpenClaw Launcher orchestration"
}
"""

SKILL_TEMPLATE = """---
name: "{skill_name}"
description: "Query business DB via local launcher bridge (no credentials in file)"
topic: "{topic}"
---

# Skill: {skill_name}

Use the launcher HTTP bridge at `http://127.0.0.1:{bridge_port}/query` with POST JSON:
```json
{{"profile_id": "<profile_id>", "sql": "SELECT ..."}}
```

Only read-only queries are allowed. Replace profile_id with a configured database profile.
"""


def ensure_workspace(root: Path | None = None) -> dict[str, Path]:
    root = root.resolve() if root else None
    from openclaw_launcher.paths import default_workspace_root

    r = root or default_workspace_root()
    paths = workspace_paths(r)
    for key in (
        "skills_finance",
        "skills_sales",
        "skills_support",
        "skills_ops",
        "skills_templates",
        "agents",
        "agents_profiles",
        "backups",
        "task_logs",
        "logs",
        "database_mappings",
        "config",
    ):
        paths[key].mkdir(parents=True, exist_ok=True)

    launcher_yaml = paths["config"] / "launcher.yaml"
    if not launcher_yaml.exists():
        launcher_yaml.write_text(DEFAULT_LAUNCHER_YAML, encoding="utf-8")

    orch = paths["config"] / "orchestration.yaml"
    if not orch.exists():
        orch.write_text(DEFAULT_ORCHESTRATION_YAML, encoding="utf-8")

    paths["agents"].mkdir(parents=True, exist_ok=True)
    active = paths["agents"] / "active.json"
    if not active.exists():
        active.write_text(DEFAULT_ACTIVE_JSON, encoding="utf-8")

    tpl = paths["skills_templates"] / "db_skill_template.md"
    if not tpl.exists():
        tpl.write_text(
            SKILL_TEMPLATE.format(skill_name="example_skill", topic="Operations", bridge_port=18765),
            encoding="utf-8",
        )

    profiles_meta = paths["database_mappings"] / "profiles_meta.yaml"
    if not profiles_meta.exists():
        profiles_meta.write_text(
            "profiles: []\n# Add profiles via Launcher UI; secrets stored in profiles.secrets.enc\n",
            encoding="utf-8",
        )

    tasks_json = paths["task_logs"] / "tasks.json"
    if not tasks_json.exists():
        tasks_json.write_text(
            '{\n  "tasks": [],\n  "updated_at": null,\n'
            '  "notes": "Managed by the Business AI task skill; urgency: CRITICAL|HIGH|MEDIUM|LOW"\n}\n',
            encoding="utf-8",
        )

    orch_md = paths["task_logs"] / "orchestrator_behavior.md"
    if not orch_md.exists():
        orch_md.write_text(
            """# Business AI Orchestrator — agent behavior

## Task management
- Maintain `tasks.json` via the task-manager skill. Each task: `id`, `title`, `urgency` (CRITICAL|HIGH|MEDIUM|LOW), `status`, `source`, `notes`, `updated_at`.
- Re-read the file before updates; merge carefully.

## Urgency engine
- Classify new work from **business conversations** and **DB signals** (e.g. low stock, stale leads).
- CRITICAL: revenue or safety risk. HIGH: time-sensitive customer issues. MEDIUM: operational. LOW: housekeeping.

## Proactive engagement
- When DB or conversation context implies action (e.g. stock low, unanswered leads), **initiate** a short message to the business owner proposing a concrete next step (e.g. draft restock order).
- Do not execute purchases without explicit owner approval unless policy says otherwise.
""",
            encoding="utf-8",
        )

    return paths
