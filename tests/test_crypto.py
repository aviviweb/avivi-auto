import base64

from avivi_shared.crypto import (
    decrypt_json,
    encrypt_json,
    fernet_from_key,
    generate_fernet_key,
    hmac_sha256_hex,
    verify_hmac_sha256,
)


def test_fernet_roundtrip():
    key = generate_fernet_key()
    f = fernet_from_key(key)
    obj = {"a": 1, "b": "x"}
    enc = encrypt_json(obj, f)
    assert decrypt_json(enc, f) == obj


def test_hmac():
    secret = b"secret"
    msg = b"payload"
    sig = hmac_sha256_hex(secret, msg)
    assert verify_hmac_sha256(secret, msg, sig)
    assert not verify_hmac_sha256(secret, msg, sig + "0")


def test_generate_key_length():
    key = generate_fernet_key()
    assert len(key) > 0
