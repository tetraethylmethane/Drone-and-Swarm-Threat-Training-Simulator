# Backup and recovery

All persistent state is in PostgreSQL (the `pgdata` Docker volume). Containers are stateless and can
be recreated from images at any time. Back up the database and keep `.env` (secrets) separately and
securely; a backup cannot be used without the matching `DRIKR_SECRET_KEY` only for *sessions*
(signed-in users must sign in again), but all records remain readable.

## Back up

```bash
scripts/backup.sh [backups]
```

Creates, in `backups/` (git-ignored):

* `drikr-<UTC>.dump`: `pg_dump` custom format (consistent snapshot; safe while the system runs);
* `drikr-<UTC>.dump.sha256`: checksum;
* `drikr-<UTC>.dump.audit.json`: audit-chain verification result including `head_hash`.

Recommended: daily backups, kept for at least 30 days, copied off-host. Copy the `head_hash` value to
a separate log that database administrators cannot alter (tamper evidence, ADR-008).

## Verify a backup (non-destructive)

```bash
scripts/verify-backup.sh backups/drikr-<UTC>.dump
```

Checks the checksum, restores into a scratch database `drikr_restore_check`, prints the schema
revision and record counts, verifies the audit chain in the restored copy and compares its head hash
with the value recorded at backup time, then drops the scratch database. Run it after every backup
job and at least monthly as a recovery exercise; keep the output as evidence.

## Restore (destructive)

```bash
scripts/restore.sh backups/drikr-<UTC>.dump --yes
```

Stops `api` and `web`, recreates the database, restores the dump, restarts the services (the API
applies any newer migrations), waits for readiness and verifies the audit chain. Users must sign in
again if `auth_sessions` in the backup have expired.

## Session recovery rules (no loss of completed results)

| Situation | Behaviour |
|---|---|
| Browser closes or network drops during an exercise | Clock stops 15 s after the last poll; the session becomes *paused (connection lost)*; the trainee resumes from the exercise page. Submitted decisions are already stored. |
| Action submitted but response lost | The client retries with the same `client_action_id`; the server returns the original event (`duplicate: true`). |
| API restarts | All state is in the database; the clock is reconstructed. Abandoned sessions are finalised by the sweeper (paused or completed and scored at the time limit). |
| Database briefly unavailable | API returns `503 database_unavailable`; the client shows *retrying*; no partial writes (transactions). |
| Completion requested twice | Idempotent; exactly one score result per session (unique constraint). |

## Local development cluster

For the `scripts/local-postgres.ps1` cluster use the PostgreSQL client tools directly:

```bash
PGPASSWORD=drikr_dev_only pg_dump -h 127.0.0.1 -p 55432 -U drikr -d drikr -Fc > dev.dump
```

## Verification record

Backup, verification and restore were exercised on 2026-10-14 against the Docker Compose stack; the
results are recorded in `docs/SPRINT_STATUS.md` (Sprint 7).
