"""Authenticated encryption of small secrets at rest (MFA seeds) with AES-256-GCM.

The key is derived with HKDF-SHA256 from ``DRIKR_SECRET_KEY`` and a purpose label, so a database
dump alone does not reveal authenticator seeds. Rotating ``DRIKR_SECRET_KEY`` makes stored MFA
seeds undecryptable; administrators then reset MFA for affected users (documented in the
administrator guide).
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = b"v1"


class SecretBoxError(ValueError):
    pass


def _key(master: str, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"drikr-secretbox", info=purpose.encode()).derive(
        master.encode()
    )


def seal(master: str, purpose: str, plaintext: str, associated: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key(master, purpose)).encrypt(nonce, plaintext.encode(), associated.encode())
    return VERSION.decode() + ":" + base64.urlsafe_b64encode(nonce + ct).decode()


def open_(master: str, purpose: str, sealed: str, associated: str) -> str:
    try:
        version, payload = sealed.split(":", 1)
        if version.encode() != VERSION:
            raise SecretBoxError("unsupported secret version")
        raw = base64.urlsafe_b64decode(payload.encode())
        return AESGCM(_key(master, purpose)).decrypt(raw[:12], raw[12:], associated.encode()).decode()
    except (InvalidTag, ValueError) as exc:
        raise SecretBoxError("secret cannot be decrypted (wrong key or tampered value)") from exc
