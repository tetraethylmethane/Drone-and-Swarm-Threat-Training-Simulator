"""Create load-test trainee accounts inside the load-test API container.

    docker compose -p drikrload exec -T -e LT_USERS=100 api python - < tests/load/create_users.py

Accounts are named lt-001 ... lt-NNN, use LT_USER_PASSWORD (DRIKR_DEMO_PASSWORD in the container)
and do not need a password change. Idempotent.
"""

import os

from sqlalchemy import select

from drikr_api.config import get_settings
from drikr_api.db import Database
from drikr_api.models import Role, User
from drikr_api.security.passwords import hash_password

settings = get_settings()
password = os.environ["DRIKR_DEMO_PASSWORD"]
count = int(os.environ.get("LT_USERS", "100"))
db_handle = Database(settings.database_url)
digest = hash_password(password)
created = 0
with db_handle.session_factory() as db:
    for i in range(1, count + 1):
        name = f"lt-{i:03d}"
        if db.scalar(select(User.id).where(User.username == name)):
            continue
        db.add(
            User(
                username=name,
                display_name=f"Load trainee {i:03d}",
                role=Role.TRAINEE,
                password_hash=digest,
                must_change_password=False,
                unit=f"Load unit {1 + (i - 1) // 25}",
            )
        )
        created += 1
    db.commit()
print(f"created {created} load-test trainees")
