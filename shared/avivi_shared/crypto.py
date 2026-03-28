from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def generate_fernet_key() -> bytes:
    return Fernet.generate_key()


def fernet_from_key(key: bytes | str) -> Fernet:
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_json(obj: Any, fernet: Fernet) -> bytes:
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(payload)


def decrypt_json(data: bytes, fernet: Fernet) -> Any:
    raw = fernet.decrypt(data)
    return json.loads(raw.decode("utf-8"))


def encrypt_bytes(data: bytes, fernet: Fernet) -> bytes:
    return fernet.encrypt(data)


def decrypt_bytes(data: bytes, fernet: Fernet) -> bytes:
    return fernet.decrypt(data)


def hmac_sha256_hex(secret: bytes, message: bytes) -> str:
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_hmac_sha256(secret: bytes, message: bytes, signature_hex: str) -> bool:
    expected = hmac_sha256_hex(secret, message)
    return hmac.compare_digest(expected, signature_hex)


def fernet_from_machine_pepper(pepper: str = "avivi-client-v1") -> Fernet:
    return Fernet(fernet_from_machine_pepper_key(pepper))


def fernet_from_machine_pepper_key(pepper: str = "avivi-client-v1") -> bytes:
    """Return a valid Fernet key derived from machine context."""
    raw = hashlib.sha256((pepper + "|" + os.environ.get("COMPUTERNAME", "pc")).encode()).digest()
    return base64.urlsafe_b64encode(raw)


__all__ = [
    "Fernet",
    "InvalidToken",
    "generate_fernet_key",
    "fernet_from_key",
    "encrypt_json",
    "decrypt_json",
    "encrypt_bytes",
    "decrypt_bytes",
    "hmac_sha256_hex",
    "verify_hmac_sha256",
    "fernet_from_machine_pepper",
    "fernet_from_machine_pepper_key",
]
