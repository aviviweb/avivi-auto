import base64
import os
import tempfile
from pathlib import Path

_fd, _test_db = tempfile.mkstemp(suffix="_avivi_test.db")
os.close(_fd)
os.environ["AVIVI_DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_test_db).as_posix()}"

from fastapi.testclient import TestClient

from avivi_master.main import app
from avivi_shared.crypto import encrypt_json, fernet_from_key
from avivi_shared.models import EnrollRequest, HeartbeatPayload


def test_enroll_and_heartbeat():
    with TestClient(app) as client:
        r = client.post(
            "/v1/enroll",
            json=EnrollRequest(hostname="test-host", app_version="0.1.0").model_dump(),
        )
        assert r.status_code == 200
        body = r.json()
        cid = body["client_id"]
        fk = body["fernet_key_b64"]
        f = fernet_from_key(base64.b64decode(fk.encode("ascii")))
        hb = HeartbeatPayload(
            client_id=cid,
            hostname="test-host",
            app_version="0.1.0",
            license_status="trial",
            capabilities={},
        )
        raw = encrypt_json(hb.model_dump(mode="json"), f)
        env = {"client_id": cid, "ciphertext_b64": base64.b64encode(raw).decode("ascii")}
        h = client.post("/v1/heartbeat", json=env)
        assert h.status_code == 200
        assert h.json().get("ok") is True
