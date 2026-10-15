"""Tamper-evident audit log.

Each audit event stores ``hash = SHA-256(prev_hash || canonical_json(record))``.
Appends are serialised with a PostgreSQL transaction-scoped advisory lock so the
chain stays linear under concurrency. A database trigger (migration 0001)
rejects UPDATE and DELETE on the table.

Tamper *evidence* is not tamper *prevention*: a database superuser can disable
the trigger and rewrite the whole chain. Exporting the latest hash to separate
storage (see docs/security/security-controls.md) detects that case.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from drikr_api.models import AuditEvent, User, utcnow
from drikr_simcore.canonical import canonical_json

GENESIS_HASH = "0" * 64
AUDIT_LOCK_KEY = 7_311_002  # arbitrary, fixed advisory-lock key for the audit chain
_SENSITIVE = ("password", "token", "secret", "csrf", "hash", "cookie")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if any(s in k.lower() for s in _SENSITIVE) else _sanitize(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def _material(ev: AuditEvent) -> dict[str, Any]:
    return {
        "occurred_at": ev.occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
        "actor_id": str(ev.actor_id) if ev.actor_id else None,
        "actor_username": ev.actor_username,
        "action": ev.action,
        "target_type": ev.target_type,
        "target_id": ev.target_id,
        "details": ev.details,
        "ip_address": ev.ip_address,
        "prev_hash": ev.prev_hash,
    }


def compute_hash(ev: AuditEvent) -> str:
    return hashlib.sha256((ev.prev_hash + canonical_json(_material(ev))).encode("utf-8")).hexdigest()


def append_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    """Append an audit event inside the caller's transaction (committed with the change it records)."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
    prev = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)) or GENESIS_HASH
    ev = AuditEvent(
        occurred_at=utcnow(),
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=_sanitize(details or {}),
        ip_address=ip_address,
        prev_hash=prev,
    )
    ev.hash = compute_hash(ev)
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session, batch: int = 1000) -> dict[str, Any]:
    prev = GENESIS_HASH
    checked = 0
    last_id = 0
    while True:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.id > last_id).order_by(AuditEvent.id).limit(batch)).all()
        if not rows:
            break
        for ev in rows:
            checked += 1
            if ev.prev_hash != prev:
                return {
                    "valid": False,
                    "checked": checked,
                    "first_invalid_id": ev.id,
                    "reason": "prev_hash does not match preceding event",
                }
            if compute_hash(ev) != ev.hash:
                return {
                    "valid": False,
                    "checked": checked,
                    "first_invalid_id": ev.id,
                    "reason": "stored hash does not match record contents",
                }
            prev = ev.hash
            last_id = ev.id
    return {"valid": True, "checked": checked, "first_invalid_id": None, "reason": None, "head_hash": prev}
