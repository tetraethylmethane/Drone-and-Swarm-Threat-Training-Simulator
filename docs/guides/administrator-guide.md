# Administrator guide

Installation, TLS, start/stop and updates: `docs/operations/offline-deployment.md`.
Backups and recovery: `docs/operations/backup-and-recovery.md`.

## First administrator

```bash
docker compose exec api drikr-api create-admin --username admin --display-name "Training Administrator"
```

The password is read from `DRIKR_ADMIN_PASSWORD` or prompted. At the first sign-in the
administrator is taken to **Account and security** to set up multi-factor authentication, which
administrators must use by default.

## Users

**Users** lets you add accounts (temporary password; change forced at first sign-in), change role,
deactivate or reactivate, reset passwords and unlock accounts locked after repeated failed sign-ins.
Role changes, deactivation and resets sign the user out everywhere. You cannot remove your own
administrator access or the last active administrator.

Tags show whether an account uses MFA, is locked, must change its password, or has been anonymised.

* **Reset MFA** (for a user who lost their authenticator and recovery codes): turns MFA off and
  signs the user out everywhere. If their role requires MFA, they set it up again at the next
  sign-in. Confirm the person's identity outside the system first.
* **Anonymise** (deactivated accounts only, irreversible): see
  [data retention](../security/data-retention.md).

## Multi-factor authentication

Each user sets up an authenticator app under **Account and security**, by scanning a QR code or
entering the key, and saves ten single-use recovery codes. After that, sign-in asks for a 6-digit
code after the password. Users can create new recovery codes, and can turn MFA off if their role
does not require it.

**Settings → Multi-factor authentication** chooses the roles that must use MFA (default:
administrators). Users in those roles who have not enrolled can reach only their account page until
they do. You must have MFA on yourself before you can require it for administrators.

Recovery when no administrator can sign in:

```bash
docker compose exec api drikr-api reset-mfa --username <name>
```

**Key rotation:** changing `DRIKR_SECRET_KEY` signs everyone out and makes every stored MFA secret
and recovery code unusable. Those users' code step fails with "Stored MFA secret cannot be read"
until their MFA is reset (in **Users**, or with the command above), after which they enrol again.

## Data retention

**Settings → Data retention** sets how long exercise event logs and expired sign-in records are kept,
and when deactivated accounts are anonymised. **Preview** before **Run now**; run history is shown
below and recorded in the audit log. For a daily schedule use `drikr-api retention-run`. What is kept
and removed: [data retention](../security/data-retention.md).

## Settings

* **Adaptive difficulty policy**: sessions considered, minimum sessions, increase and decrease
  thresholds, confidence spread. Changes apply to future recommendations only.
* **Self-guided practice** can be switched off for all trainees.
* **Multi-factor authentication** and **Data retention**: see the sections above.

All changes are audited with before and after values.

## Audit log

Lists privileged and security-relevant events (sign-ins and failures, lockouts, user changes,
scenario and rubric versions, assignments, aborts, reviews, exports, verifications, settings).
**Verify chain** recomputes the hash chain. A break identifies the first altered event. Keep the head
hash from each backup in separate storage.

## System health

Versions of every component, database latency and size, record counts, audit-chain status, and a
confirmation that the system has no external runtime dependencies or telemetry.

## Operational commands

| Command | Purpose |
|---|---|
| `drikr-api migrate` | Apply database migrations (also runs at container start) |
| `drikr-api seed-demo [--with-demo-users]` | Load demonstration rubric and scenarios |
| `drikr-api verify-audit` | Verify the audit chain (exit code 1 if broken) |
| `drikr-api sweep` | Finalise timed-out or abandoned sessions once |
| `drikr-api reset-mfa --username <name>` | Turn off MFA for an account and sign it out (audited) |
| `drikr-api retention-run [--dry-run]` | Apply the saved retention policy (audited; for scheduled jobs) |

## Training analytics and research data

**Analytics** shows each trainee's change between their first and latest attempt at a scenario,
with cohort statistics. This is a monitoring view: without a control group it cannot show that
training works. **Export pseudonymised dataset** produces the input for a controlled study
(`docs/research/training-effectiveness-study-protocol.md`). How well the score measures skill was
checked with synthetic trainees (`docs/research/assessment-validation.md`).
