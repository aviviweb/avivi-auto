from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable


class ProcessWatchdog:
    """Background timer that detects subprocess death, clears cache, and invokes restart."""

    def __init__(
        self,
        get_proc: Callable[[], subprocess.Popen | None],
        on_restart: Callable[[], None],
        cache_dir: Path,
        interval: float = 2.0,
    ) -> None:
        from PyQt6.QtCore import QTimer

        self.get_proc = get_proc
        self.on_restart = on_restart
        self.cache_dir = cache_dir
        self.interval_ms = int(interval * 1000)
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._was_running = False
        self.on_recovery: Callable[[str], None] | None = None

    def start(self) -> None:
        self._timer.start(self.interval_ms)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        p = self.get_proc()
        if p is None:
            self._was_running = False
            return
        running = p.poll() is None
        if self._was_running and not running:
            try:
                if self.cache_dir.exists():
                    shutil.rmtree(self.cache_dir, ignore_errors=True)
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.on_restart()
            if self.on_recovery:
                self.on_recovery(f"Gateway restarted (exit {p.poll()})")
        self._was_running = running
