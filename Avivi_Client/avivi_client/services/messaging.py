from __future__ import annotations

import json
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class MessagingBackend(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def pairing_status(self) -> str: ...

    @abstractmethod
    def identity_label(self) -> str: ...

    @abstractmethod
    def send_text(self, to: str, text: str) -> None: ...

    def on_incoming(self, cb: Callable[[str, str], None]) -> None:
        self._on_incoming = cb  # noqa: SLF001

    @abstractmethod
    def latest_qr_base64(self) -> str | None: ...


class WebWhatsAppGateway(MessagingBackend):
    """Spawns Node bridge; reads JSON lines for qr / status / messages."""

    def __init__(self, bridge_dir: Path | None = None) -> None:
        self._bridge_dir = bridge_dir or Path(__file__).resolve().parent.parent / "node_bridge"
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._qr_b64: str | None = None
        self._status = "stopped"
        self._identity = ""
        self._on_incoming: Callable[[str, str], None] | None = None

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._proc is not None:
            self._proc = None
        script = self._bridge_dir / "index.js"
        if not script.exists():
            self._status = "bridge_missing"
            return
        node = "node"
        self._proc = subprocess.Popen(
            [node, str(script)],
            cwd=str(self._bridge_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._stop.clear()
        self._status = "starting"

        def read_loop() -> None:
            assert self._proc and self._proc.stdout
            for line in self._proc.stdout:
                if self._stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = msg.get("type")
                if t == "qr":
                    self._qr_b64 = msg.get("data")
                    self._status = "awaiting_scan"
                elif t == "ready":
                    self._status = "connected"
                    self._identity = msg.get("identity", "Business")
                elif t == "message" and self._on_incoming:
                    self._on_incoming(msg.get("from", ""), msg.get("body", ""))

        self._reader = threading.Thread(target=read_loop, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        self._status = "stopped"

    def pairing_status(self) -> str:
        return self._status

    def identity_label(self) -> str:
        return self._identity or "—"

    def send_text(self, to: str, text: str) -> None:
        if not self._proc or not self._proc.stdin:
            return
        try:
            payload = json.dumps({"cmd": "send", "to": to, "body": text}) + "\n"
            self._proc.stdin.write(payload)
            self._proc.stdin.flush()
        except Exception:
            pass

    def latest_qr_base64(self) -> str | None:
        return self._qr_b64


class CloudWhatsAppStub(MessagingBackend):
    """Placeholder for Meta Cloud API."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def pairing_status(self) -> str:
        return "cloud_api_not_configured"

    def identity_label(self) -> str:
        return "Cloud API"

    def send_text(self, to: str, text: str) -> None:
        raise NotImplementedError("Configure CloudWhatsApp backend")

    def latest_qr_base64(self) -> str | None:
        return None
