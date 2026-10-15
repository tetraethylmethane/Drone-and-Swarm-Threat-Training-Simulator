"""Multi-factor authentication: TOTP enrolment, verification, recovery codes and sign-in challenges.

Sign-in with MFA is two steps: a correct password yields a short-lived, single-use challenge token;
the session is only issued after a valid TOTP or recovery code is presented for that challenge.
"""

from __future__ import annotations

import base64
import secrets
from datetime import timedelta
from typing import Literal

import segno
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from drikr_api.errors import ApiError
from drikr_api.models import MfaChallenge, MfaRecoveryCode, User, utcnow
from drikr_api.security import totp
from drikr_api.security.secretbox import SecretBoxError, open_, seal
from drikr_api.security.tokens import new_token, token_digest
from drikr_api.services import settings_service

PURPOSE = "mfa-totp-seed"
CHALLENGE_TTL = timedelta(minutes=5)
MAX_CHALLENGE_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L, U


def required_for(db: Session, user: User) -> bool:
    return user.role.value in settings_service.get_all(db)["mfa_required_roles"]


def enrollment_pending(db: Session, user: User) -> bool:
    return required_for(db, user) and not user.mfa_enabled


def _seal(secret_key: str, user: User, value: str) -> str:
    return seal(secret_key, PURPOSE, value, associated=str(user.id))


def _open(secret_key: str, user: User, sealed: str) -> str:
    try:
        return open_(secret_key, PURPOSE, sealed, associated=str(user.id))
    except SecretBoxError as exc:
        raise ApiError(
            409, "mfa_unreadable", "Stored MFA secret cannot be read; an administrator must reset MFA"
        ) from exc


def qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#1B1F1D", light="#FFFFFF")


def begin_setup(db: Session, secret_key: str, user: User) -> dict[str, str]:
    if user.mfa_enabled:
        raise ApiError(409, "mfa_already_enabled", "Multi-factor authentication is already enabled")
    secret = totp.new_secret()
    user.mfa_pending_secret_enc = _seal(secret_key, user, secret)
    uri = totp.provisioning_uri(secret, user.username)
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg_base64": base64.b64encode(qr_svg(uri).encode()).decode(),
    }


def _new_recovery_codes(db: Session, secret_key: str, user: User) -> list[str]:
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
        db.add(MfaRecoveryCode(user_id=user.id, code_digest=token_digest(secret_key, raw)))
    return codes


def enable(db: Session, secret_key: str, user: User, code: str) -> list[str]:
    if user.mfa_enabled:
        raise ApiError(409, "mfa_already_enabled", "Multi-factor authentication is already enabled")
    if not user.mfa_pending_secret_enc:
        raise ApiError(409, "mfa_setup_required", "Start MFA setup first")
    secret = _open(secret_key, user, user.mfa_pending_secret_enc)
    step = totp.verify(secret, code)
    if step is None:
        raise ApiError(400, "mfa_code_invalid", "The code is not valid; check the authenticator time and try again")
    user.mfa_secret_enc = _seal(secret_key, user, secret)
    user.mfa_pending_secret_enc = None
    user.mfa_enabled_at = utcnow()
    user.mfa_last_step = step
    return _new_recovery_codes(db, secret_key, user)


def check_code(db: Session, secret_key: str, user: User, code: str) -> Literal["totp", "recovery"] | None:
    """Verify a TOTP or unused recovery code. Consumes recovery codes; rejects TOTP replays."""
    if not user.mfa_enabled or not user.mfa_secret_enc:
        return None
    cleaned = code.strip().replace(" ", "").upper()
    if cleaned.isdigit():
        step = totp.verify(_open(secret_key, user, user.mfa_secret_enc), cleaned, last_step=user.mfa_last_step)
        if step is None:
            return None
        user.mfa_last_step = step
        return "totp"
    raw = cleaned.replace("-", "")
    if len(raw) != 10:
        return None
    rc = db.scalar(
        select(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.code_digest == token_digest(secret_key, raw),
            MfaRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    )
    if rc is None:
        return None
    rc.used_at = utcnow()
    return "recovery"


def recovery_remaining(db: Session, user: User) -> int:
    return (
        db.scalar(select(func.count()).where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None)))
        or 0
    )


def regenerate_codes(db: Session, secret_key: str, user: User) -> list[str]:
    return _new_recovery_codes(db, secret_key, user)


def clear(db: Session, user: User) -> None:
    user.mfa_secret_enc = None
    user.mfa_pending_secret_enc = None
    user.mfa_enabled_at = None
    user.mfa_last_step = None
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    db.execute(delete(MfaChallenge).where(MfaChallenge.user_id == user.id))


def create_challenge(db: Session, secret_key: str, user: User, mode: str, ip: str | None) -> tuple[str, MfaChallenge]:
    token = new_token()
    ch = MfaChallenge(
        user_id=user.id,
        token_digest=token_digest(secret_key, token),
        mode=mode,
        expires_at=utcnow() + CHALLENGE_TTL,
        ip_address=ip,
    )
    db.add(ch)
    db.flush()
    return token, ch


def load_challenge(db: Session, secret_key: str, token: str) -> MfaChallenge:
    ch = db.scalar(
        select(MfaChallenge).where(MfaChallenge.token_digest == token_digest(secret_key, token)).with_for_update()
    )
    if ch is None or ch.used_at is not None or ch.expires_at <= utcnow() or ch.attempts >= MAX_CHALLENGE_ATTEMPTS:
        raise ApiError(401, "mfa_challenge_invalid", "The sign-in attempt has expired; sign in again")
    return ch
