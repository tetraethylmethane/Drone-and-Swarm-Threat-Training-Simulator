"""TOTP (RFC 6238) and secret sealing."""

from __future__ import annotations

import base64

import pytest

from drikr_api.security import totp
from drikr_api.security.secretbox import SecretBoxError, open_, seal

# RFC 6238 Appendix B, SHA-1 key "12345678901234567890", 8-digit codes.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize(("t", "code"), RFC_VECTORS)
def test_rfc6238_vectors(t: int, code: str) -> None:
    assert totp.code_at(RFC_SECRET, t, digits=8) == code


def test_verify_window_and_replay() -> None:
    secret = totp.new_secret()
    t = 1_700_000_000
    code = totp.code_at(secret, t)
    step = totp.verify(secret, code, at=t)
    assert step == t // 30
    assert totp.verify(secret, code, at=t + 30) == step  # one step of drift accepted
    assert totp.verify(secret, code, at=t + 90) is None  # outside the window
    assert totp.verify(secret, code, at=t, last_step=step) is None  # replay rejected
    assert totp.verify(secret, "12345", at=t) is None
    assert totp.verify(secret, "abcdef", at=t) is None


def test_secret_has_160_bits_and_uri() -> None:
    s = totp.new_secret()
    assert len(base64.b32decode(s + "=" * (-len(s) % 8))) == 20
    uri = totp.provisioning_uri(s, "trainee1")
    assert uri.startswith("otpauth://totp/Drikr%20Systems%3Atrainee1?") and f"secret={s}" in uri


def test_secretbox_roundtrip_and_tamper() -> None:
    key = "k" * 40
    sealed = seal(key, "purpose", "JBSWY3DPEHPK3PXP", associated="user-1")
    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert open_(key, "purpose", sealed, associated="user-1") == "JBSWY3DPEHPK3PXP"
    assert seal(key, "purpose", "x", "u") != seal(key, "purpose", "x", "u")  # random nonce
    for bad in (
        lambda: open_("other" * 10, "purpose", sealed, "user-1"),  # wrong key
        lambda: open_(key, "purpose", sealed, "user-2"),  # bound to the user id
        lambda: open_(key, "other", sealed, "user-1"),  # wrong purpose
        lambda: open_(key, "purpose", sealed[:-4] + "AAAA", "user-1"),  # tampered
    ):
        with pytest.raises(SecretBoxError):
            bad()
