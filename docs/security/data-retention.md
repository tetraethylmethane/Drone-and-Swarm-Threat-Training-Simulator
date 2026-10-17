# Data retention and anonymisation

This document describes what the system keeps, for how long, and how to remove personal data. It
supports, but does not replace, the deploying organisation's own records-retention schedule and
data-protection impact assessment.

## What is stored about a person

| Data | Where | Personal? | Default retention |
|---|---|---|---|
| Account: username, display name, role, password hash, MFA secret (encrypted), recovery-code digests | `users`, `mfa_recovery_codes` | Yes | Until the account is anonymised |
| Sign-in sessions and MFA challenges | `auth_sessions`, `mfa_challenges` | Yes (IP address, user agent) | Expired or revoked records deleted after 30 days (1–365) |
| Exercise event log: every synthetic observation, decision and optional note | `session_events` | Decisions and notes, linked to the trainee | Kept, unless a period is set (30–3650 days after completion) |
| Session summary, score and score explanation | `training_sessions`, `score_results` | Linked to the account (pseudonymous once the account is anonymised) | Kept |
| Instructor review (notes, strengths, improvements) | `instructor_reviews` | Yes (free text) | Kept; free text cleared on anonymisation |
| Audit log | `audit_events` | Usernames, IP addresses | **Never deleted** (integrity record) |
| Backups | Files from `scripts/backup.sh` | Everything above | As the operator's backup rotation decides |

All exercise content is synthetic; no real sensor data or operational information is stored.

## The retention policy

**Administration → Settings → Data retention.** A period left empty turns that rule off.

| Rule | Effect | Bounds |
|---|---|---|
| Delete exercise event logs after N days | Deletes the raw event log of completed or aborted sessions older than N days. The session record, score, score explanation and digests are kept. The AAR timeline then shows "Event log removed under the data-retention policy". *Verify* still regenerates the timeline from the scenario version and seed and checks the stored score; the stored-log check reports "not checked". | 30–3650, or off |
| Delete expired sign-in records after N days | Deletes sign-in sessions and MFA challenges that expired or were revoked more than N days ago. Live sessions are never touched. | 1–365 (default 30) |
| Anonymise deactivated accounts after N days | Anonymises accounts that have been deactivated for at least N days (see below). | 30–3650, or off |

Applying the policy:

1. **Preview** shows what the saved policy would remove now.
2. **Run now** asks for confirmation, deletes, and records the run with a summary.
3. Every run, including dry runs and runs from the host, appears in the run history and in the
   audit log (`retention.dry_run`, `retention.executed`).

For a schedule, run on the host, for example daily from cron or Task Scheduler:

```bash
docker compose exec -T api drikr-api retention-run            # apply
docker compose exec -T api drikr-api retention-run --dry-run  # report only
```

Running again is harmless: data already removed is not counted twice.

## Anonymising an account

**Administration → Users → Anonymise** (shown only for deactivated accounts), confirmed by typing
the username. The policy rule above applies the same operation automatically.

Anonymisation:

- replaces the username with `deleted-<random>` and the display name with "Deleted user";
- replaces the password with an unknown random one, and removes MFA secrets, recovery codes and all
  sign-in sessions;
- deletes the exercise event logs of the person's sessions, which include any notes they typed;
- clears the free text of instructor reviews on those sessions;
- keeps the session records and scores, so cohort statistics and the study dataset stay complete.
  They are now linked only to a pseudonymous account.

It is refused while the account is active, has an unfinished session, is the caller's own account,
or is the last active administrator. **It cannot be undone**, and the account cannot be reactivated.

## What anonymisation does not remove

- **The audit log.** It is hash-chained, and deleting or editing entries would break the chain that
  makes tampering detectable. It keeps the usernames, IP addresses and actions recorded before
  anonymisation; the `user.anonymised` entry itself records the previous username. Record this in the
  data-protection impact assessment. Access to the audit log is limited to administrators.
- **Backups.** Older backups still contain the data until they are rotated out. Align the backup
  retention period with the policy.
- **Files already exported** (CSV, PDF, study dataset) and copies held elsewhere.

## Research dataset

`GET /reports/study.csv` (instructors and administrators; audited) exports one row per scored
session for training-effectiveness analysis. Participants appear only as a stable code derived with
a keyed HMAC from the account id. It contains no names, usernames, free text or times of day, only
the completion date. The code stays the same after anonymisation, so a participant's
records remain linked within the dataset without being identifiable from it. See
`docs/research/training-effectiveness-study-protocol.md`.

## Verification

Integration tests in `tests/integration/test_retention.py` cover:
- the policy bounds;
- preview, dry run and execution;
- that scores and the PDF report survive a purge, and that verification still regenerates the
  timeline;
- that repeated runs are idempotent;
- that raw logs can be deleted only by a recorded purge, that the API's database role can neither
  delete them nor mark them purged, and that verification flags an unrecorded purge
  (`tests/integration/test_purge_integrity.py`, migration `0005`);
- removal of expired sign-in records, with live sessions untouched;
- anonymisation, including that typed notes and review text are removed and that the account
  cannot sign in or be reactivated;
- the automatic anonymisation rule;
- administrator-only access.
