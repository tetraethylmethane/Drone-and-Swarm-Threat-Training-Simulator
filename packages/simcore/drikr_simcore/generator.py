"""Deterministic timeline generation: the authoritative logical simulation.

Given a validated scenario, a seed and a difficulty level, ``generate_timeline``
produces the complete ordered event log for an exercise: ground-truth motion of
every virtual entity, synthetic sensor observations with configured
degradation, and scripted exercise events.

Simulation timing model (ADR-002):

* Fixed step of 100 ms (``TICK_MS``). Kinematics integrate every tick.
* Ground-truth entity state is recorded once per simulated second.
* Each sensor updates on its own interval with a seeded phase offset; update
  instants are quantised to the tick.
* Observation visibility is delayed by sensor latency (plus any scripted extra
  delay), rounded up to the next tick.

Identical (scenario definition, seed, difficulty level, engine version) inputs
produce byte-identical canonical event logs; ``Timeline.digest`` captures this.
Outputs are rounded (positions to 0.1 m, quality to 0.01) to keep digests stable
in the presence of last-bit floating-point differences between platforms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from drikr_contracts.enums import (
    Behavior,
    EntityClass,
    Formation,
    SensorKind,
    TimeOfDay,
    TrackClassification,
    Weather,
)
from drikr_contracts.events import TICK_MS, EventOrigin, EventType, EventVisibility
from drikr_contracts.scenario import (
    AREA_RADIUS_M,
    ElectroOpticalConfig,
    EntityGroup,
    ExerciseMessageEvent,
    RadarConfig,
    RfConfig,
    Scenario,
    SensorDegradedEvent,
    SensorRestoredEvent,
    VisibilityChangeEvent,
)
from drikr_simcore.canonical import digest
from drikr_simcore.difficulty import DifficultyModifiers, modifiers_for
from drikr_simcore.rng import Rng

ENGINE_VERSION = "simcore-1.0.0"

DT_S = TICK_MS / 1000.0
STATE_INTERVAL_MS = 1000
SPAWN_RADIUS_M = AREA_RADIUS_M * 0.95
#: Approaching entities appear this far beyond their closest-approach distance
#: (capped at SPAWN_RADIUS_M) so that they arrive within a training-useful time.
INGRESS_DISTANCE_M = 1800.0
TRACK_LOST_MIN_MS = 8000

SIGNATURE = {
    EntityClass.SMALL_MULTIROTOR: 0.6,
    EntityClass.FIXED_WING_UAS: 0.9,
    EntityClass.COORDINATED_SWARM: 0.5,
    EntityClass.BIRD_OR_CLUTTER: 0.4,
}
TURN_RATE_DEG_S = {
    EntityClass.SMALL_MULTIROTOR: 60.0,
    EntityClass.FIXED_WING_UAS: 15.0,
    EntityClass.COORDINATED_SWARM: 40.0,
    EntityClass.BIRD_OR_CLUTTER: 45.0,
}
LIGHT_RANGE_FACTOR = {TimeOfDay.DAY: 1.0, TimeOfDay.DUSK: 0.7, TimeOfDay.NIGHT: 0.45}
LIGHT_ACCURACY_FACTOR = {TimeOfDay.DAY: 1.0, TimeOfDay.DUSK: 0.85, TimeOfDay.NIGHT: 0.65}
WEATHER_RADAR_FACTOR = {Weather.CLEAR: 1.0, Weather.HAZE: 1.0, Weather.RAIN: 0.85, Weather.FOG: 0.95}
WEATHER_EO_ACCURACY = {Weather.CLEAR: 1.0, Weather.HAZE: 0.9, Weather.RAIN: 0.85, Weather.FOG: 0.75}

# Sort order for events that share a tick: environment first, then truth, then observations.
_TYPE_ORDER = {
    EventType.ENVIRONMENT_UPDATE: 0,
    EventType.SENSOR_STATUS: 1,
    EventType.EXERCISE_MESSAGE: 2,
    EventType.ENTITY_SPAWNED: 3,
    EventType.ENTITY_STATE: 4,
    EventType.TRACK_ASSIGNED: 5,
    EventType.TRACK_OBSERVATION: 6,
    EventType.OBSERVATION_MISSED: 7,
    EventType.TRACK_LOST: 8,
    EventType.ENTITY_EXITED: 9,
}


def _r1(v: float) -> float:
    return round(v, 1)


def _r2(v: float) -> float:
    return round(v, 2)


def _ceil_tick(ms: float) -> int:
    return int(math.ceil(ms / TICK_MS - 1e-9)) * TICK_MS


def _floor_tick(ms: float) -> int:
    return int(math.floor(ms / TICK_MS + 1e-9)) * TICK_MS


def _wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


# ---------------------------------------------------------------------------
# Entity expansion and motion
# ---------------------------------------------------------------------------


@dataclass
class _Entity:
    entity_id: str
    group_id: str
    entity_class: EntityClass
    behavior: Behavior
    cooperative: bool
    signature: float
    spawn_ms: int
    speed: float
    altitude: float
    approach_m: float
    dwell_ms: int | None
    rng: Rng
    swarm_id: str | None = None
    formation_offset: tuple[float, float] = (0.0, 0.0)
    clutter: bool = False
    lifetime_ms: int | None = None
    # dynamic state
    x: float = 0.0
    y: float = 0.0
    alt: float = 0.0
    heading: float = 0.0
    cur_speed: float = 0.0
    phase: str = "inbound"
    phase_started_ms: int = 0
    anchor: tuple[float, float] = (0.0, 0.0)
    active: bool = False
    exited: bool = False

    @property
    def range_m(self) -> float:
        return math.hypot(self.x, self.y)


@dataclass
class _SwarmLeader:
    """Invisible reference point that swarm members fly in formation around."""

    proxy: _Entity
    members: list[_Entity] = field(default_factory=list)


def _formation_offsets(formation: Formation, size: int, spacing: float, rng: Rng) -> list[tuple[float, float]]:
    offsets: list[tuple[float, float]] = []
    for i in range(size):
        if formation is Formation.LINE:
            offsets.append((0.0, (i - (size - 1) / 2) * spacing))
        elif formation is Formation.WEDGE:
            row = (i + 1) // 2
            side = 1 if i % 2 else -1
            offsets.append((-row * spacing, side * row * spacing * 0.8))
        else:
            r = spacing * math.sqrt(i + 0.5) * 0.9
            a = i * 2.39996323  # golden angle
            offsets.append(
                (r * math.cos(a) + rng.gauss(0, spacing * 0.1), r * math.sin(a) + rng.gauss(0, spacing * 0.1))
            )
    return offsets


def _initial_position(e: _Entity) -> None:
    bearing = e.rng.uniform(0, 2 * math.pi)
    if e.behavior is Behavior.ERRATIC:
        r = e.approach_m
        e.x, e.y = r * math.cos(bearing), r * math.sin(bearing)
        e.heading = e.rng.uniform(-math.pi, math.pi)
    else:
        spawn_r = min(SPAWN_RADIUS_M, e.approach_m + INGRESS_DISTANCE_M)
        e.x, e.y = spawn_r * math.cos(bearing), spawn_r * math.sin(bearing)
        e.heading = math.atan2(-e.y, -e.x)
        if e.behavior is Behavior.TRANSIT:
            side = 1 if e.rng.chance(0.5) else -1
            perp = bearing + side * math.pi / 2
            e.anchor = (e.approach_m * math.cos(perp), e.approach_m * math.sin(perp))
        elif e.behavior in (Behavior.LOITER, Behavior.HOVER):
            jitter = e.rng.uniform(-0.6, 0.6)
            e.anchor = (e.approach_m * math.cos(bearing + jitter), e.approach_m * math.sin(bearing + jitter))
    e.alt = e.altitude
    e.cur_speed = e.speed


def _steer(e: _Entity, desired: float) -> None:
    max_turn = math.radians(TURN_RATE_DEG_S[e.entity_class]) * DT_S
    delta = _wrap_angle(desired - e.heading)
    e.heading = _wrap_angle(e.heading + max(-max_turn, min(max_turn, delta)))


def _step_motion(e: _Entity, now_ms: int) -> None:
    rng = e.rng
    b = e.behavior
    elapsed_phase = now_ms - e.phase_started_ms

    def set_phase(p: str) -> None:
        e.phase = p
        e.phase_started_ms = now_ms

    dwell_done = e.dwell_ms is not None and elapsed_phase >= e.dwell_ms
    speed_target = e.speed

    if b is Behavior.TRANSIT:
        if e.phase == "inbound":
            ax, ay = e.anchor
            desired = math.atan2(ay - e.y, ax - e.x)
            if math.hypot(ax - e.x, ay - e.y) < 60:
                set_phase("outbound")
            _steer(e, desired)
        # outbound: keep heading
    elif b is Behavior.LOITER:
        ax, ay = e.anchor
        loiter_r = 250.0 if e.entity_class is EntityClass.FIXED_WING_UAS else 120.0
        if e.phase == "inbound":
            _steer(e, math.atan2(ay - e.y, ax - e.x))
            if math.hypot(ax - e.x, ay - e.y) < loiter_r:
                set_phase("loiter")
        elif e.phase == "loiter":
            ang = math.atan2(e.y - ay, e.x - ax)
            dist = math.hypot(e.x - ax, e.y - ay)
            correction = (dist - loiter_r) / loiter_r
            _steer(e, ang + math.pi / 2 + max(-0.8, min(0.8, correction)))
            if dwell_done:
                set_phase("egress")
        else:
            _steer(e, math.atan2(e.y, e.x))
    elif b is Behavior.ORBIT:
        if e.phase == "inbound":
            _steer(e, math.atan2(-e.y, -e.x))
            if e.range_m <= max(e.approach_m, 150.0):
                set_phase("orbit")
        elif e.phase == "orbit":
            r = max(e.approach_m, 150.0)
            ang = math.atan2(e.y, e.x)
            correction = (e.range_m - r) / r
            _steer(e, ang + math.pi / 2 + max(-0.8, min(0.8, correction)))
            if dwell_done:
                set_phase("egress")
        else:
            _steer(e, math.atan2(e.y, e.x))
    elif b is Behavior.HOVER:
        ax, ay = e.anchor
        if e.phase == "inbound":
            _steer(e, math.atan2(ay - e.y, ax - e.x))
            d = math.hypot(ax - e.x, ay - e.y)
            speed_target = min(e.speed, max(1.0, d / 4))
            if d < 15:
                set_phase("hover")
        elif e.phase == "hover":
            speed_target = 0.0
            e.x += rng.gauss(0, 0.15)
            e.y += rng.gauss(0, 0.15)
            if dwell_done:
                set_phase("egress")
        else:
            _steer(e, math.atan2(e.y, e.x))
    elif b is Behavior.ERRATIC:
        limit = e.approach_m + 400.0
        if e.range_m > limit:
            _steer(e, math.atan2(-e.y, -e.x))
        else:
            e.heading = _wrap_angle(e.heading + rng.gauss(0, 0.12))
        speed_target = max(0.5, e.speed * (0.7 + 0.6 * rng.uniform()))

    # speed and altitude response
    e.cur_speed += (speed_target - e.cur_speed) * 0.2
    e.alt = max(5.0, e.alt + rng.gauss(0, 0.3) + (e.altitude - e.alt) * 0.02)
    e.x += e.cur_speed * math.cos(e.heading) * DT_S
    e.y += e.cur_speed * math.sin(e.heading) * DT_S


def _expand(scn: Scenario, seed: int, mods: DifficultyModifiers) -> tuple[list[_Entity], list[_SwarmLeader]]:
    entities: list[_Entity] = []
    leaders: list[_SwarmLeader] = []
    for g in scn.entities:
        grng = Rng.stream(seed, "group", g.id)
        count = grng.randint(g.count.min, g.count.max)
        for n in range(1, count + 1):
            erng_seed = Rng.stream(seed, "entity", g.id, n)
            base = _make_entity(g, f"{g.id}-{n:02d}", erng_seed)
            if g.swarm is not None:
                size = erng_seed.randint(g.swarm.size.min, g.swarm.size.max)
                leader = _SwarmLeader(proxy=base)
                offsets = _formation_offsets(g.swarm.formation, size, g.swarm.spacing_m, erng_seed)
                for k, off in enumerate(offsets, start=1):
                    member = _make_entity(g, f"{g.id}-{n:02d}-m{k:02d}", Rng.stream(seed, "member", g.id, n, k))
                    member.spawn_ms = base.spawn_ms
                    member.speed = base.speed
                    member.altitude = base.altitude + member.rng.uniform(-8, 8)
                    member.swarm_id = base.entity_id
                    member.formation_offset = off
                    leader.members.append(member)
                    entities.append(member)
                leaders.append(leader)
            else:
                entities.append(base)

    clutter_rate = scn.sensors.radar.clutter_tracks_per_min + (
        mods.extra_clutter_per_min if scn.sensors.radar.enabled else 0
    )
    if scn.sensors.radar.enabled and clutter_rate > 0:
        crng = Rng.stream(seed, "clutter")
        duration_ms = scn.time_limits.duration_s * 1000
        t = 0.0
        n = 0
        while True:
            t += -math.log(max(crng.uniform(), 1e-12)) * 60000.0 / clutter_rate
            if t >= duration_ms - 20000:
                break
            n += 1
            e = _Entity(
                entity_id=f"clutter-{n:02d}",
                group_id="radar-clutter",
                entity_class=EntityClass.BIRD_OR_CLUTTER,
                behavior=Behavior.ERRATIC,
                cooperative=False,
                signature=0.35,
                spawn_ms=_floor_tick(t),
                speed=crng.uniform(2, 12),
                altitude=crng.uniform(20, 150),
                approach_m=crng.uniform(400, min(scn.sensors.radar.range_m * 0.9, 3500)),
                dwell_ms=None,
                rng=Rng.stream(seed, "clutter-entity", n),
                clutter=True,
                lifetime_ms=_floor_tick(crng.uniform(10000, 40000)),
            )
            entities.append(e)
    return entities, leaders


def _make_entity(g: EntityGroup, entity_id: str, rng: Rng) -> _Entity:
    dwell = None
    if g.dwell_s is not None:
        dwell = int(rng.uniform(g.dwell_s.min, g.dwell_s.max) * 1000)
    return _Entity(
        entity_id=entity_id,
        group_id=g.id,
        entity_class=g.entity_class,
        behavior=g.behavior,
        cooperative=g.cooperative,
        signature=SIGNATURE[g.entity_class],
        spawn_ms=_floor_tick(rng.uniform(g.spawn_time_s.min, g.spawn_time_s.max) * 1000),
        speed=rng.uniform(g.speed_mps.min, g.speed_mps.max),
        altitude=rng.uniform(g.altitude_m.min, g.altitude_m.max),
        approach_m=rng.uniform(g.closest_approach_m.min, g.closest_approach_m.max),
        dwell_ms=dwell,
        rng=rng,
    )


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------


@dataclass
class _SensorState:
    kind: SensorKind
    interval_ms: int
    phase_ms: int
    latency_ms: float
    detection_factor: float = 1.0
    noise_factor: float = 1.0
    extra_delay_s: float = 0.0


@dataclass
class _TrackState:
    track_id: str
    last_positional_ms: int
    lost: bool = False


@dataclass
class Timeline:
    engine_version: str
    scenario_key: str
    scenario_version: int
    seed: int
    difficulty_level: int
    duration_ms: int
    events: list[dict[str, Any]]
    digest: str
    stats: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "scenario_key": self.scenario_key,
            "scenario_version": self.scenario_version,
            "seed": self.seed,
            "difficulty_level": self.difficulty_level,
            "duration_ms": self.duration_ms,
            "digest": self.digest,
            "stats": self.stats,
        }


class _Builder:
    def __init__(self) -> None:
        self.raw: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def add(
        self,
        t_ms: int,
        etype: EventType,
        payload: dict[str, Any],
        *,
        available_at_ms: int | None = None,
        tiebreak: str = "",
    ) -> None:
        vis = EventVisibility.GROUND_TRUTH if etype in _GT else EventVisibility.TRAINEE
        avail = t_ms if available_at_ms is None else max(t_ms, available_at_ms)
        key = (t_ms, _TYPE_ORDER[etype], tiebreak)
        self.raw.append(
            (
                key,
                {
                    "t_ms": t_ms,
                    "available_at_ms": avail,
                    "type": etype.value,
                    "visibility": vis.value,
                    "origin": EventOrigin.GENERATED.value,
                    "payload": payload,
                },
            )
        )

    def finish(self) -> list[dict[str, Any]]:
        self.raw.sort(key=lambda kv: kv[0])
        out = []
        for seq, (_, ev) in enumerate(self.raw):
            out.append({"event_id": f"G-{seq:06d}", "seq": seq, **ev})
        return out


_GT = {
    EventType.ENTITY_SPAWNED,
    EventType.ENTITY_STATE,
    EventType.ENTITY_EXITED,
    EventType.TRACK_ASSIGNED,
    EventType.OBSERVATION_MISSED,
}

_LABELS = [c for c in TrackClassification if c is not TrackClassification.UNKNOWN]


def effective_eo_range(scn: Scenario, visibility_km: float) -> float:
    eo = scn.sensors.electro_optical
    return min(eo.range_m, visibility_km * 1000.0 * LIGHT_RANGE_FACTOR[scn.environment.time_of_day])


def effective_eo_accuracy(scn: Scenario, mods: DifficultyModifiers) -> float:
    eo = scn.sensors.electro_optical
    acc = (
        eo.classification_accuracy
        * mods.eo_accuracy_mult
        * LIGHT_ACCURACY_FACTOR[scn.environment.time_of_day]
        * WEATHER_EO_ACCURACY[scn.environment.weather]
    )
    return min(0.98, acc)


def wrong_label(true_label: TrackClassification, rng: Rng) -> TrackClassification:
    if rng.chance(0.4):
        return TrackClassification.UNKNOWN
    return rng.choice([c for c in _LABELS if c is not true_label])


def generate_timeline(scn: Scenario, seed: int | None = None, difficulty_level: int | None = None) -> Timeline:
    seed = scn.randomization.seed if seed is None else seed
    level = scn.difficulty.level if difficulty_level is None else difficulty_level
    mods = modifiers_for(level)
    duration_ms = scn.time_limits.duration_s * 1000
    out = _Builder()

    entities, leaders = _expand(scn, seed, mods)
    for e in entities:
        _initial_position(e)
    leader_of = {m.entity_id: ld for ld in leaders for m in ld.members}
    for ld in leaders:
        _initial_position(ld.proxy)

    # --- sensors -----------------------------------------------------------
    srng = Rng.stream(seed, "sensor-phase")
    sensors: dict[SensorKind, _SensorState] = {}
    cfgs: dict[SensorKind, RadarConfig | ElectroOpticalConfig | RfConfig] = {
        SensorKind.RADAR: scn.sensors.radar,
        SensorKind.ELECTRO_OPTICAL: scn.sensors.electro_optical,
        SensorKind.RF: scn.sensors.rf,
    }
    for kind, cfg in cfgs.items():
        if cfg.enabled:
            interval = max(TICK_MS, _floor_tick(cfg.update_interval_s * 1000))
            sensors[kind] = _SensorState(
                kind=kind,
                interval_ms=interval,
                phase_ms=_floor_tick(srng.uniform(0, interval)),
                latency_ms=(cfg.latency_s + mods.latency_add_s) * 1000,
            )
            out.add(0, EventType.SENSOR_STATUS, _sensor_status(sensors[kind]), tiebreak=kind.value)
    visibility_km = scn.environment.visibility_km
    out.add(0, EventType.ENVIRONMENT_UPDATE, {"visibility_km": visibility_km})

    schedule = sorted(scn.event_schedule, key=lambda ev: (ev.at_s, ev.id))
    sched_idx = 0

    radar_interval = sensors[SensorKind.RADAR].interval_ms if SensorKind.RADAR in sensors else 3000
    lost_after_ms = max(TRACK_LOST_MIN_MS, 3 * radar_interval)

    obs_rng = {k: Rng.stream(seed, "obs", k.value) for k in sensors}
    tracks: dict[str, _TrackState] = {}
    next_track = 1
    eo_acc = effective_eo_accuracy(scn, mods)
    stats_obs = 0

    def ensure_track(e: _Entity, t_ms: int) -> _TrackState:
        nonlocal next_track
        tr = tracks.get(e.entity_id)
        if tr is None:
            tr = _TrackState(track_id=f"TRK-{next_track:03d}", last_positional_ms=t_ms)
            next_track += 1
            tracks[e.entity_id] = tr
            out.add(
                t_ms,
                EventType.TRACK_ASSIGNED,
                {"track_id": tr.track_id, "entity_id": e.entity_id},
                tiebreak=e.entity_id,
            )
        return tr

    for tick in range(duration_ms // TICK_MS + 1):
        now = tick * TICK_MS

        # scripted events
        while sched_idx < len(schedule) and _floor_tick(schedule[sched_idx].at_s * 1000) <= now:
            ev = schedule[sched_idx]
            sched_idx += 1
            if isinstance(ev, SensorDegradedEvent):
                st = sensors[ev.sensor]
                st.detection_factor, st.noise_factor, st.extra_delay_s = (
                    ev.detection_factor,
                    ev.noise_factor,
                    ev.extra_delay_s,
                )
                out.add(now, EventType.SENSOR_STATUS, _sensor_status(st), tiebreak=ev.id)
            elif isinstance(ev, SensorRestoredEvent):
                st = sensors[ev.sensor]
                st.detection_factor, st.noise_factor, st.extra_delay_s = 1.0, 1.0, 0.0
                out.add(now, EventType.SENSOR_STATUS, _sensor_status(st), tiebreak=ev.id)
            elif isinstance(ev, VisibilityChangeEvent):
                visibility_km = ev.visibility_km
                out.add(now, EventType.ENVIRONMENT_UPDATE, {"visibility_km": visibility_km}, tiebreak=ev.id)
            elif isinstance(ev, ExerciseMessageEvent):
                out.add(now, EventType.EXERCISE_MESSAGE, {"message": ev.message}, tiebreak=ev.id)

        # spawn
        for e in entities:
            if not e.active and not e.exited and e.spawn_ms == now:
                e.active = True
                e.phase_started_ms = now
                if e.swarm_id:
                    ld = leader_of[e.entity_id]
                    _place_member(e, ld.proxy)
                out.add(
                    now,
                    EventType.ENTITY_SPAWNED,
                    {
                        "entity_id": e.entity_id,
                        "group_id": e.group_id,
                        "entity_class": e.entity_class.value,
                        "behavior": e.behavior.value,
                        "cooperative": e.cooperative,
                        "swarm_id": e.swarm_id,
                        "signature": e.signature,
                    },
                    tiebreak=e.entity_id,
                )
                out.add(now, EventType.ENTITY_STATE, _state_payload(e), tiebreak=e.entity_id)
        for ld in leaders:
            if not ld.proxy.active and not ld.proxy.exited and ld.proxy.spawn_ms == now:
                ld.proxy.active = True
                ld.proxy.phase_started_ms = now

        # motion (skip the spawn tick so spawn state is the initial position)
        for ld in leaders:
            if ld.proxy.active and ld.proxy.spawn_ms < now:
                _step_motion(ld.proxy, now)
        for e in entities:
            if not e.active or e.spawn_ms == now:
                continue
            if e.swarm_id:
                _place_member(e, leader_of[e.entity_id].proxy)
            else:
                _step_motion(e, now)
            faded = e.clutter and e.lifetime_ms is not None and now - e.spawn_ms >= e.lifetime_ms
            if e.range_m > AREA_RADIUS_M or faded:
                e.active = False
                e.exited = True
                out.add(
                    now,
                    EventType.ENTITY_EXITED,
                    {"entity_id": e.entity_id, "reason": "faded" if faded else "left_area"},
                    tiebreak=e.entity_id,
                )
                tr = tracks.get(e.entity_id)
                if tr is not None and not tr.lost:
                    tr.lost = True
                    out.add(
                        now,
                        EventType.TRACK_LOST,
                        {"track_id": tr.track_id},
                        available_at_ms=_ceil_tick(now + 2000),
                        tiebreak=tr.track_id,
                    )
                continue
            if (now - e.spawn_ms) % STATE_INTERVAL_MS == 0:
                out.add(now, EventType.ENTITY_STATE, _state_payload(e), tiebreak=e.entity_id)

        # sensor updates
        for kind, st in sensors.items():
            if now < st.phase_ms or (now - st.phase_ms) % st.interval_ms != 0:
                continue
            rng = obs_rng[kind]
            for e in entities:
                if not e.active:
                    continue
                obs = _sense(kind, st, e, scn, mods, rng, visibility_km, eo_acc)
                if obs is None:
                    continue
                if isinstance(obs, str):
                    out.add(
                        now,
                        EventType.OBSERVATION_MISSED,
                        {"entity_id": e.entity_id, "sensor": kind.value, "reason": obs},
                        tiebreak=f"{e.entity_id}|{kind.value}",
                    )
                    continue
                tr = ensure_track(e, now)
                if kind is not SensorKind.RF:
                    tr.last_positional_ms = now
                tr.lost = False
                delay = st.latency_ms + st.extra_delay_s * 1000 * (0.5 + rng.uniform())
                obs["track_id"] = tr.track_id
                out.add(
                    now,
                    EventType.TRACK_OBSERVATION,
                    obs,
                    available_at_ms=_ceil_tick(now + delay),
                    tiebreak=f"{tr.track_id}|{kind.value}",
                )
                stats_obs += 1

        # track loss
        for e in entities:
            tr = tracks.get(e.entity_id)
            if tr is None or tr.lost or not e.active:
                continue
            if now - tr.last_positional_ms >= lost_after_ms:
                tr.lost = True
                out.add(now, EventType.TRACK_LOST, {"track_id": tr.track_id}, tiebreak=tr.track_id)

    events = out.finish()
    by_class: dict[str, int] = {}
    for e in entities:
        by_class[e.entity_class.value] = by_class.get(e.entity_class.value, 0) + 1
    tracked_classes: dict[str, int] = {}
    for e in entities:
        if e.entity_id in tracks:
            tracked_classes[e.entity_class.value] = tracked_classes.get(e.entity_class.value, 0) + 1
    stats = {
        "entities": len(entities),
        "entities_by_class": dict(sorted(by_class.items())),
        "tracks": len(tracks),
        "tracks_by_class": dict(sorted(tracked_classes.items())),
        "observations": stats_obs,
        "events": len(events),
        "difficulty": mods.as_dict(),
    }
    return Timeline(
        engine_version=ENGINE_VERSION,
        scenario_key=scn.key,
        scenario_version=scn.version,
        seed=seed,
        difficulty_level=level,
        duration_ms=duration_ms,
        events=events,
        digest=digest(events),
        stats=stats,
    )


def _place_member(m: _Entity, leader: _Entity) -> None:
    fx, fy = m.formation_offset
    c, s = math.cos(leader.heading), math.sin(leader.heading)
    m.x = leader.x + fx * c - fy * s + m.rng.gauss(0, 1.5)
    m.y = leader.y + fx * s + fy * c + m.rng.gauss(0, 1.5)
    m.alt = max(5.0, m.altitude + (leader.alt - leader.altitude) + m.rng.gauss(0, 0.5))
    m.heading = leader.heading
    m.cur_speed = leader.cur_speed


def _state_payload(e: _Entity) -> dict[str, Any]:
    return {
        "entity_id": e.entity_id,
        "x_m": _r1(e.x),
        "y_m": _r1(e.y),
        "alt_m": _r1(e.alt),
        "speed_mps": _r1(e.cur_speed),
        "heading_deg": _r1(math.degrees(e.heading) % 360),
        "range_m": _r1(e.range_m),
    }


def _sensor_status(st: _SensorState) -> dict[str, Any]:
    degraded = st.detection_factor < 1.0 or st.noise_factor > 1.0 or st.extra_delay_s > 0
    return {
        "sensor": st.kind.value,
        "status": "degraded" if degraded else "nominal",
        "detection_factor": _r2(st.detection_factor),
        "noise_factor": _r2(st.noise_factor),
        "extra_delay_s": _r2(st.extra_delay_s),
    }


def _sense(
    kind: SensorKind,
    st: _SensorState,
    e: _Entity,
    scn: Scenario,
    mods: DifficultyModifiers,
    rng: Rng,
    visibility_km: float,
    eo_acc: float,
) -> dict[str, Any] | str | None:
    """Return an observation payload, a miss reason, or None when the sensor cannot sense this entity at all."""
    r = e.range_m
    if kind is SensorKind.RADAR:
        cfg = scn.sensors.radar
        if r > cfg.range_m:
            return "out_of_range"
        p = (
            cfg.detection_probability
            * mods.detection_mult
            * st.detection_factor
            * WEATHER_RADAR_FACTOR[scn.environment.weather]
            * (0.55 + 0.45 * e.signature)
            * (1 - 0.35 * (r / cfg.range_m) ** 2)
        )
        if not rng.chance(min(1.0, p)):
            return "not_detected"
        sigma = cfg.position_noise_m * mods.noise_mult * st.noise_factor * (0.5 + r / cfg.range_m)
        quality = max(0.05, min(1.0, (1 - sigma / 150.0) * (0.7 + 0.3 * e.signature)))
        return {
            "sensor": kind.value,
            "synthetic": True,
            "quality": _r2(quality),
            "x_m": _r1(e.x + rng.gauss(0, sigma)),
            "y_m": _r1(e.y + rng.gauss(0, sigma)),
            "alt_m": _r1(max(0.0, e.alt + rng.gauss(0, sigma * 0.5))),
            "speed_mps": _r1(max(0.0, e.cur_speed + rng.gauss(0, 1.5 * mods.noise_mult * st.noise_factor))),
        }
    if kind is SensorKind.ELECTRO_OPTICAL:
        if e.clutter:
            return None  # radar clutter has no optical counterpart
        cfg_eo = scn.sensors.electro_optical
        eff = effective_eo_range(scn, visibility_km)
        if r > eff:
            return "out_of_range"
        p = cfg_eo.detection_probability * mods.detection_mult * st.detection_factor * (1 - 0.4 * (r / eff) ** 2)
        if not rng.chance(min(1.0, p)):
            return "not_detected"
        acc = eo_acc * (1 - 0.5 * (r / eff)) * (1.0 / st.noise_factor)
        true_label = TrackClassification(e.entity_class.value)
        hint = true_label if rng.chance(acc) else wrong_label(true_label, rng)
        sigma = 40.0 * mods.noise_mult * st.noise_factor
        return {
            "sensor": kind.value,
            "synthetic": True,
            "quality": _r2(max(0.05, min(1.0, acc))),
            "x_m": _r1(e.x + rng.gauss(0, sigma)),
            "y_m": _r1(e.y + rng.gauss(0, sigma)),
            "class_hint": hint.value,
        }
    # RF: only virtual drones emit simulated control/beacon signals.
    if e.entity_class is EntityClass.BIRD_OR_CLUTTER:
        return None
    cfg_rf = scn.sensors.rf
    if r > cfg_rf.range_m:
        return "out_of_range"
    p = cfg_rf.detection_probability * mods.detection_mult * st.detection_factor * (1 - 0.3 * (r / cfg_rf.range_m) ** 2)
    if not rng.chance(min(1.0, p)):
        return "not_detected"
    bearing = math.degrees(math.atan2(e.y, e.x)) + rng.gauss(0, 4.0 * mods.noise_mult * st.noise_factor)
    beacon = e.cooperative and rng.chance(0.95)
    return {
        "sensor": kind.value,
        "synthetic": True,
        "quality": _r2(0.5 / st.noise_factor),
        "bearing_deg": _r1(bearing % 360),
        "beacon": beacon,
    }
