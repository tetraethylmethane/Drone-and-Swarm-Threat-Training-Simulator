"""Role-based access control policy.

Permissions are checked on the backend for every request. Object-level rules
(for example, a trainee may only read their own sessions) are enforced in the
routers through ``ensure_*`` helpers in ``drikr_api.deps``.
"""

from __future__ import annotations

from enum import StrEnum

from drikr_api.models import Role


class Permission(StrEnum):
    USERS_MANAGE = "users:manage"
    USERS_READ_TRAINEES = "users:read_trainees"
    SETTINGS_MANAGE = "settings:manage"
    SYSTEM_HEALTH = "system:health"
    AUDIT_READ = "audit:read"

    SCENARIOS_READ = "scenarios:read"
    SCENARIOS_WRITE = "scenarios:write"
    RUBRICS_READ = "rubrics:read"
    RUBRICS_WRITE = "rubrics:write"

    ASSIGNMENTS_MANAGE = "assignments:manage"
    ASSIGNMENTS_READ_OWN = "assignments:read_own"

    SESSIONS_PARTICIPATE = "sessions:participate"
    SESSIONS_READ_ALL = "sessions:read_all"
    SESSIONS_READ_OWN = "sessions:read_own"
    SESSIONS_ABORT = "sessions:abort"
    SESSIONS_VERIFY = "sessions:verify"

    REVIEWS_WRITE = "reviews:write"
    ANALYTICS_READ_ALL = "analytics:read_all"
    ANALYTICS_READ_OWN = "analytics:read_own"
    REPORTS_EXPORT = "reports:export"
    REPORTS_EXPORT_OWN = "reports:export_own"


P = Permission

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMINISTRATOR: frozenset(
        {
            P.USERS_MANAGE,
            P.USERS_READ_TRAINEES,
            P.SETTINGS_MANAGE,
            P.SYSTEM_HEALTH,
            P.AUDIT_READ,
            P.SCENARIOS_READ,
            P.RUBRICS_READ,
            P.SESSIONS_READ_ALL,
            P.SESSIONS_ABORT,
            P.SESSIONS_VERIFY,
            P.ANALYTICS_READ_ALL,
            P.REPORTS_EXPORT,
        }
    ),
    Role.INSTRUCTOR: frozenset(
        {
            P.USERS_READ_TRAINEES,
            P.SCENARIOS_READ,
            P.SCENARIOS_WRITE,
            P.RUBRICS_READ,
            P.RUBRICS_WRITE,
            P.ASSIGNMENTS_MANAGE,
            P.SESSIONS_READ_ALL,
            P.SESSIONS_ABORT,
            P.SESSIONS_VERIFY,
            P.REVIEWS_WRITE,
            P.ANALYTICS_READ_ALL,
            P.REPORTS_EXPORT,
        }
    ),
    Role.TRAINEE: frozenset(
        {
            P.SCENARIOS_READ,
            P.ASSIGNMENTS_READ_OWN,
            P.SESSIONS_PARTICIPATE,
            P.SESSIONS_READ_OWN,
            P.ANALYTICS_READ_OWN,
            P.REPORTS_EXPORT_OWN,
        }
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def permissions_for(role: Role) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS[role])
