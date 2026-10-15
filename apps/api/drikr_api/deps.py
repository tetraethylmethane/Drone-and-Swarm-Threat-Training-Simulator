"""Request dependencies: application context, database sessions, authentication and authorisation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.config import Settings
from drikr_api.db import Database
from drikr_api.errors import ApiError, forbidden
from drikr_api.models import AuthSession, Role, User, utcnow
from drikr_api.security.rate_limit import SlidingWindowLimiter
from drikr_api.security.rbac import Permission, has_permission
from drikr_api.security.tokens import constant_time_equal, token_digest
from drikr_api.services import mfa_service

SESSION_COOKIE = "drikr_session"
CSRF_COOKIE = "drikr_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LAST_SEEN_RESOLUTION = timedelta(seconds=30)


@dataclass
class AppContext:
    settings: Settings
    database: Database
    login_limiter: SlidingWindowLimiter
    action_limiter: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(600, 60))


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


def get_db(ctx: AppContext = Depends(get_ctx)) -> Iterator[Session]:
    yield from ctx.database.session()


def client_ip(request: Request, ctx: AppContext) -> str | None:
    if ctx.settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


@dataclass
class Principal:
    user: User
    auth_session: AuthSession
    ip: str | None

    @property
    def role(self) -> Role:
        return self.user.role

    def can(self, permission: Permission) -> bool:
        return has_permission(self.user.role, permission)


def _unauthorized(code: str = "unauthorized", message: str = "Authentication required") -> ApiError:
    return ApiError(401, code, message)


def get_principal(request: Request, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)) -> Principal:
    secret = ctx.settings.secret_key.get_secret_value()
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        token, kind = bearer[7:].strip(), "bearer"
    else:
        token, kind = request.cookies.get(SESSION_COOKIE, ""), "cookie"
    if not token:
        raise _unauthorized()

    sess = db.scalar(select(AuthSession).where(AuthSession.token_digest == token_digest(secret, token)))
    now = utcnow()
    if sess is None or sess.kind != kind or sess.revoked_at is not None:
        raise _unauthorized("session_invalid", "Session is invalid or has been signed out")
    if sess.expires_at <= now or sess.last_seen_at + timedelta(minutes=ctx.settings.session_idle_minutes) <= now:
        sess.revoked_at = now
        db.commit()
        raise _unauthorized("session_expired", "Session expired; sign in again")
    user = sess.user
    if not user.is_active:
        raise _unauthorized("account_disabled", "Account is disabled")

    if kind == "cookie" and request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if (
            not sent
            or sess.csrf_digest is None
            or not constant_time_equal(token_digest(secret, sent), sess.csrf_digest)
        ):
            raise ApiError(403, "csrf_failed", "Missing or invalid CSRF token")

    if now - sess.last_seen_at >= LAST_SEEN_RESOLUTION:
        sess.last_seen_at = now
        db.commit()
    return Principal(user=user, auth_session=sess, ip=client_ip(request, ctx))


def require(*permissions: Permission) -> Callable[..., Principal]:
    """Dependency factory: authenticated principal holding *any* of the given permissions."""

    def dependency(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Principal:
        if principal.user.must_change_password and permissions:
            raise ApiError(403, "password_change_required", "Change your password before continuing")
        if permissions and mfa_service.enrollment_pending(db, principal.user):
            raise ApiError(403, "mfa_enrollment_required", "Set up multi-factor authentication before continuing")
        if permissions and not any(principal.can(p) for p in permissions):
            raise forbidden()
        return principal

    return dependency
