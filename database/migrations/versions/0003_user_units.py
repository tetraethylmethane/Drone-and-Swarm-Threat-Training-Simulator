"""user units for unit-level reporting

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("unit", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_users_unit"), "users", ["unit"], unique=False)
    op.create_check_constraint("unit_not_blank", "users", "unit IS NULL OR length(btrim(unit)) BETWEEN 1 AND 80")


def downgrade() -> None:
    op.drop_constraint("unit_not_blank", "users", type_="check")
    op.drop_index(op.f("ix_users_unit"), table_name="users")
    op.drop_column("users", "unit")
