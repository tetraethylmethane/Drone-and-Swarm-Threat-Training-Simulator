"""recorded, owner-enforced purges of raw session event logs

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 12:00:00

Security finding F-09 (docs/security/security-findings.md): the API role could delete a session's
raw event log and set `events_purged_at`, and verification then reported a routine purge. Now:

* raw logs are deleted only by two SECURITY DEFINER functions owned by the schema owner:
  `drikr_purge_session_events` purges finished sessions older than the cutoff of a real
  (non-dry-run, in-progress) retention run, never less than the policy minimum of 30 days, with age
  measured by the database clock; `drikr_purge_user_event_logs` purges a deactivated trainee's
  finished sessions for anonymisation;
* each purge is recorded in the append-only table `event_log_purges`, which the API role can only
  read;
* `events_purged_at` can only change from NULL to a value, and only when a purge record exists.

The API role loses DELETE on `session_events` (provisioned in `drikr_api/db_roles.py`). Sessions
purged before this revision get a record with reason `legacy`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = """
CREATE TABLE event_log_purges (
    session_id uuid NOT NULL,
    reason text NOT NULL,
    retention_run_id uuid,
    purged_at timestamptz NOT NULL,
    events_deleted integer NOT NULL,
    CONSTRAINT pk_event_log_purges PRIMARY KEY (session_id),
    CONSTRAINT fk_event_log_purges_session_id_training_sessions FOREIGN KEY (session_id)
        REFERENCES training_sessions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_event_log_purges_retention_run_id_retention_runs FOREIGN KEY (retention_run_id)
        REFERENCES retention_runs (id) ON DELETE RESTRICT,
    CONSTRAINT ck_event_log_purges_events_deleted_nonnegative CHECK (events_deleted >= 0),
    CONSTRAINT ck_event_log_purges_reason_valid CHECK (reason IN ('retention', 'anonymisation', 'legacy')),
    CONSTRAINT ck_event_log_purges_run_matches_reason CHECK ((reason = 'retention') = (retention_run_id IS NOT NULL))
);

INSERT INTO event_log_purges (session_id, reason, retention_run_id, purged_at, events_deleted)
SELECT id, 'legacy', NULL, events_purged_at, 0 FROM training_sessions WHERE events_purged_at IS NOT NULL;

CREATE OR REPLACE FUNCTION drikr_event_log_purges_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'event_log_purges are append-only (% rejected)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER event_log_purges_append_only
    BEFORE UPDATE OR DELETE ON event_log_purges
    FOR EACH STATEMENT EXECUTE FUNCTION drikr_event_log_purges_append_only();

CREATE OR REPLACE FUNCTION drikr_purged_flag_requires_record() RETURNS trigger AS $$
BEGIN
    IF OLD.events_purged_at IS NOT NULL THEN
        RAISE EXCEPTION 'events_purged_at of session % cannot be changed once set', NEW.id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM event_log_purges WHERE session_id = NEW.id) THEN
        RAISE EXCEPTION 'session % has no recorded purge; use drikr_purge_session_events', NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER training_sessions_purged_flag
    BEFORE UPDATE OF events_purged_at ON training_sessions
    FOR EACH ROW WHEN (NEW.events_purged_at IS DISTINCT FROM OLD.events_purged_at)
    EXECUTE FUNCTION drikr_purged_flag_requires_record();

CREATE OR REPLACE FUNCTION drikr_purge_session_events(p_run uuid, p_sessions uuid[])
RETURNS TABLE (sessions_purged integer, events_deleted integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_days integer;
    v_cutoff timestamptz;
    v_ids uuid[];
    v_events integer := 0;
BEGIN
    SELECT (r.policy ->> 'session_event_days')::integer INTO v_days
    FROM retention_runs r
    WHERE r.id = p_run AND NOT r.dry_run AND r.finished_at IS NULL AND r.started_at > now() - interval '1 hour';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'retention run % is not an in-progress, non-dry run', p_run;
    END IF;
    IF v_days IS NULL OR v_days < 30 THEN
        RAISE EXCEPTION 'retention run % does not allow purging event logs (minimum 30 days)', p_run;
    END IF;
    v_cutoff := now() - make_interval(days => v_days);

    -- Only finished sessions older than the cutoff (database clock) and not yet purged; others are
    -- skipped, never deleted.
    SELECT coalesce(array_agg(t.id), '{}') INTO v_ids
    FROM training_sessions t
    WHERE t.id = ANY (p_sessions) AND t.status IN ('completed', 'aborted')
      AND t.completed_at < v_cutoff AND t.events_purged_at IS NULL;

    INSERT INTO event_log_purges (session_id, reason, retention_run_id, purged_at, events_deleted)
    SELECT s, 'retention', p_run, now(), (SELECT count(*) FROM session_events e WHERE e.session_id = s)
    FROM unnest(v_ids) AS s;

    DELETE FROM session_events WHERE session_id = ANY (v_ids);
    GET DIAGNOSTICS v_events = ROW_COUNT;
    UPDATE training_sessions SET events_purged_at = now() WHERE id = ANY (v_ids);
    RETURN QUERY SELECT cardinality(v_ids), v_events;
END;
$$;

REVOKE ALL ON FUNCTION drikr_purge_session_events(uuid, uuid[]) FROM PUBLIC;

-- Anonymisation of a departed trainee deletes the raw logs of all their finished sessions,
-- whatever their age; only for a deactivated account with no unfinished session.
CREATE OR REPLACE FUNCTION drikr_purge_user_event_logs(p_user uuid)
RETURNS TABLE (sessions_purged integer, events_deleted integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_ids uuid[];
    v_events integer := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users u WHERE u.id = p_user AND NOT u.is_active) THEN
        RAISE EXCEPTION 'user % is not a deactivated account', p_user;
    END IF;
    IF EXISTS (
        SELECT 1 FROM training_sessions t
        WHERE t.trainee_id = p_user AND t.status NOT IN ('completed', 'aborted')
    ) THEN
        RAISE EXCEPTION 'user % has unfinished sessions', p_user;
    END IF;
    SELECT coalesce(array_agg(t.id), '{}') INTO v_ids
    FROM training_sessions t WHERE t.trainee_id = p_user AND t.events_purged_at IS NULL;

    INSERT INTO event_log_purges (session_id, reason, retention_run_id, purged_at, events_deleted)
    SELECT s, 'anonymisation', NULL, now(), (SELECT count(*) FROM session_events e WHERE e.session_id = s)
    FROM unnest(v_ids) AS s;

    DELETE FROM session_events WHERE session_id = ANY (v_ids);
    GET DIAGNOSTICS v_events = ROW_COUNT;
    UPDATE training_sessions SET events_purged_at = now() WHERE id = ANY (v_ids);
    RETURN QUERY SELECT cardinality(v_ids), v_events;
END;
$$;

REVOKE ALL ON FUNCTION drikr_purge_user_event_logs(uuid) FROM PUBLIC;
"""

DOWN = """
DROP FUNCTION IF EXISTS drikr_purge_user_event_logs(uuid);
DROP FUNCTION IF EXISTS drikr_purge_session_events(uuid, uuid[]);
DROP TRIGGER IF EXISTS training_sessions_purged_flag ON training_sessions;
DROP FUNCTION IF EXISTS drikr_purged_flag_requires_record();
DROP TRIGGER IF EXISTS event_log_purges_append_only ON event_log_purges;
DROP FUNCTION IF EXISTS drikr_event_log_purges_append_only();
DROP TABLE IF EXISTS event_log_purges;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
