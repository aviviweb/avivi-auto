from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import psutil

log = logging.getLogger(__name__)


class RecoveryOrchestrator:
    """Kill gateway-related processes, clear caches, restart via callback; log to recovery.log."""

    def __init__(
        self,
        recovery_log: Path,
        cache_dirs: list[str],
        process_name_substrings: list[str],
        max_log_mb: float = 10.0,
    ) -> None:
        self.recovery_log = recovery_log
        self.cache_dirs = cache_dirs
        self.process_name_substrings = [s.lower() for s in process_name_substrings]
        self.max_log_mb = max_log_mb

    def _rotate_log_if_needed(self) -> None:
        if not self.recovery_log.exists():
            return
        mb = self.recovery_log.stat().st_size / (1024 * 1024)
        if mb >= self.max_log_mb:
            backup = self.recovery_log.with_suffix(".log.old")
            try:
                if backup.exists():
                    backup.unlink()
                self.recovery_log.rename(backup)
            except OSError:
                self.recovery_log.write_text("", encoding="utf-8")

    def append_log(self, message: str, reason: str = "info") -> None:
        self._rotate_log_if_needed()
        self.recovery_log.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts}\t{reason}\t{message}\n"
        with self.recovery_log.open("a", encoding="utf-8") as f:
            f.write(line)
        log.info("recovery.log: %s", line.strip())

    def clear_caches(self) -> None:
        for d in self.cache_dirs:
            p = Path(d).expanduser()
            if p.exists():
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    p.mkdir(parents=True, exist_ok=True)
                    self.append_log(f"Cleared cache: {p}", "cache_clear")
                except Exception as e:
                    self.append_log(f"Cache clear failed {p}: {e}", "error")

    def kill_matching_processes(self, exclude_pids: set[int] | None = None) -> int:
        exclude = exclude_pids or set()
        killed = 0
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = proc.info["pid"]
                if pid in exclude or pid is None:
                    continue
                name = (proc.info.get("name") or "").lower()
                cmdline = proc.info.get("cmdline") or []
                blob = name + " " + " ".join(cmdline).lower()
                if any(sub in blob for sub in self.process_name_substrings):
                    p = psutil.Process(pid)
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        p.kill()
                    killed += 1
                    self.append_log(f"Terminated pid={pid} name={name}", "kill")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return killed

    def run_recovery(
        self,
        reason: str,
        restart: Callable[[], None],
        launcher_pid: int | None = None,
    ) -> None:
        self.append_log(f"Recovery started: {reason}", "recovery_start")
        excl = {launcher_pid} if launcher_pid else set()
        try:
            import os

            excl.add(os.getpid())
        except Exception:
            pass
        self.kill_matching_processes(exclude_pids=excl)
        self.clear_caches()
        try:
            restart()
            self.append_log("Restart callback completed", "recovery_end")
        except Exception as e:
            self.append_log(f"Restart failed: {e}", "error")
