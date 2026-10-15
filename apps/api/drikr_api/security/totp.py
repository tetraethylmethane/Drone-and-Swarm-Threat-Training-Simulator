"""Time-based one-time passwords (RFC 6238, HMAC-SHA1, 6 digits, 30 s), compatible with
standard authenticator apps. Verification accepts one step of clock drift either side and
returns the matched step so callers can reject replays."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_S = 30
DIGITS = 6
ISSUER = "Drikr Systems"


def new_secret() -> str:
    """160-bit secret, base32 without padding (RFC 4226 recommends at least 128 bits)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def code_at(secret_b32: str, at: float, digits: int = DIGITS) -> str:
    return hotp(_key(secret_b32), int(at // STEP_S), digits)


def verify(
    secret_b32: str, code: str, *, at: float | None = None, window: int = 1, last_step: int | None = None
) -> int | None:
    """Return the matching time step, or None. Steps at or before ``last_step`` are rejected (replay)."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = time.time() if at is None else at
    current = int(now // STEP_S)
    key = _key(secret_b32)
    for step in range(current - window, current + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(hotp(key, step), code):
            return step
    return None


def provisioning_uri(secret_b32: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    query = urlencode({"secret": secret_b32, "issuer": ISSUER, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_S})
    return f"otpauth://totp/{label}?{query}"


def hashlib_available() -> bool:  # pragma: no cover - environment guard
    return "sha1" in hashlib.algorithms_available
