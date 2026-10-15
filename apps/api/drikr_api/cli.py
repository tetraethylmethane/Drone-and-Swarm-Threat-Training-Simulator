"""Operational command-line interface.

Usage::

    drikr-api migrate                       apply database migrations
    drikr-api seed-demo [--with-demo-users] load demonstration rubric and scenarios (idempotent)
    drikr-api create-admin --username NAME  create the first administrator
                                            (password from DRIKR_ADMIN_PASSWORD or prompt)
    drikr-api verify-audit                  verify the audit hash chain
    drikr-api sweep                         finalise timed-out sessions once
    drikr-api reset-mfa --username NAME     break-glass removal of a user's MFA (audited)
    drikr-api retention-run [--dry-run]     apply the data-retention policy (for scheduled jobs)

Demonstration content is flagged ``is_demo`` and is clearly separated from real trainee records.
Demo users are only created with ``--with-demo-users`` and a password supplied in DRIKR_DEMO_PASSWORD.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from drikr_api.audit import append_audit, verify_chain
from drikr_api.config import get_settings
from drikr_api.db import Database
from drikr_api.models import Role, Rubric, Scenario, User
from drikr_api.security.passwords import hash_password, policy_violations
from drikr_api.services import catalog_service, mfa_service, retention_service, session_service
from drikr_scoring import load_default_rubrics
from drikr_simcore import load_demo_scenarios


def migrations_dir() -> Path:
    """Locate database/migrations: DRIKR_MIGRATIONS_DIR, else the repository checkout."""
    env = os.environ.get("DRIKR_MIGRATIONS_DIR")
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[3] / "database" / "migrations")
    for c in candidates:
        if (c / "env.py").is_file():
            return c
    raise SystemExit("Migration scripts not found; set DRIKR_MIGRATIONS_DIR to the database/migrations directory")


DEMO_USERS = [
    ("admin", "Demo Administrator", Role.ADMINISTRATOR),
    ("instructor", "Demo Instructor", Role.INSTRUCTOR),
    ("trainee1", "Demo Trainee One", Role.TRAINEE),
    ("trainee2", "Demo Trainee Two", Role.TRAINEE),
]


def migrate(url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir()))
    os.environ["DRIKR_DATABASE_URL"] = url
    command.upgrade(cfg, "head")


def seed_demo(db_url: str, with_users: bool) -> dict[str, int]:
    database = Database(db_url)
    created = {"rubrics": 0, "scenarios": 0, "users": 0}
    with database.session_factory() as db:
        for definition in load_default_rubrics():
            if db.scalar(
                select(Rubric.id).where(Rubric.key == definition["key"], Rubric.version == definition["version"])
            ):
                continue
            row = catalog_service.create_rubric(db, definition, None, new_key=True, is_demo=True)
            append_audit(
                db, actor=None, action="seed.rubric", target_type="rubric", target_id=row.id, details={"key": row.key}
            )
            created["rubrics"] += 1
        for definition in load_demo_scenarios():
            if db.scalar(select(Scenario.id).where(Scenario.key == definition["key"])):
                continue
            scn = catalog_service.create_scenario(db, definition, None, new_key=True, is_demo=True)
            append_audit(
                db,
                actor=None,
                action="seed.scenario",
                target_type="scenario",
                target_id=scn.id,
                details={"key": scn.key},
            )
            created["scenarios"] += 1
        if with_users:
            password = os.environ.get("DRIKR_DEMO_PASSWORD", "")
            for username, name, role in DEMO_USERS:
                if db.scalar(select(User.id).where(User.username == username)):
                    continue
                problems = policy_violations(password, username)
                if problems:
                    raise SystemExit(
                        "DRIKR_DEMO_PASSWORD is missing or does not meet the policy: " + "; ".join(problems)
                    )
                u = User(username=username, display_name=name, role=role, password_hash=hash_password(password))
                db.add(u)
                db.flush()
                append_audit(
                    db,
                    actor=None,
                    action="seed.user",
                    target_type="user",
                    target_id=u.id,
                    details={"username": username, "role": role.value},
                )
                created["users"] += 1
        db.commit()
    database.dispose()
    return created


def create_admin(db_url: str, username: str, display_name: str) -> None:
    password = os.environ.get("DRIKR_ADMIN_PASSWORD") or getpass.getpass("Administrator password: ")
    problems = policy_violations(password, username)
    if problems:
        raise SystemExit("Password does not meet the policy: " + "; ".join(problems))
    database = Database(db_url)
    with database.session_factory() as db:
        if db.scalar(select(User.id).where(User.username == username)):
            raise SystemExit(f"User '{username}' already exists")
        u = User(
            username=username, display_name=display_name, role=Role.ADMINISTRATOR, password_hash=hash_password(password)
        )
        db.add(u)
        db.flush()
        append_audit(
            db,
            actor=None,
            action="cli.admin_created",
            target_type="user",
            target_id=u.id,
            details={"username": username},
        )
        db.commit()
    database.dispose()
    print(f"Administrator '{username}' created.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="drikr-api")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    seed = sub.add_parser("seed-demo")
    seed.add_argument("--with-demo-users", action="store_true")
    adm = sub.add_parser("create-admin")
    adm.add_argument("--username", required=True)
    adm.add_argument("--display-name", default="Administrator")
    sub.add_parser("verify-audit")
    sub.add_parser("sweep")
    rm = sub.add_parser("reset-mfa")
    rm.add_argument("--username", required=True)
    rr = sub.add_parser("retention-run")
    rr.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    url = settings.database_url
    if args.cmd == "migrate":
        migrate(url)
    elif args.cmd == "seed-demo":
        print(json.dumps(seed_demo(url, args.with_demo_users)))
    elif args.cmd == "create-admin":
        create_admin(url, args.username, args.display_name)
    elif args.cmd == "verify-audit":
        database = Database(url)
        with database.session_factory() as db:
            report = verify_chain(db)
        print(json.dumps(report))
        sys.exit(0 if report["valid"] else 1)
    elif args.cmd == "sweep":
        database = Database(url)
        with database.session_factory() as db:
            print(json.dumps({"sessions_changed": session_service.sweep(db, settings.heartbeat_grace_s)}))
    elif args.cmd == "reset-mfa":
        database = Database(url)
        with database.session_factory() as db:
            user = db.scalar(select(User).where(User.username == args.username.lower()).with_for_update())
            if user is None:
                raise SystemExit(f"User '{args.username}' not found")
            mfa_service.clear(db, user)
            append_audit(
                db,
                actor=None,
                action="cli.mfa_reset",
                target_type="user",
                target_id=user.id,
                details={"username": user.username},
            )
            db.commit()
        print(f"MFA removed for '{args.username}'. They must enrol again at next sign-in if their role requires it.")
    elif args.cmd == "retention-run":
        database = Database(url)
        with database.session_factory() as db:
            record = retention_service.run(db, None, dry_run=args.dry_run, trigger="cli")
            db.commit()
            print(json.dumps(retention_service.run_out(record), default=str))


if __name__ == "__main__":
    main()
