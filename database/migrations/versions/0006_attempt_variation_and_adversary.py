"""per-attempt scenario variation and the adaptive adversary

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 18:00:00

* ``assignments.vary_seed``: each attempt gets its own (recorded) seed, so repeated attempts are not
  the same exercise (SIH26247: randomisation to prevent rote learning). New assignments vary by
  default (ORM default); assignments that already exist keep identical attempts, so comparisons in
  progress are not disturbed.
* ``assignments.adaptive_adversary``: plan each session's threat against the trainee's recorded
  weaknesses (``drikr_simcore.adversary``); off unless an instructor enables it.
* ``training_sessions.adversary_plan``: the plan and its reasons, stored with the session.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("vary_seed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "assignments", sa.Column("adaptive_adversary", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("training_sessions", sa.Column("adversary_plan", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("training_sessions", "adversary_plan")
    op.drop_column("assignments", "adaptive_adversary")
    op.drop_column("assignments", "vary_seed")
