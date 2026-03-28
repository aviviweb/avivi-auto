from __future__ import annotations

import base64
import uuid

from avivi_shared.crypto import generate_fernet_key
from avivi_shared.models import EnrollResponse


def new_enroll_bundle() -> EnrollResponse:
    fkey = generate_fernet_key()
    hmac_secret = generate_fernet_key()
    client_id = str(uuid.uuid4())
    return EnrollResponse(
        client_id=client_id,
        fernet_key_b64=base64.b64encode(fkey).decode("ascii"),
        hmac_secret_b64=base64.b64encode(hmac_secret).decode("ascii"),
    )
