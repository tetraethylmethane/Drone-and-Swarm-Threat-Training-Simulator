"""Least-privilege database role for the running API (security finding F-01).

Migrations run as the database owner. The API itself connects as a separate login role that may
read and write rows but cannot change the schema, disable triggers, truncate tables or bypass
triggers with `session_replication_role` (all of which need ownership or superuser rights).
On top of the triggers, privileges are withheld so that, at the database level:

* `audit_events`, `score_results` and `session_events` can only be inserted and read. Raw event
  logs are deleted only through `drikr_purge_session_events`, an owner-defined function that
  checks the retention policy and records every purge (migration 0005, security finding F-09);
* `event_log_purges` can only be read.

`provision()` is idempotent and runs at every API start, after migrations, so new tables and
restored databases (restores drop grants) are always covered.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url

#: Tables whose rows the application never updates or deletes.
INSERT_ONLY = ("audit_events", "score_results", "session_events")
#: Tables the application may only read (written by owner-defined functions).
READ_ONLY = ("event_log_purges",)
#: Owner-defined functions the application may call.
FUNCTIONS = ("drikr_purge_session_events(uuid, uuid[])", "drikr_purge_user_event_logs(uuid)")

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"invalid role name {name!r}")
    return name


def app_role_from_urls(app_url: str, owner_url: str) -> tuple[str, str] | None:
    """(role, password) when the API should use its own role, or None when it uses the owner."""
    app, owner = make_url(app_url), make_url(owner_url)
    if not app.username or app.username == owner.username:
        return None
    if not app.password:
        raise ValueError("DRIKR_DATABASE_URL must include a password for the application role")
    return _ident(app.username), str(app.password)


def provision(conn: Connection, role: str, password: str) -> dict[str, Any]:
    """Create or update the application role and grant exactly what the API needs."""
    role = _ident(role)
    database = conn.execute(text("SELECT current_database()")).scalar_one()
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar() is not None
    attrs = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
    # Identifiers are validated above; the password is passed as a bound literal via format().
    pw = conn.execute(text("SELECT quote_literal(:p)"), {"p": password}).scalar_one()
    if exists:
        conn.execute(text(f"ALTER ROLE {role} WITH {attrs} PASSWORD {pw}"))
    else:
        conn.execute(text(f"CREATE ROLE {role} WITH {attrs} PASSWORD {pw}"))
    db_ident = conn.execute(text("SELECT quote_ident(:d)"), {"d": database}).scalar_one()
    statements = [
        f"REVOKE ALL ON DATABASE {db_ident} FROM {role}",
        f"GRANT CONNECT ON DATABASE {db_ident} TO {role}",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        f"REVOKE ALL ON SCHEMA public FROM {role}",
        f"GRANT USAGE ON SCHEMA public TO {role}",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
        f"REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {role}",
        *(f"REVOKE UPDATE, DELETE ON {t} FROM {role}" for t in INSERT_ONLY),
        *(f"REVOKE INSERT, UPDATE, DELETE ON {t} FROM {role}" for t in READ_ONLY),
        *(f"GRANT EXECUTE ON FUNCTION {f} TO {role}" for f in FUNCTIONS),
    ]
    for sql in statements:
        conn.execute(text(sql))
    return {
        "role": role,
        "created": not exists,
        "insert_only": list(INSERT_ONLY),
        "read_only": list(READ_ONLY),
        "functions": list(FUNCTIONS),
    }


def describe_current_role(conn: Connection) -> dict[str, Any]:
    """What the running API connects as (shown on System health)."""
    row = conn.execute(
        text(
            "SELECT current_user, r.rolsuper, "
            "pg_has_role(current_user, (SELECT tableowner FROM pg_tables WHERE tablename = 'audit_events'), 'MEMBER') "
            "FROM pg_roles r WHERE r.rolname = current_user"
        )
    ).one()
    name, superuser, owner = row
    return {
        "name": name,
        "superuser": bool(superuser),
        "owns_tables": bool(owner),
        "least_privilege": not (superuser or owner),
    }
