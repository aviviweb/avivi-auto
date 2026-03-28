from __future__ import annotations

import os
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from openclaw_launcher.config_model import GatewayConfig

if TYPE_CHECKING:
    from openclaw_launcher.services.recovery import RecoveryOrchestrator


class GatewayState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class GatewaySupervisor:
    """Runs OpenClaw gateway as subprocess; detects exit and triggers recovery."""

    def __init__(
        self,
        gateway_cfg: GatewayConfig,
        on_crash: Callable[[str], None] | None = None,
    ) -> None:
        self.cfg = gateway_cfg
        self._proc: subprocess.Popen[str] | None = None
        self._on_crash = on_crash
        self._was_running = False
        self._state = GatewayState.STOPPED

    @property
    def state(self) -> GatewayState:
        return self._state

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._proc

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> tuple[bool, str]:
        if self.is_running():
            return True, "already running"
        cmd = self.cfg.command
        if not cmd:
            self._state = GatewayState.ERROR
            return False, "gateway.command is empty"
        cwd = Path(self.cfg.cwd).expanduser() if self.cfg.cwd else None
        env = os.environ.copy()
        env.update(self.cfg.env)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._state = GatewayState.STARTING
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                creationflags=creationflags,
            )
            self._was_running = True
            self._state = GatewayState.RUNNING
            return True, f"started pid={self._proc.pid}"
        except Exception as e:
            self._proc = None
            self._state = GatewayState.ERROR
            return False, str(e)

    def stop(self) -> None:
        if self._proc is None:
            self._state = GatewayState.STOPPED
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        except Exception:
            pass
        self._proc = None
        self._was_running = False
        self._state = GatewayState.STOPPED

    def tick(self) -> str | None:
        """Call periodically; returns crash reason or None."""
        if self._proc is None:
            return None
        code = self._proc.poll()
        if code is None:
            self._was_running = True
            self._state = GatewayState.RUNNING
            return None
        if self._was_running:
            self._was_running = False
            reason = f"gateway exited with code {code}"
            self._proc = None
            self._state = GatewayState.ERROR
            if self._on_crash:
                self._on_crash(reason)
            return reason
        return None
