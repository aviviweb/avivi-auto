from __future__ import annotations

from datetime import datetime
from pathlib import Path


def activity_log_path(workspace_root: Path) -> Path:
    return workspace_root / "Task_Logs" / "activity.log"


def append_activity(workspace_root: Path, message: str) -> None:
    p = activity_log_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H:%M")
    line = f"{ts} — {message}\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)


def read_activity_tail(workspace_root: Path, max_lines: int = 40) -> str:
    p = activity_log_path(workspace_root)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])
