"""immutable session events and score results

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16 12:00:00

The application never updates stored session events or score results (they are written once;
event logs may only be deleted by the retention policy). These triggers make the database enforce
that too, so a defect or a misused connection cannot silently rewrite history. Like the audit
trigger, they can be bypassed by a database superuser (session_replication_role); the
least-privilege application role (docs/security/security-findings.md, F-01) cannot do that.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = """
CREATE OR REPLACE FUNCTION drikr_session_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'session_events are append-only (% rejected)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER session_events_append_only
    BEFORE UPDATE ON session_events
    FOR EACH STATEMENT EXECUTE FUNCTION drikr_session_events_append_only();

CREATE OR REPLACE FUNCTION drikr_score_results_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'score_results are immutable (% rejected)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER score_results_immutable
    BEFORE UPDATE OR DELETE ON score_results
    FOR EACH STATEMENT EXECUTE FUNCTION drikr_score_results_immutable();
"""

DOWN = """
DROP TRIGGER IF EXISTS score_results_immutable ON score_results;
DROP FUNCTION IF EXISTS drikr_score_results_immutable();
DROP TRIGGER IF EXISTS session_events_append_only ON session_events;
DROP FUNCTION IF EXISTS drikr_session_events_append_only();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
