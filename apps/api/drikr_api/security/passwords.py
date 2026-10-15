"""Password hashing (Argon2id) and password policy."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# OWASP-recommended Argon2id baseline (m=19 MiB, t=2, p=1) raised slightly for desktop servers.
_hasher = PasswordHasher(time_cost=3, memory_cost=19 * 1024, parallelism=1, hash_len=32, salt_len=16)

MIN_LENGTH = 12
MAX_LENGTH = 128

# Hash of a random value, used to equalise timing when the username does not exist.
_DUMMY_HASH = _hasher.hash("drikr-timing-equaliser-not-a-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def policy_violations(password: str, username: str) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"must be at most {MAX_LENGTH} characters")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("must contain at least three of: lowercase, uppercase, digit, symbol")
    if username and username.lower() in password.lower():
        problems.append("must not contain the username")
    return problems
