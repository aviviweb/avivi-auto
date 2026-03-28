from __future__ import annotations

import base64
import hashlib
import os
from datetime import date
from pathlib import Path

from cryptography.fernet import Fernet

from openclaw_launcher.paths_openclaw import openclaw_config_path


def _openclaw_backup_fernet() -> Fernet:
    """Fernet key for ~/.openclaw/openclaw.json daily backups (machine-local)."""
    raw = hashlib.sha256(
        (os.environ.get("COMPUTERNAME", "pc") + "|openclaw-json-backup-v1").encode()
    ).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def maybe_run_daily_openclaw_backup(backups_dir: Path) -> str | None:
    """
    If calendar day changed since last run, encrypt openclaw.json to Backups/openclaw_YYYYMMDD.enc.
    Returns a short status message or None if skipped.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    marker = backups_dir / ".last_openclaw_backup_date"
    today = date.today().isoformat()
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
        return None
    src = openclaw_config_path()
    if not src.exists():
        marker.write_text(today, encoding="utf-8")
        return None
    ymd = today.replace("-", "")
    out = backups_dir / f"openclaw_{ymd}.enc"
    f = _openclaw_backup_fernet()
    out.write_bytes(f.encrypt(src.read_bytes()))
    marker.write_text(today, encoding="utf-8")
    return f"Encrypted backup: {out.name}"
