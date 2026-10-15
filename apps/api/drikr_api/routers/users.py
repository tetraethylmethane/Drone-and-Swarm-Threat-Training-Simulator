"""User administration (administrators) and trainee directory (instructors)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import Principal, get_db, require
from drikr_api.errors import ApiError, conflict, not_found
from drikr_api.models import AuthSession, Role, User, utcnow
from drikr_api.schemas import AnonymiseBody, PasswordReset, UserCreate, UserUpdate
from drikr_api.security.passwords import hash_password, policy_violations
from drikr_api.security.rbac import Permission
from drikr_api.serializers import page, user_out
from drikr_api.services import mfa_service, retention_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(
    role: Role | None = None,
    q: str | None = Query(default=None, max_length=64),
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require(Permission.USERS_MANAGE, Permission.USERS_READ_TRAINEES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(User)
    if not principal.can(Permission.USERS_MANAGE):
        # Instructors only see the active trainee directory.
        stmt = stmt.where(User.role == Role.TRAINEE, User.is_active.is_(True))
    else:
        if role is not None:
            stmt = stmt.where(User.role == role)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.display_name).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.display_name).limit(limit).offset(offset)).all()
    return page([user_out(u) for u in rows], total, limit, offset)


def _check_policy(password: str, username: str) -> None:
    problems = policy_violations(password, username)
    if problems:
        raise ApiError(422, "password_policy", "Password does not meet the policy", problems)


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _check_policy(body.password, body.username)
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise conflict("username_taken", "That username is already in use")
    user = User(
        username=body.username,
        display_name=body.display_name,
        role=body.role,
        password_hash=hash_password(body.password),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    append_audit(
        db,
        actor=principal.user,
        action="user.created",
        target_type="user",
        target_id=user.id,
        details={"username": user.username, "role": user.role.value},
        ip_address=principal.ip,
    )
    db.commit()
    return user_out(user)


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    u = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if u is None:
        raise not_found("User")
    return u


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).where(User.role == Role.ADMINISTRATOR, User.is_active.is_(True))) or 0


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    u = _get_user(db, user_id)
    changes: dict[str, Any] = {}
    removing_admin = u.role is Role.ADMINISTRATOR and (
        (body.role is not None and body.role is not Role.ADMINISTRATOR) or body.is_active is False
    )
    if removing_admin and u.id == principal.user.id:
        raise conflict("self_lockout", "You cannot remove your own administrator access")
    if removing_admin and _active_admins(db) <= 1:
        raise conflict("last_admin", "At least one active administrator must remain")
    if body.display_name is not None and body.display_name != u.display_name:
        changes["display_name"] = [u.display_name, body.display_name]
        u.display_name = body.display_name
    if body.role is not None and body.role is not u.role:
        changes["role"] = [u.role.value, body.role.value]
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        changes["is_active"] = [u.is_active, body.is_active]
        if u.anonymised_at is not None and body.is_active:
            raise conflict("anonymised", "Anonymised accounts cannot be reactivated")
        u.is_active = body.is_active
        u.deactivated_at = None if body.is_active else utcnow()
    if "role" in changes or changes.get("is_active") == [True, False]:
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    if changes:
        append_audit(
            db,
            actor=principal.user,
            action="user.updated",
            target_type="user",
            target_id=u.id,
            details=changes,
            ip_address=principal.ip,
        )
    db.commit()
    return user_out(u)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID,
    body: PasswordReset,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    u = _get_user(db, user_id)
    _check_policy(body.new_password, u.username)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = True
    u.failed_login_count = 0
    u.locked_until = None
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    append_audit(
        db,
        actor=principal.user,
        action="user.password_reset",
        target_type="user",
        target_id=u.id,
        ip_address=principal.ip,
    )
    db.commit()
    return user_out(u)


@router.post("/{user_id}/reset-mfa")
def reset_mfa(
    user_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Remove a user's authenticator and recovery codes (lost device). The user re-enrols at next sign-in."""
    u = _get_user(db, user_id)
    if u.id == principal.user.id:
        raise conflict("self_reset", "Use the account page to change your own multi-factor settings")
    had = u.mfa_enabled
    mfa_service.clear(db, u)
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    append_audit(
        db,
        actor=principal.user,
        action="user.mfa_reset",
        target_type="user",
        target_id=u.id,
        details={"was_enabled": had},
        ip_address=principal.ip,
    )
    db.commit()
    return user_out(u)


@router.post("/{user_id}/anonymise")
def anonymise(
    user_id: uuid.UUID,
    body: AnonymiseBody,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Irreversibly remove identifying data from a deactivated account (data-subject erasure)."""
    u = _get_user(db, user_id)
    if body.confirm_username != u.username:
        raise ApiError(422, "confirmation_mismatch", "Type the account's username to confirm")
    summary = retention_service.anonymise_user(db, u, principal.user, principal.ip)
    db.commit()
    return {**user_out(u), "anonymisation": summary}


@router.post("/{user_id}/unlock")
def unlock(
    user_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    u = _get_user(db, user_id)
    u.locked_until = None
    u.failed_login_count = 0
    append_audit(
        db, actor=principal.user, action="user.unlocked", target_type="user", target_id=u.id, ip_address=principal.ip
    )
    db.commit()
    return user_out(u)
