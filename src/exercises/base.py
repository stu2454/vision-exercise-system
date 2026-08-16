"""Common exercise-engine contract (CLAUDE.md §11, Document 03 §18).

An exercise engine owns states, transitions, repetition rules, task
completion, and its own quality and safety observations.

It does not own the camera, pose inference, the user interface, persistence,
or speech. It receives poses, features and a pose-quality verdict, and emits
events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from src.exercises.events import Event
from src.movement.features import FeatureSet
from src.pose.models import PoseFrame
from src.pose.quality import PoseQualityReport


@dataclass
class ExerciseResult:
    """Portable result of one exercise instance (CLAUDE.md §23).

    Deliberately plain data. The participant UI and any future clinician
    system consume this contract rather than reaching into engine internals.
    """

    exercise_id: str
    exercise_specification_version: str
    exercise_algorithm_version: str
    attempted_repetitions: int = 0
    valid_repetitions: int = 0
    partial_repetitions: int = 0
    target_repetitions: Optional[int] = None
    duration_seconds: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, int] = field(default_factory=dict)
    pose_quality: str = "unknown"
    repetitions: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "incomplete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "exercise_id": self.exercise_id,
            "exercise_specification_version": self.exercise_specification_version,
            "exercise_algorithm_version": self.exercise_algorithm_version,
            "attempted_repetitions": self.attempted_repetitions,
            "valid_repetitions": self.valid_repetitions,
            "partial_repetitions": self.partial_repetitions,
            "target_repetitions": self.target_repetitions,
            "duration_seconds": round(self.duration_seconds, 3),
            "metrics": dict(self.metrics),
            "quality_flags": dict(self.quality_flags),
            "pose_quality": self.pose_quality,
            "repetitions": [dict(r) for r in self.repetitions],
            "outcome": self.outcome,
        }


class ExerciseEngine(ABC):
    """Interprets movement as exercise performance."""

    @abstractmethod
    def initialise(self, calibration: Optional[Any] = None) -> list[Event]:
        """Prepare for a new attempt, optionally with existing calibration."""

    @abstractmethod
    def update(
        self,
        pose: PoseFrame,
        features: FeatureSet,
        quality: PoseQualityReport,
    ) -> list[Event]:
        """Process one frame and return any events it produced.

        Timing comes from the frame, not from a clock read here, so that a
        replayed recording produces identical results to the live session.
        """

    @abstractmethod
    def pause(self, reason: str) -> list[Event]:
        """Suspend scoring. Any repetition in progress is abandoned."""

    @abstractmethod
    def resume(self) -> list[Event]:
        """Resume scoring after a pause."""

    @abstractmethod
    def stop(self) -> list[Event]:
        """End the attempt."""

    @abstractmethod
    def result(self) -> ExerciseResult:
        """The portable result so far."""
