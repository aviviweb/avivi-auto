"""User-level OpenClaw paths (~/.openclaw)."""

from __future__ import annotations

from pathlib import Path


def openclaw_home() -> Path:
    return Path.home() / ".openclaw"


def openclaw_skills_dir() -> Path:
    return openclaw_home() / "skills"


def openclaw_config_path() -> Path:
    return openclaw_home() / "openclaw.json"
