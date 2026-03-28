from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openclaw_launcher.paths_openclaw import openclaw_config_path, openclaw_home


def _default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "skills": [],
        "skill_paths": [],
        "context_files": [],
        "system_prompt_extensions": {},
        "channels": {},
        "launcher": {"managed_skill_ids": []},
    }


def load_openclaw_config() -> dict[str, Any]:
    p = openclaw_config_path()
    if not p.exists():
        return _default_config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_config()
        data.setdefault("skills", [])
        data.setdefault("skill_paths", [])
        data.setdefault("context_files", [])
        if not isinstance(data.get("context_files"), list):
            data["context_files"] = []
        data.setdefault("system_prompt_extensions", {})
        if not isinstance(data.get("system_prompt_extensions"), dict):
            data["system_prompt_extensions"] = {}
        data.setdefault("channels", {})
        if not isinstance(data.get("channels"), dict):
            data["channels"] = {}
        data.setdefault("launcher", {})
        data["launcher"].setdefault("managed_skill_ids", [])
        return data
    except (json.JSONDecodeError, OSError):
        return _default_config()


def register_context_files_in_openclaw_config(paths: list[Path]) -> None:
    """Append absolute paths for agent context (schema snapshots, etc.)."""
    if not paths:
        return
    openclaw_home().mkdir(parents=True, exist_ok=True)
    cfg = load_openclaw_config()
    lst = [str(p) for p in cfg.get("context_files") or [] if isinstance(p, str)]
    for p in paths:
        s = str(p.resolve())
        if s not in lst:
            lst.append(s)
    cfg["context_files"] = lst
    exts = cfg.get("system_prompt_extensions")
    if isinstance(exts, dict) and "database_schema" not in exts:
        exts["database_schema"] = (
            "Launcher registered database_mappings schema_context_* files in context_files."
        )
    openclaw_config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def register_skill_bundle_in_openclaw_config(paths: list[Path], skill_id: str) -> None:
    """Register multiple skill artifact paths (JSON, Python, JS) under one skill id."""
    if not paths:
        return
    openclaw_home().mkdir(parents=True, exist_ok=True)
    cfg = load_openclaw_config()
    resolved = [str(p.resolve()) for p in paths]
    skill_paths = list(cfg.get("skill_paths") or [])
    for sp in resolved:
        if sp not in skill_paths:
            skill_paths.append(sp)
    cfg["skill_paths"] = skill_paths
    skills_list = cfg.get("skills")
    if not isinstance(skills_list, list):
        skills_list = []
    entry = next(
        (x for x in skills_list if isinstance(x, dict) and x.get("id") == skill_id),
        None,
    )
    if entry:
        entry["path"] = resolved[0]
        entry["paths"] = resolved
        entry["enabled"] = True
    else:
        skills_list.append(
            {
                "id": skill_id,
                "path": resolved[0],
                "paths": resolved,
                "enabled": True,
            }
        )
    cfg["skills"] = skills_list
    managed = list(cfg["launcher"].get("managed_skill_ids") or [])
    if skill_id not in managed:
        managed.append(skill_id)
    cfg["launcher"]["managed_skill_ids"] = managed
    openclaw_config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def register_skill_in_openclaw_config(skill_path: Path, skill_id: str) -> None:
    register_skill_bundle_in_openclaw_config([skill_path], skill_id)


def sync_telegram_channel_to_openclaw_config(bot_token: str) -> None:
    """Merge Telegram bot token into openclaw.json channels (launcher onboarding)."""
    openclaw_home().mkdir(parents=True, exist_ok=True)
    cfg = load_openclaw_config()
    ch = cfg.setdefault("channels", {})
    if not isinstance(ch, dict):
        ch = {}
        cfg["channels"] = ch
    tok = bot_token.strip()
    tg = ch.setdefault("telegram", {})
    if not isinstance(tg, dict):
        tg = {}
        ch["telegram"] = tg
    tg["enabled"] = bool(tok)
    tg["bot_token"] = tok
    tg["provider"] = "telegram"
    openclaw_config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
