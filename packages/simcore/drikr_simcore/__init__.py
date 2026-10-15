"""Authoritative logical simulation core for the Drikr Systems training simulator.

Pure Python with no I/O: scenario expansion, deterministic event timeline
generation, synthetic sensor models, validation and replay helpers. It can be
exercised entirely without Unity, the database or the web client.
"""

from drikr_simcore.confirmation import CONFIRMATION_DELAY_MS, sensor_confirmation_event
from drikr_simcore.demo import load_demo_scenarios
from drikr_simcore.difficulty import DIFFICULTY_TABLE, modifiers_for
from drikr_simcore.generator import ENGINE_VERSION, Timeline, generate_timeline
from drikr_simcore.ground_truth import GroundTruthIndex
from drikr_simcore.validation import ValidationIssue, ValidationReport, validate_definition

__all__ = [
    "CONFIRMATION_DELAY_MS",
    "DIFFICULTY_TABLE",
    "ENGINE_VERSION",
    "GroundTruthIndex",
    "Timeline",
    "ValidationIssue",
    "ValidationReport",
    "generate_timeline",
    "load_demo_scenarios",
    "modifiers_for",
    "sensor_confirmation_event",
    "validate_definition",
]
