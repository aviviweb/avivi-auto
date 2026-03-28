from __future__ import annotations

import json
from pathlib import Path

from openclaw_launcher.paths_openclaw import openclaw_skills_dir


def generate_all_db_bridge_skill_artifacts(
    skill_id: str,
    profile_id: str,
    bridge_host: str,
    bridge_port: int,
    engine_hint: str,
) -> list[Path]:
    """JSON + Python + JS stubs for the same bridge profile (all registered in openclaw.json)."""
    return [
        generate_db_bridge_skill_json(
            skill_id, profile_id, bridge_host, bridge_port, engine_hint
        ),
        generate_db_bridge_skill_python(skill_id, profile_id, bridge_host, bridge_port),
        generate_db_bridge_skill_js(skill_id, profile_id, bridge_host, bridge_port),
    ]


def generate_db_bridge_skill_json(
    skill_id: str,
    profile_id: str,
    bridge_host: str,
    bridge_port: int,
    engine_hint: str,
) -> Path:
    skills_dir = openclaw_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in skill_id)[:64]
    path = skills_dir / f"{safe}.json"
    payload = {
        "name": safe,
        "version": "1.0",
        "description": (
            f"DB via launcher bridge profile={profile_id} engine={engine_hint}. "
            "POST /query with profile_id and sql (SELECT only)."
        ),
        "type": "launcher_db_bridge",
        "launcher": {
            "bridge_url": f"http://{bridge_host}:{bridge_port}",
            "profile_id": profile_id,
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def generate_db_bridge_skill_python(
    skill_id: str,
    profile_id: str,
    bridge_host: str,
    bridge_port: int,
) -> Path:
    skills_dir = openclaw_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in skill_id)[:64]
    path = skills_dir / f"{safe}_bridge.py"
    pid_lit = json.dumps(profile_id)
    code = (
        f'"""Launcher DB bridge skill stub (read-only SELECT via HTTP). Skill id: {safe}"""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any\n\n"
        "import httpx\n\n"
        f'BRIDGE = "http://{bridge_host}:{bridge_port}"\n'
        f"PROFILE_ID = {pid_lit}\n\n\n"
        "def query_db(sql: str, timeout: float = 30.0) -> dict[str, Any]:\n"
        "    r = httpx.post(\n"
        '        f"{BRIDGE}/query",\n'
        '        json={"profile_id": PROFILE_ID, "sql": sql},\n'
        "        timeout=timeout,\n"
        "    )\n"
        "    r.raise_for_status()\n"
        "    return r.json()\n\n\n"
        "def main() -> None:\n"
        '    print(json.dumps(query_db("SELECT 1 AS ok"), indent=2))\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
    path.write_text(code, encoding="utf-8")
    return path


def generate_db_bridge_skill_js(
    skill_id: str,
    profile_id: str,
    bridge_host: str,
    bridge_port: int,
) -> Path:
    skills_dir = openclaw_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in skill_id)[:64]
    path = skills_dir / f"{safe}.js"
    pid = json.dumps(profile_id)
    code = (
        f"const BRIDGE = 'http://{bridge_host}:{bridge_port}';\n"
        f"const PROFILE_ID = {pid};\n"
        "export async function queryDb(sql) {\n"
        "  const r = await fetch(BRIDGE + '/query', {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify({ profile_id: PROFILE_ID, sql }),\n"
        "  });\n"
        "  if (!r.ok) throw new Error(await r.text());\n"
        "  return r.json();\n"
        "}\n"
    )
    path.write_text(code, encoding="utf-8")
    return path


def generate_task_manager_skill_bundle(workspace_root: Path) -> list[Path]:
    """JSON + Python helpers for Task_Logs/tasks.json (Smart Manager)."""
    tasks_path = (workspace_root / "Task_Logs" / "tasks.json").resolve()
    skills_dir = openclaw_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_id = "business_task_manager"
    json_path = skills_dir / f"{skill_id}.json"
    py_path = skills_dir / f"{skill_id}.py"
    tp_lit = json.dumps(str(tasks_path))

    payload = {
        "name": skill_id,
        "version": "1.0",
        "description": (
            "Maintain tasks.json with urgencies CRITICAL/HIGH/MEDIUM/LOW; "
            "use DB + conversation context; propose proactive owner messages."
        ),
        "type": "business_task_manager",
        "tasks_file": str(tasks_path),
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    code = (
        '"""Business AI task manager — read/write workspace Task_Logs/tasks.json."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        f"TASKS_FILE = Path({tp_lit})\n"
        "URGENCY_ORDER = ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')\n\n\n"
        "def _load() -> dict[str, Any]:\n"
        "    if not TASKS_FILE.exists():\n"
        '        return {"tasks": [], "updated_at": None}\n'
        "    return json.loads(TASKS_FILE.read_text(encoding='utf-8'))\n\n\n"
        "def _save(doc: dict[str, Any]) -> None:\n"
        "    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)\n"
        "    doc['updated_at'] = datetime.now(timezone.utc).isoformat()\n"
        "    TASKS_FILE.write_text(\n"
        "        json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8'\n"
        "    )\n\n\n"
        "def list_tasks() -> list[dict[str, Any]]:\n"
        '    return list(_load().get("tasks") or [])\n\n\n'
        "def upsert_task(task: dict[str, Any]) -> dict[str, Any]:\n"
        "    doc = _load()\n"
        '    tasks = list(doc.get("tasks") or [])\n'
        "    tid = str(task.get('id') or '')\n"
        "    if not tid:\n"
        "        raise ValueError('task.id required')\n"
        "    out: list[dict[str, Any]] = []\n"
        "    found = False\n"
        "    for t in tasks:\n"
        "        if str(t.get('id')) == tid:\n"
        "            merged = {**t, **task, 'id': tid}\n"
        "            out.append(merged)\n"
        "            found = True\n"
        "        else:\n"
        "            out.append(t)\n"
        "    if not found:\n"
        "        out.append({**task, 'id': tid})\n"
        '    doc["tasks"] = out\n'
        "    _save(doc)\n"
        "    return doc\n\n\n"
        "def top_by_urgency(limit: int = 5) -> list[dict[str, Any]]:\n"
        "    tasks = list_tasks()\n"
        "    rank = {u: i for i, u in enumerate(URGENCY_ORDER)}\n"
        "    def key(t: dict[str, Any]) -> tuple[int, str]:\n"
        "        u = str(t.get('urgency', 'LOW')).upper()\n"
        "        return (rank.get(u, 99), str(t.get('title', '')))\n"
        "    tasks.sort(key=key)\n"
        "    return tasks[:limit]\n"
    )
    py_path.write_text(code, encoding="utf-8")
    return [json_path, py_path]
