from __future__ import annotations

import base64

from avivi_shared.crypto import encrypt_json, fernet_from_key


def auth_blob(client_id: str, extra: dict | None = None) -> str:
    data = {"client_id": client_id}
    if extra:
        data.update(extra)
    return data


def encrypt_blob(client_id: str, fernet_key_b64: str, extra: dict | None = None) -> str:
    f = fernet_from_key(base64.b64decode(fernet_key_b64.encode("ascii")))
    raw = encrypt_json(auth_blob(client_id, extra), f)
    return base64.b64encode(raw).decode("ascii")
