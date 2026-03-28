from __future__ import annotations

import base64
from datetime import datetime, timezone

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

from avivi_client.config import ClientSettings
from avivi_shared.crypto import encrypt_json, fernet_from_key
from avivi_shared.models import HeartbeatPayload


class HeartbeatWorker(QThread):
    status_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        client_id: str,
        fernet_key_b64: str,
        settings: ClientSettings,
        interval_sec: int = 30,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.fernet_key_b64 = fernet_key_b64
        self.settings = settings
        self.interval_sec = interval_sec
        self._stop = False
        self.capabilities: dict = {}

    def stop(self) -> None:
        self._stop = True

    def set_capabilities(self, caps: dict) -> None:
        self.capabilities = dict(caps)

    def run(self) -> None:
        import time

        while not self._stop:
            try:
                f = fernet_from_key(base64.b64decode(self.fernet_key_b64.encode("ascii")))
                oc = (self.settings.owner_telegram_chat_id or "").strip() or None
                hb = HeartbeatPayload(
                    client_id=self.client_id,
                    hostname=__import__("socket").gethostname(),
                    app_version=self.settings.app_version,
                    license_status=self.settings.license_status,
                    build_channel=self.settings.build_channel,
                    owner_telegram_chat_id=oc,
                    capabilities=self.capabilities,
                    ts=datetime.now(timezone.utc),
                )
                raw = encrypt_json(hb.model_dump(mode="json"), f)
                env = {
                    "client_id": self.client_id,
                    "ciphertext_b64": base64.b64encode(raw).decode("ascii"),
                }
                with httpx.Client(timeout=20.0) as client:
                    r = client.post(f"{self.base_url}/v1/heartbeat", json=env)
                    r.raise_for_status()
                    self.status_signal.emit(r.json())
            except Exception as e:
                self.error_signal.emit(str(e))
            for _ in range(self.interval_sec):
                if self._stop:
                    break
                time.sleep(1)
