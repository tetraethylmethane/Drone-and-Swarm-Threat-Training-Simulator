"""Versioned scenario definition schema.

A scenario fully describes a synthetic training exercise: the virtual
environment, simulated sensor quality, virtual entity groups, scripted events,
randomisation constraints, difficulty profile, scoring rubric reference, time
limits and learning objectives.

Validation happens in two layers:

1. Structural and cross-field rules enforced by these Pydantic models.
2. Generation checks in ``drikr_simcore.validation`` which expand the scenario
   with a seed and verify the resulting timeline is usable for training.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from drikr_contracts._base import StrictModel
from drikr_contracts.enums import (
    Behavior,
    EntityClass,
    Formation,
    SensorKind,
    Terrain,
    TimeOfDay,
    TrainingResponse,
    Weather,
)

SCENARIO_SCHEMA_VERSION = "1.0"

#: Hard cap on expanded virtual entities, protecting generation time and the UI.
MAX_TOTAL_ENTITIES = 60
#: Simulated operating area radius around the protected site, in metres.
AREA_RADIUS_M = 4000.0

Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
ShortId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


class FloatRange(StrictModel):
    min: float
    max: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")
        return self


class IntRange(StrictModel):
    min: int
    max: int

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")
        return self


# ---------------------------------------------------------------------------
# Learning objectives
# ---------------------------------------------------------------------------


class ClassifyCorrectlyCriterion(StrictModel):
    """At least ``min_fraction`` of observable tracks of ``entity_class`` are classified correctly."""

    kind: Literal["classify_correctly"] = "classify_correctly"
    entity_class: EntityClass
    min_fraction: float = Field(ge=0.0, le=1.0)


class RespondWithinCriterion(StrictModel):
    """Every observable track of ``entity_class`` receives ``response`` within ``within_s`` of first observation."""

    kind: Literal["respond_within"] = "respond_within"
    entity_class: EntityClass
    response: TrainingResponse
    within_s: float = Field(gt=0, le=1800)


class NoFalseClearanceCriterion(StrictModel):
    """No non-cooperative drone track is logged as cleared."""

    kind: Literal["no_false_clearance"] = "no_false_clearance"


class ClassifyAllCriterion(StrictModel):
    """At least ``min_fraction`` of all observable tracks receive any classification."""

    kind: Literal["classify_all"] = "classify_all"
    min_fraction: float = Field(ge=0.0, le=1.0)


ObjectiveCriterion = Annotated[
    ClassifyCorrectlyCriterion | RespondWithinCriterion | NoFalseClearanceCriterion | ClassifyAllCriterion,
    Field(discriminator="kind"),
]


class LearningObjective(StrictModel):
    id: ShortId
    description: str = Field(min_length=5, max_length=300)
    criterion: ObjectiveCriterion


# ---------------------------------------------------------------------------
# Environment and sensors
# ---------------------------------------------------------------------------


class EnvironmentConfig(StrictModel):
    terrain: Terrain
    time_of_day: TimeOfDay
    weather: Weather
    visibility_km: float = Field(ge=0.2, le=30.0)
    wind_mps: float = Field(ge=0.0, le=25.0, default=3.0)

    @model_validator(mode="after")
    def _weather_consistent(self) -> Self:
        if self.weather is Weather.FOG and self.visibility_km > 2.0:
            raise ValueError("fog requires visibility_km <= 2.0")
        if self.weather is Weather.HAZE and self.visibility_km > 8.0:
            raise ValueError("haze requires visibility_km <= 8.0")
        return self


class RadarConfig(StrictModel):
    enabled: bool = True
    range_m: float = Field(ge=500, le=10000, default=4000)
    update_interval_s: float = Field(ge=0.5, le=10.0, default=2.0)
    detection_probability: float = Field(ge=0.05, le=1.0, default=0.9)
    position_noise_m: float = Field(ge=0.0, le=250.0, default=25.0)
    latency_s: float = Field(ge=0.0, le=10.0, default=0.5)
    clutter_tracks_per_min: float = Field(ge=0.0, le=6.0, default=0.0)


class ElectroOpticalConfig(StrictModel):
    enabled: bool = True
    range_m: float = Field(ge=200, le=6000, default=2000)
    update_interval_s: float = Field(ge=0.5, le=10.0, default=3.0)
    detection_probability: float = Field(ge=0.05, le=1.0, default=0.8)
    classification_accuracy: float = Field(ge=0.0, le=1.0, default=0.75)
    latency_s: float = Field(ge=0.0, le=10.0, default=1.0)


class RfConfig(StrictModel):
    enabled: bool = True
    range_m: float = Field(ge=200, le=8000, default=3000)
    update_interval_s: float = Field(ge=0.5, le=10.0, default=4.0)
    detection_probability: float = Field(ge=0.05, le=1.0, default=0.7)
    latency_s: float = Field(ge=0.0, le=10.0, default=1.5)


class SensorSuite(StrictModel):
    radar: RadarConfig = Field(default_factory=RadarConfig)
    electro_optical: ElectroOpticalConfig = Field(default_factory=ElectroOpticalConfig)
    rf: RfConfig = Field(default_factory=RfConfig)

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if not (self.radar.enabled or self.electro_optical.enabled or self.rf.enabled):
            raise ValueError("at least one simulated sensor must be enabled")
        if not (self.radar.enabled or self.electro_optical.enabled):
            raise ValueError("radar or electro_optical must be enabled to produce positional tracks")
        return self


# ---------------------------------------------------------------------------
# Virtual entities
# ---------------------------------------------------------------------------


class SwarmConfig(StrictModel):
    size: IntRange
    formation: Formation = Formation.CLUSTER
    spacing_m: float = Field(ge=5.0, le=200.0, default=30.0)

    @model_validator(mode="after")
    def _size(self) -> Self:
        if self.size.min < 3 or self.size.max > 24:
            raise ValueError("swarm size must be within 3..24")
        return self


class EntityGroup(StrictModel):
    id: ShortId
    label: str = Field(min_length=2, max_length=120)
    entity_class: EntityClass
    behavior: Behavior
    cooperative: bool = False
    count: IntRange
    spawn_time_s: FloatRange
    speed_mps: FloatRange
    altitude_m: FloatRange
    closest_approach_m: FloatRange
    dwell_s: FloatRange | None = None
    swarm: SwarmConfig | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.count.min < 1 or self.count.max > 20:
            raise ValueError("count must be within 1..20")
        if self.spawn_time_s.min < 0:
            raise ValueError("spawn_time_s must be non-negative")
        if self.speed_mps.min < 0 or self.speed_mps.max > 60:
            raise ValueError("speed_mps must be within 0..60")
        if self.altitude_m.min < 5 or self.altitude_m.max > 1500:
            raise ValueError("altitude_m must be within 5..1500")
        if self.closest_approach_m.min < 0 or self.closest_approach_m.max > AREA_RADIUS_M * 0.9:
            raise ValueError(f"closest_approach_m must be within 0..{AREA_RADIUS_M * 0.9:.0f}")
        is_swarm = self.entity_class is EntityClass.COORDINATED_SWARM
        if is_swarm and self.swarm is None:
            raise ValueError("coordinated_swarm groups require a swarm configuration")
        if not is_swarm and self.swarm is not None:
            raise ValueError("swarm configuration is only valid for coordinated_swarm groups")
        if self.behavior is Behavior.HOVER and self.entity_class is EntityClass.FIXED_WING_UAS:
            raise ValueError("fixed_wing_uas cannot hover")
        if self.entity_class is EntityClass.BIRD_OR_CLUTTER and self.cooperative:
            raise ValueError("bird_or_clutter entities cannot be cooperative")
        if self.behavior is Behavior.TRANSIT and self.speed_mps.min <= 0:
            raise ValueError("transit behaviour requires a positive minimum speed")
        return self

    def max_entities(self) -> int:
        per = self.swarm.size.max if self.swarm else 1
        return self.count.max * per


# ---------------------------------------------------------------------------
# Scripted events
# ---------------------------------------------------------------------------


class SensorDegradedEvent(StrictModel):
    """Simulated sensor-quality degradation (reduced detection, more noise, extra delay)."""

    type: Literal["sensor_degraded"] = "sensor_degraded"
    id: ShortId
    at_s: float = Field(ge=0)
    sensor: SensorKind
    detection_factor: float = Field(ge=0.0, le=1.0)
    noise_factor: float = Field(ge=1.0, le=5.0, default=1.0)
    extra_delay_s: float = Field(ge=0.0, le=10.0, default=0.0)


class SensorRestoredEvent(StrictModel):
    type: Literal["sensor_restored"] = "sensor_restored"
    id: ShortId
    at_s: float = Field(ge=0)
    sensor: SensorKind


class VisibilityChangeEvent(StrictModel):
    type: Literal["visibility_change"] = "visibility_change"
    id: ShortId
    at_s: float = Field(ge=0)
    visibility_km: float = Field(ge=0.2, le=30.0)


class ExerciseMessageEvent(StrictModel):
    type: Literal["exercise_message"] = "exercise_message"
    id: ShortId
    at_s: float = Field(ge=0)
    message: str = Field(min_length=3, max_length=280)


ScheduledEvent = Annotated[
    SensorDegradedEvent | SensorRestoredEvent | VisibilityChangeEvent | ExerciseMessageEvent,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Difficulty, scoring, time limits and trainee options
# ---------------------------------------------------------------------------


class DifficultyProfile(StrictModel):
    """Difficulty level 3 runs the scenario exactly as authored; see drikr_simcore.difficulty."""

    level: int = Field(ge=1, le=5, default=3)
    adaptive_allowed: bool = True
    min_level: int = Field(ge=1, le=5, default=1)
    max_level: int = Field(ge=1, le=5, default=5)

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if not (self.min_level <= self.level <= self.max_level):
            raise ValueError("difficulty level must lie within min_level..max_level")
        return self


class ScoringRef(StrictModel):
    rubric_key: Slug
    rubric_version: int = Field(ge=1)


class TimeLimits(StrictModel):
    duration_s: int = Field(ge=60, le=1800)
    allow_pause: bool = True


class RandomizationConfig(StrictModel):
    seed: int = Field(ge=0, le=2**53 - 1)
    allow_seed_override: bool = True


class TraineeOptions(StrictModel):
    """Options an instructor permits a trainee to choose at launch.

    Empty lists mean the option is fixed to the scenario's authored value.
    """

    time_of_day: list[TimeOfDay] = Field(default_factory=list)
    weather: list[Weather] = Field(default_factory=list)
    allow_custom_seed: bool = False


class TraineeSelection(StrictModel):
    time_of_day: TimeOfDay | None = None
    weather: Weather | None = None
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


class Scenario(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    key: Slug
    version: int = Field(ge=1, default=1)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    briefing: str = Field(min_length=10, max_length=4000)
    learning_objectives: list[LearningObjective] = Field(min_length=1, max_length=10)
    environment: EnvironmentConfig
    sensors: SensorSuite
    entities: list[EntityGroup] = Field(min_length=1, max_length=20)
    event_schedule: list[ScheduledEvent] = Field(default_factory=list, max_length=50)
    randomization: RandomizationConfig
    difficulty: DifficultyProfile = Field(default_factory=DifficultyProfile)
    scoring: ScoringRef
    time_limits: TimeLimits
    self_guided: bool = False

    @model_validator(mode="after")
    def _cross_field(self) -> Self:
        duration = self.time_limits.duration_s

        group_ids = [g.id for g in self.entities]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("entity group ids must be unique")
        objective_ids = [o.id for o in self.learning_objectives]
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("learning objective ids must be unique")
        event_ids = [e.id for e in self.event_schedule]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("scheduled event ids must be unique")

        for g in self.entities:
            if g.spawn_time_s.max > duration - 30:
                raise ValueError(f"entity group '{g.id}' must spawn at least 30 s before the time limit ({duration} s)")
        total = sum(g.max_entities() for g in self.entities)
        if total > MAX_TOTAL_ENTITIES:
            raise ValueError(f"scenario may expand to {total} entities; the maximum is {MAX_TOTAL_ENTITIES}")

        for e in self.event_schedule:
            if e.at_s >= duration:
                raise ValueError(f"scheduled event '{e.id}' occurs after the time limit")
            if (
                isinstance(e, SensorDegradedEvent | SensorRestoredEvent)
                and not getattr(self.sensors, e.sensor.value).enabled
            ):
                raise ValueError(f"scheduled event '{e.id}' targets disabled sensor '{e.sensor.value}'")

        present = {g.entity_class for g in self.entities}
        for o in self.learning_objectives:
            crit = o.criterion
            if (
                isinstance(crit, ClassifyCorrectlyCriterion | RespondWithinCriterion)
                and crit.entity_class not in present
            ):
                raise ValueError(
                    f"objective '{o.id}' references entity class '{crit.entity_class.value}' "
                    "which no entity group provides"
                )
        return self

    def apply_selection(self, options: TraineeOptions, selection: TraineeSelection) -> Scenario:
        """Return a copy with permitted trainee selections applied; reject anything not permitted."""
        data = self.model_copy(deep=True)
        if selection.time_of_day is not None:
            if selection.time_of_day not in options.time_of_day:
                raise ValueError("time_of_day selection is not permitted for this exercise")
            data.environment.time_of_day = selection.time_of_day
        if selection.weather is not None:
            if selection.weather not in options.weather:
                raise ValueError("weather selection is not permitted for this exercise")
            data.environment.weather = selection.weather
            # Keep the environment consistent with the chosen weather.
            if selection.weather is Weather.FOG:
                data.environment.visibility_km = min(data.environment.visibility_km, 1.5)
            elif selection.weather is Weather.HAZE:
                data.environment.visibility_km = min(data.environment.visibility_km, 6.0)
        if selection.seed is not None:
            if not (options.allow_custom_seed and self.randomization.allow_seed_override):
                raise ValueError("custom seeds are not permitted for this exercise")
            data.randomization.seed = selection.seed
        # Re-run full validation on the modified copy.
        return Scenario.model_validate(data.model_dump(mode="json"))
