"""Enumerations shared by every contract. Values are part of the public, versioned schema."""

from enum import StrEnum


class Terrain(StrEnum):
    URBAN = "urban"
    RURAL = "rural"
    COASTAL = "coastal"
    INDUSTRIAL = "industrial"


class TimeOfDay(StrEnum):
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class Weather(StrEnum):
    CLEAR = "clear"
    HAZE = "haze"
    RAIN = "rain"
    FOG = "fog"


class EntityClass(StrEnum):
    """Ground-truth category of a virtual entity (generic training categories)."""

    SMALL_MULTIROTOR = "small_multirotor"
    FIXED_WING_UAS = "fixed_wing_uas"
    COORDINATED_SWARM = "coordinated_swarm"
    BIRD_OR_CLUTTER = "bird_or_clutter"


class TrackClassification(StrEnum):
    """Labels a trainee may assign to a track. ``unknown`` is always permitted."""

    SMALL_MULTIROTOR = "small_multirotor"
    FIXED_WING_UAS = "fixed_wing_uas"
    COORDINATED_SWARM = "coordinated_swarm"
    BIRD_OR_CLUTTER = "bird_or_clutter"
    UNKNOWN = "unknown"


class Behavior(StrEnum):
    TRANSIT = "transit"
    LOITER = "loiter"
    ORBIT = "orbit"
    HOVER = "hover"
    ERRATIC = "erratic"


class Formation(StrEnum):
    LINE = "line"
    WEDGE = "wedge"
    CLUSTER = "cluster"


class SensorKind(StrEnum):
    RADAR = "radar"
    ELECTRO_OPTICAL = "electro_optical"
    RF = "rf"


class TrainingResponse(StrEnum):
    CONTINUE_MONITORING = "continue_monitoring"
    REQUEST_SENSOR_CONFIRMATION = "request_sensor_confirmation"
    REPORT_TO_EXERCISE_CONTROL = "report_to_exercise_control"
    LOG_AS_CLEARED = "log_as_cleared"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionKind(StrEnum):
    CLASSIFY = "classify"
    RESPOND = "respond"
