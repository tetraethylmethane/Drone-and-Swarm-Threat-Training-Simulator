"""Authentication: sign-in (with optional TOTP second step), sign-out, current user, password
change and multi-factor authentication management."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AppContext,
    Principal,
    client_ip,
    get_ctx,
    get_db,
    get_principal,
)
from drikr_api.errors import ApiError
from drikr_api.models import AuthSession, User, utcnow
from drikr_api.schemas import ChangePasswordRequest, LoginRequest, MfaCode, MfaDisable, MfaSetup, MfaVerify
from drikr_api.security.passwords import hash_password, needs_rehash, policy_violations, verify_password
from drikr_api.security.rbac import permissions_for
from drikr_api.security.tokens import new_token, token_digest
from drikr_api.serializers import user_out
from drikr_api.services import mfa_service

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_FAILURE = "Invalid username or password, or the account is temporarily locked"


def _me(db: Session, user: User) -> dict[str, Any]:
    required = mfa_service.required_for(db, user)
    return {
        **user_out(user),
        "permissions": permissions_for(user.role),
        "mfa_required": required,
        "mfa_enrollment_required": required and not user.mfa_enabled,
    }


def _secret(ctx: AppContext) -> str:
    return ctx.settings.secret_key.get_secret_value()


def _record_failure(db: Session, ctx: AppContext, user: User, ip: str | None, action: str) -> None:
    """Count a failed credential (password or second factor) towards the account lockout."""
    now = utcnow()
    user.failed_login_count += 1
    if user.failed_login_count >= ctx.settings.lockout_threshold:
        user.locked_until = now + timedelta(minutes=ctx.settings.lockout_minutes)
        user.failed_login_count = 0
        append_audit(
            db,
            actor=None,
            action="auth.account_locked",
            target_type="user",
            target_id=user.id,
            details={"username": user.username},
            ip_address=ip,
        )
    append_audit(db, actor=None, action=action, details={"username": user.username}, ip_address=ip)


def _issue_session(
    db: Session,
    ctx: AppContext,
    request: Request,
    response: Response,
    user: User,
    mode: str,
    ip: str | None,
    factors: str,
) -> dict[str, Any]:
    now = utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    secret = _secret(ctx)
    token = new_token()
    csrf = new_token() if mode == "cookie" else None
    expires = now + timedelta(minutes=ctx.settings.session_ttl_minutes)
    db.add(
        AuthSession(
            user_id=user.id,
            token_digest=token_digest(secret, token),
            csrf_digest=token_digest(secret, csrf) if csrf else None,
            kind="cookie" if mode == "cookie" else "bearer",
            expires_at=expires,
            last_seen_at=now,
            ip_address=ip,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    append_audit(
        db, actor=user, action="auth.login_succeeded", details={"mode": mode, "factors": factors}, ip_address=ip
    )
    db.commit()

    out: dict[str, Any] = {"mfa_required": False, "user": _me(db, user), "expires_at": expires.isoformat()}
    if mode == "cookie":
        max_age = ctx.settings.session_ttl_minutes * 60
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=max_age,
            httponly=True,
            secure=ctx.settings.cookie_secure,
            samesite="strict",
            path="/api",
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf or "",
            max_age=max_age,
            httponly=False,
            secure=ctx.settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        out["csrf_token"] = csrf
    else:
        out["access_token"] = token
        out["token_type"] = "bearer"  # noqa: S105 - token type label, not a secret
    return out


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Step 1. Returns a session, or ``{"mfa_required": true, "mfa_token": ...}`` when MFA is enabled."""
    ip = client_ip(request, ctx)
    username = body.username.lower()
    if not ctx.login_limiter.allow(f"ip:{ip}") or not ctx.login_limiter.allow(f"user:{username}"):
        raise ApiError(429, "rate_limited", "Too many sign-in attempts. Wait a minute and try again.")

    now = utcnow()
    user = db.scalar(select(User).where(User.username == username).with_for_update())
    ok = verify_password(user.password_hash if user else None, body.password)
    locked = bool(user and user.locked_until and user.locked_until > now)
    if user is None or not ok or locked or not user.is_active:
        if user is not None and not locked:
            _record_failure(db, ctx, user, ip, "auth.login_failed")
        else:
            append_audit(db, actor=None, action="auth.login_failed", details={"username": username[:64]}, ip_address=ip)
        db.commit()
        raise ApiError(401, "invalid_credentials", GENERIC_LOGIN_FAILURE)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    if user.mfa_enabled:
        token, ch = mfa_service.create_challenge(db, _secret(ctx), user, body.mode, ip)
        append_audit(db, actor=user, action="auth.mfa_challenge_issued", details={"mode": body.mode}, ip_address=ip)
        db.commit()
        return {"mfa_required": True, "mfa_token": token, "expires_at": ch.expires_at.isoformat()}

    return _issue_session(db, ctx, request, response, user, body.mode, ip, "password")


@router.post("/mfa/verify")
def mfa_verify(
    body: MfaVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Step 2. Exchange the challenge token and a TOTP or recovery code for a session."""
    ip = client_ip(request, ctx)
    if not ctx.login_limiter.allow(f"ip:{ip}"):
        raise ApiError(429, "rate_limited", "Too many sign-in attempts. Wait a minute and try again.")
    ch = mfa_service.load_challenge(db, _secret(ctx), body.mfa_token)
    user = db.scalar(select(User).where(User.id == ch.user_id).with_for_update())
    assert user is not None
    if not user.is_active or (user.locked_until and user.locked_until > utcnow()):
        ch.used_at = utcnow()
        db.commit()
        raise ApiError(401, "invalid_credentials", GENERIC_LOGIN_FAILURE)
    factor = mfa_service.check_code(db, _secret(ctx), user, body.code)
    if factor is None:
        ch.attempts += 1
        _record_failure(db, ctx, user, ip, "auth.mfa_failed")
        db.commit()
        raise ApiError(401, "mfa_code_invalid", "The verification code is not valid")
    ch.used_at = utcnow()
    if factor == "recovery":
        append_audit(
            db, actor=user, action="auth.mfa_recovery_code_used", target_type="user", target_id=user.id, ip_address=ip
        )
    return _issue_session(db, ctx, request, response, user, ch.mode, ip, f"password+{factor}")


@router.post("/logout")
def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    sess = db.get(AuthSession, principal.auth_session.id)
    if sess is not None:
        sess.revoked_at = utcnow()
    append_audit(db, actor=principal.user, action="auth.logout", ip_address=principal.ip)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/api")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "signed_out"}


@router.get("/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    return _me(db, principal.user)


def _revoke_other_sessions(db: Session, principal: Principal) -> None:
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == principal.user.id,
            AuthSession.id != principal.auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = db.get(User, principal.user.id)
    assert user is not None
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(400, "invalid_password", "Current password is incorrect")
    problems = policy_violations(body.new_password, user.username)
    if body.new_password == body.current_password:
        problems.append("must differ from the current password")
    if problems:
        raise ApiError(422, "password_policy", "New password does not meet the policy", problems)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    _revoke_other_sessions(db, principal)
    append_audit(
        db, actor=user, action="auth.password_changed", target_type="user", target_id=user.id, ip_address=principal.ip
    )
    db.commit()
    return _me(db, user)


# --- multi-factor authentication management -------------------------------------


@router.get("/mfa")
def mfa_status(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    u = principal.user
    return {
        "enabled": u.mfa_enabled,
        "enabled_at": u.mfa_enabled_at.isoformat() if u.mfa_enabled_at else None,
        "required": mfa_service.required_for(db, u),
        "recovery_codes_remaining": mfa_service.recovery_remaining(db, u) if u.mfa_enabled else 0,
    }


def _locked_user(db: Session, principal: Principal) -> User:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    assert user is not None
    return user


@router.post("/mfa/setup")
def mfa_setup(
    body: MfaSetup,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, str]:
    """Generate a new authenticator secret (re-authentication with the password is required)."""
    user = _locked_user(db, principal)
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(400, "invalid_password", "Current password is incorrect")
    out = mfa_service.begin_setup(db, _secret(ctx), user)
    db.commit()
    return out


@router.post("/mfa/enable")
def mfa_enable(
    body: MfaCode,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Confirm the authenticator with a current code; returns one-time recovery codes (shown once)."""
    user = _locked_user(db, principal)
    codes = mfa_service.enable(db, _secret(ctx), user, body.code)
    _revoke_other_sessions(db, principal)
    append_audit(
        db, actor=user, action="auth.mfa_enabled", target_type="user", target_id=user.id, ip_address=principal.ip
    )
    db.commit()
    return {"enabled": True, "recovery_codes": codes}


@router.post("/mfa/recovery-codes")
def mfa_regenerate(
    body: MfaCode,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    user = _locked_user(db, principal)
    if mfa_service.check_code(db, _secret(ctx), user, body.code) != "totp":
        raise ApiError(400, "mfa_code_invalid", "Enter a current code from your authenticator")
    codes = mfa_service.regenerate_codes(db, _secret(ctx), user)
    append_audit(
        db,
        actor=user,
        action="auth.mfa_recovery_codes_regenerated",
        target_type="user",
        target_id=user.id,
        ip_address=principal.ip,
    )
    db.commit()
    return {"recovery_codes": codes}


@router.post("/mfa/disable")
def mfa_disable(
    body: MfaDisable,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    user = _locked_user(db, principal)
    if mfa_service.required_for(db, user):
        raise ApiError(409, "mfa_required_by_policy", "Your role requires multi-factor authentication")
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(400, "invalid_password", "Current password is incorrect")
    if mfa_service.check_code(db, _secret(ctx), user, body.code) is None:
        raise ApiError(400, "mfa_code_invalid", "The verification code is not valid")
    mfa_service.clear(db, user)
    append_audit(
        db, actor=user, action="auth.mfa_disabled", target_type="user", target_id=user.id, ip_address=principal.ip
    )
    db.commit()
    return {"enabled": False}
