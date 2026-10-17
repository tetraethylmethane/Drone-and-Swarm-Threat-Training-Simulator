"""Training session lifecycle and the authoritative exercise clock.

Clock model (ADR-002):

* The server owns simulation time. ``sim_time = sim_elapsed_ms + (now - running_since)``
  while running, quantised down to the 100 ms tick and capped at the duration.
* Time only accrues while the trainee's client is connected: it stops at
  ``last_heartbeat_at + heartbeat_grace_s``. A session whose client stays silent
  beyond the grace period is paused with reason ``connection_lost`` (or
  completed with ``time_limit`` if the time limit had already been reached).
* Every state change is recorded as an event and serialised with a row lock.

Allowed transitions::

    created  -> running              (start)
    running  -> paused               (pause, or connection loss)
    paused   -> running              (resume)
    running | paused -> completed    (complete, or time limit)
    created | running | paused -> aborted  (instructor/administrator abort)
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from drikr_api import cpu
from drikr_api.errors import ApiError, conflict
from drikr_api.models import (
    Assignment,
    DifficultyMode,
    Scenario,
    SessionEvent,
    SessionMode,
    SessionStatus,
    TrainingSession,
    User,
    utcnow,
)
from drikr_api.services import adaptive_service, scoring_service
from drikr_contracts.actions import TraineeAction
from drikr_contracts.enums import ActionKind, TrainingResponse
from drikr_contracts.events import TICK_MS, EventOrigin, EventType, EventVisibility
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_contracts.scenario import TraineeOptions, TraineeSelection
from drikr_simcore import ENGINE_VERSION, GroundTruthIndex, generate_timeline, sensor_confirmation_event
from drikr_simcore.canonical import digest

S = SessionStatus
ACTIVE_STATUSES = (S.CREATED, S.RUNNING, S.PAUSED)


def config_digest(definition: dict[str, Any], seed: int, level: int) -> str:
    return digest({"definition": definition, "seed": seed, "difficulty_level": level, "engine_version": ENGINE_VERSION})


def now_sim_ms(s: TrainingSession, now: datetime, grace_s: int) -> int:
    elapsed = s.sim_elapsed_ms
    if s.status is S.RUNNING and s.running_since is not None:
        end = now
        if s.last_heartbeat_at is not None:
            end = min(now, s.last_heartbeat_at + timedelta(seconds=grace_s))
        elapsed += max(0, int((end - s.running_since).total_seconds() * 1000))
    elapsed = (elapsed // TICK_MS) * TICK_MS
    return min(elapsed, s.duration_ms)


#: Advisory-lock key that serialises the final capacity check (any constant unique to this use).
_CAPACITY_LOCK = 0x44524B01
#: A created session holds a place for this long before it is started.
CREATED_HOLD = timedelta(minutes=10)


def active_session_count(db: Session) -> int:
    """Running sessions, plus created ones from the last 10 minutes that are about to start."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(TrainingSession)
            .where(
                or_(
                    TrainingSession.status == S.RUNNING,
                    (TrainingSession.status == S.CREATED) & (TrainingSession.created_at > func.now() - CREATED_HOLD),
                )
            )
        )
        or 0
    )


def _at_capacity(limit: int) -> ApiError:
    return ApiError(
        503,
        "capacity_reached",
        f"The training server is running its maximum of {limit} exercises. Try again in a minute.",
        {"limit": limit},
        headers={"Retry-After": "30"},
    )


_inflight = 0
_inflight_lock = threading.Lock()


@contextlib.contextmanager
def creation_slot(db: Session, limit: int) -> Iterator[None]:
    """Hold a place for a session being created, from before its costly generation until commit.

    Refused requests must do no generation work, or they slow the admitted trainees the limit
    protects (load-resilience-report.md 5.8, defect L-05). Uncommitted creations are invisible to
    a database count, so at a synchronised start every request used to see an empty server. The
    supported deployment is one API process, so an in-process count of creations in progress is
    exact; ``enforce_capacity`` (locked, in the database) remains the guarantee if more processes
    are ever run.
    """
    global _inflight
    if limit <= 0:
        yield
        return
    with _inflight_lock:
        if active_session_count(db) + _inflight >= limit:
            raise _at_capacity(limit)
        _inflight += 1
    try:
        yield
    finally:
        with _inflight_lock:
            _inflight -= 1


def enforce_capacity(db: Session, limit: int) -> None:
    """Admission control (backlog B-01). Call after the session being admitted is flushed, as the
    last step before commit: the transaction-scoped advisory lock is held until commit, so two
    trainees cannot both take the last place, while the costly generation stays outside the lock."""
    if limit <= 0:
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CAPACITY_LOCK})
    if active_session_count(db) > limit:
        raise _at_capacity(limit)


def lock_session(db: Session, session_id: uuid.UUID) -> TrainingSession:
    s = db.scalar(select(TrainingSession).where(TrainingSession.id == session_id).with_for_update())
    if s is None:
        raise ApiError(404, "not_found", "Session not found")
    return s


def _append(
    db: Session,
    s: TrainingSession,
    etype: EventType,
    payload: dict[str, Any],
    *,
    t_ms: int,
    origin: EventOrigin,
    visibility: EventVisibility,
    available_at_ms: int | None = None,
    client_action_id: uuid.UUID | None = None,
) -> SessionEvent:
    prefix = {EventOrigin.TRAINEE: "T", EventOrigin.SYSTEM: "S", EventOrigin.GENERATED: "G"}[origin]
    ev = SessionEvent(
        session_id=s.id,
        seq=s.next_seq,
        event_id=f"{prefix}-{s.next_seq:06d}",
        t_ms=t_ms,
        available_at_ms=t_ms if available_at_ms is None else available_at_ms,
        type=etype.value,
        visibility=visibility.value,
        origin=origin.value,
        payload=payload,
        client_action_id=client_action_id,
    )
    s.next_seq += 1
    db.add(ev)
    return ev


def _lifecycle(db: Session, s: TrainingSession, etype: EventType, t_ms: int, reason: str | None = None) -> None:
    _append(db, s, etype, {"reason": reason}, t_ms=t_ms, origin=EventOrigin.SYSTEM, visibility=EventVisibility.SYSTEM)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def _attempts_used(db: Session, assignment_id: uuid.UUID) -> int:
    return len(
        db.scalars(
            select(TrainingSession.id).where(
                TrainingSession.assignment_id == assignment_id, TrainingSession.status != S.ABORTED
            )
        ).all()
    )


def create_session(
    db: Session,
    trainee: User,
    *,
    assignment: Assignment | None,
    scenario_row: Scenario | None,
    selection: TraineeSelection,
    self_guided_enabled: bool,
) -> TrainingSession:
    if assignment is not None:
        if assignment.trainee_id != trainee.id:
            raise ApiError(404, "not_found", "Assignment not found")
        if assignment.status != "active":
            raise conflict("assignment_inactive", "This assignment has been cancelled")
        active = db.scalar(
            select(TrainingSession).where(
                TrainingSession.assignment_id == assignment.id, TrainingSession.status.in_(ACTIVE_STATUSES)
            )
        )
        if active is not None:
            raise conflict("session_in_progress", "An attempt is already in progress", {"session_id": str(active.id)})
        used = _attempts_used(db, assignment.id)
        if used >= assignment.max_attempts:
            raise conflict("attempts_exhausted", f"All {assignment.max_attempts} attempts have been used")
        scn_row = assignment.scenario
        options = TraineeOptions.model_validate(assignment.trainee_options)
        level = adaptive_service.next_level_for_assignment(db, assignment)
        mode = SessionMode.ASSIGNED
        attempt = used + 1
    else:
        if scenario_row is None:
            raise ApiError(404, "not_found", "Scenario not found")
        if not self_guided_enabled:
            raise ApiError(403, "self_guided_disabled", "Self-guided practice is disabled by the administrator")
        if not scenario_row.self_guided or scenario_row.status != "published":
            raise ApiError(403, "not_self_guided", "This scenario is not available for self-guided practice")
        active = db.scalar(
            select(TrainingSession).where(
                TrainingSession.trainee_id == trainee.id,
                TrainingSession.scenario_id == scenario_row.id,
                TrainingSession.mode == SessionMode.SELF_GUIDED,
                TrainingSession.status.in_(ACTIVE_STATUSES),
            )
        )
        if active is not None:
            raise conflict(
                "session_in_progress", "A practice attempt is already in progress", {"session_id": str(active.id)}
            )
        scn_row = scenario_row
        # Self-guided practice permits time-of-day, weather and seed variation.
        options = TraineeOptions(
            time_of_day=["day", "dusk", "night"], weather=["clear", "haze", "rain", "fog"], allow_custom_seed=True
        )
        level = adaptive_service.next_level_self_guided(db, trainee, scn_row)
        mode = SessionMode.SELF_GUIDED
        attempt = 1 + len(
            db.scalars(
                select(TrainingSession.id).where(
                    TrainingSession.trainee_id == trainee.id,
                    TrainingSession.scenario_id == scn_row.id,
                    TrainingSession.mode == SessionMode.SELF_GUIDED,
                )
            ).all()
        )

    base = ScenarioContract.model_validate(scn_row.definition)
    try:
        effective = base.apply_selection(options, selection)
    except ValueError as exc:
        raise ApiError(422, "selection_not_permitted", str(exc).splitlines()[0]) from exc
    seed = effective.randomization.seed
    timeline = cpu.run(generate_timeline, effective, seed=seed, difficulty_level=level)
    eff_json = effective.model_dump(mode="json")

    s = TrainingSession(
        trainee_id=trainee.id,
        assignment_id=assignment.id if assignment else None,
        scenario_id=scn_row.id,
        rubric_id=scn_row.rubric_id,
        mode=mode,
        attempt_number=attempt,
        seed=seed,
        difficulty_level=level,
        selection=selection.model_dump(mode="json", exclude_none=True),
        effective_definition=eff_json,
        config_digest=config_digest(eff_json, seed, level),
        timeline_digest=timeline.digest,
        engine_version=timeline.engine_version,
        generated_event_count=len(timeline.events),
        next_seq=len(timeline.events),
        status=S.CREATED,
        duration_ms=timeline.duration_ms,
        allow_pause=effective.time_limits.allow_pause,
    )
    db.add(s)
    db.flush()
    _copy_events(db, s.id, timeline.events)
    return s


_EVENT_COLUMNS = (
    "session_id",
    "seq",
    "event_id",
    "t_ms",
    "available_at_ms",
    "type",
    "visibility",
    "origin",
    "payload",
    "recorded_at",
)


def _copy_events(db: Session, session_id: uuid.UUID, events: list[dict[str, Any]]) -> None:
    """Write a generated timeline (thousands of rows) with COPY inside the caller's transaction.

    A parameterised multi-row INSERT took about 0.7 s of API CPU per session and held a pooled
    connection throughout; under concurrent session creation that exhausted the pool
    (docs/testing/load-resilience-report.md, defect L-01). COPY writes the same rows in a single
    round trip, and the table's constraints and triggers apply exactly as for INSERT.
    """
    now = utcnow()
    raw = db.connection().connection.driver_connection
    assert raw is not None  # a live psycopg connection inside the session's transaction
    with raw.cursor() as cur, cur.copy(f"COPY session_events ({', '.join(_EVENT_COLUMNS)}) FROM STDIN") as copy:
        for e in events:
            copy.write_row(
                (
                    session_id,
                    e["seq"],
                    e["event_id"],
                    e["t_ms"],
                    e["available_at_ms"],
                    e["type"],
                    e["visibility"],
                    e["origin"],
                    Jsonb(e["payload"]),
                    now,
                )
            )


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def _invalid(s: TrainingSession, action: str) -> ApiError:
    return conflict(
        "invalid_transition", f"Cannot {action} a session that is {s.status.value}", {"status": s.status.value}
    )


def start(db: Session, s: TrainingSession, now: datetime) -> None:
    if s.status is not S.CREATED:
        raise _invalid(s, "start")
    s.status = S.RUNNING
    s.running_since = now
    s.last_heartbeat_at = now
    s.started_at = now
    _lifecycle(db, s, EventType.SESSION_STARTED, 0)


def pause(db: Session, s: TrainingSession, now: datetime, grace_s: int, reason: str = "trainee") -> None:
    if s.status is not S.RUNNING:
        raise _invalid(s, "pause")
    if reason == "trainee" and not s.allow_pause:
        raise conflict("pause_not_allowed", "Pausing is not permitted for this exercise")
    t = now_sim_ms(s, now, grace_s)
    s.sim_elapsed_ms = t
    s.running_since = None
    s.status = S.PAUSED
    s.pause_reason = reason
    s.pause_count += 1
    _lifecycle(db, s, EventType.SESSION_PAUSED, t, reason)


def resume(db: Session, s: TrainingSession, now: datetime) -> None:
    if s.status is not S.PAUSED:
        raise _invalid(s, "resume")
    s.status = S.RUNNING
    s.running_since = now
    s.last_heartbeat_at = now
    s.pause_reason = None
    _lifecycle(db, s, EventType.SESSION_RESUMED, s.sim_elapsed_ms)


def complete(db: Session, s: TrainingSession, now: datetime, grace_s: int, reason: str) -> bool:
    """Complete and score the session. Returns False if it was already completed (idempotent)."""
    if s.status is S.COMPLETED:
        return False
    if s.status not in (S.RUNNING, S.PAUSED):
        raise _invalid(s, "complete")
    t = now_sim_ms(s, now, grace_s)
    s.sim_elapsed_ms = t
    s.running_since = None
    s.status = S.COMPLETED
    s.completion_reason = reason
    s.completed_at = now
    _lifecycle(db, s, EventType.SESSION_COMPLETED, t, reason)
    db.flush()
    scoring_service.score_and_store(db, s, end_ms=t)
    adaptive_service.record_after_session(db, s)
    return True


def abort(db: Session, s: TrainingSession, now: datetime, grace_s: int, reason: str) -> None:
    if s.status not in ACTIVE_STATUSES:
        raise _invalid(s, "abort")
    t = now_sim_ms(s, now, grace_s)
    s.sim_elapsed_ms = t
    s.running_since = None
    s.status = S.ABORTED
    s.completion_reason = "aborted"
    s.completed_at = now
    _lifecycle(db, s, EventType.SESSION_COMPLETED, t, f"aborted: {reason}")


def refresh(db: Session, s: TrainingSession, now: datetime, grace_s: int, *, heartbeat: bool) -> None:
    """Apply time-based rules (connection loss, time limit); optionally record a heartbeat."""
    if s.status is not S.RUNNING:
        return
    assert s.last_heartbeat_at is not None
    lost = now > s.last_heartbeat_at + timedelta(seconds=grace_s)
    t = now_sim_ms(s, now, grace_s)
    if t >= s.duration_ms:
        complete(db, s, now, grace_s, "time_limit")
    elif lost:
        pause(db, s, now, grace_s, reason="connection_lost")
    elif heartbeat:
        s.last_heartbeat_at = now


def sweep(db: Session, grace_s: int, now: datetime | None = None) -> int:
    """Background maintenance: finalise running sessions that timed out or lost their client."""
    now = now or utcnow()
    changed = 0
    ids = db.scalars(select(TrainingSession.id).where(TrainingSession.status == S.RUNNING)).all()
    for sid in ids:
        s = lock_session(db, sid)
        before = s.status
        refresh(db, s, now, grace_s, heartbeat=False)
        if s.status is not before:
            changed += 1
        db.commit()
    return changed


# ---------------------------------------------------------------------------
# Feed and actions
# ---------------------------------------------------------------------------


def feed(db: Session, s: TrainingSession, since_ms: int, now_ms: int) -> list[dict[str, Any]]:
    """Trainee-visible events with since_ms <= available_at_ms <= now_ms (clients de-duplicate by event_id)."""
    rows = db.scalars(
        select(SessionEvent)
        .where(
            SessionEvent.session_id == s.id,
            SessionEvent.visibility != EventVisibility.GROUND_TRUTH.value,
            SessionEvent.available_at_ms >= since_ms,
            SessionEvent.available_at_ms <= now_ms,
        )
        .order_by(SessionEvent.available_at_ms, SessionEvent.seq)
    ).all()
    return [r.as_event() for r in rows]


def visible_track_ids(db: Session, s: TrainingSession, now_ms: int) -> set[str]:
    rows = db.execute(
        select(SessionEvent.payload["track_id"].astext)
        .where(
            SessionEvent.session_id == s.id,
            SessionEvent.type == EventType.TRACK_OBSERVATION.value,
            SessionEvent.available_at_ms <= now_ms,
        )
        .distinct()
    ).all()
    return {r[0] for r in rows}


def _ground_truth_for_track(db: Session, s: TrainingSession, track_id: str) -> GroundTruthIndex:
    assigned = db.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == s.id,
            SessionEvent.type == EventType.TRACK_ASSIGNED.value,
            SessionEvent.payload["track_id"].astext == track_id,
        )
    )
    if assigned is None:
        return GroundTruthIndex([])
    entity_id = assigned.payload["entity_id"]
    rows = db.scalars(
        select(SessionEvent)
        .where(
            SessionEvent.session_id == s.id,
            SessionEvent.type.in_(
                [EventType.ENTITY_SPAWNED.value, EventType.ENTITY_STATE.value, EventType.ENTITY_EXITED.value]
            ),
            SessionEvent.payload["entity_id"].astext == entity_id,
        )
        .order_by(SessionEvent.seq)
    ).all()
    return GroundTruthIndex([assigned.as_event(), *[r.as_event() for r in rows]])


def submit_action(
    db: Session, s: TrainingSession, action: TraineeAction, now: datetime, grace_s: int
) -> tuple[dict[str, Any], bool, list[dict[str, Any]]]:
    """Record a trainee action. Returns (event, duplicate, confirmation_events)."""
    existing = db.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == s.id, SessionEvent.client_action_id == action.client_action_id
        )
    )
    if existing is not None:
        return existing.as_event(), True, []

    refresh(db, s, now, grace_s, heartbeat=True)
    if s.status is not S.RUNNING:
        raise conflict(
            "session_not_running", f"Actions can only be submitted while running (session is {s.status.value})"
        )
    t = now_sim_ms(s, now, grace_s)
    visible = visible_track_ids(db, s, t)
    unknown = [tid for tid in action.track_ids if tid not in visible]
    if unknown:
        raise ApiError(
            422, "unknown_tracks", "One or more tracks are not visible in this exercise", {"track_ids": unknown}
        )

    if action.kind is ActionKind.CLASSIFY:
        etype = EventType.CLASSIFICATION_SUBMITTED
        payload: dict[str, Any] = {
            "client_action_id": str(action.client_action_id),
            "track_ids": action.track_ids,
            "classification": action.classification.value if action.classification else None,
            "confidence": action.confidence.value if action.confidence else None,
            "note": action.note,
        }
    else:
        etype = EventType.RESPONSE_SUBMITTED
        payload = {
            "client_action_id": str(action.client_action_id),
            "track_ids": action.track_ids,
            "response": action.response.value if action.response else None,
            "note": action.note,
        }
    ev = _append(
        db,
        s,
        etype,
        payload,
        t_ms=t,
        origin=EventOrigin.TRAINEE,
        visibility=EventVisibility.TRAINEE,
        client_action_id=action.client_action_id,
    )
    confirmations: list[dict[str, Any]] = []
    if action.response is TrainingResponse.REQUEST_SENSOR_CONFIRMATION:
        scn = ScenarioContract.model_validate(s.effective_definition)
        for tid in action.track_ids:
            index = _ground_truth_for_track(db, s, tid)
            c = sensor_confirmation_event(scn, s.seed, s.difficulty_level, index, tid, t, action.client_action_id)
            cev = _append(
                db,
                s,
                EventType.SENSOR_CONFIRMATION,
                c["payload"],
                t_ms=c["t_ms"],
                origin=EventOrigin.SYSTEM,
                visibility=EventVisibility.TRAINEE,
                available_at_ms=c["available_at_ms"],
            )
            confirmations.append(cev.as_event())
    db.flush()
    return ev.as_event(), False, confirmations


def all_events(db: Session, s: TrainingSession) -> list[dict[str, Any]]:
    rows = db.scalars(select(SessionEvent).where(SessionEvent.session_id == s.id).order_by(SessionEvent.seq)).all()
    return [r.as_event() for r in rows]


def is_adaptive(assignment: Assignment | None) -> bool:
    return assignment is not None and assignment.difficulty_mode is DifficultyMode.ADAPTIVE
