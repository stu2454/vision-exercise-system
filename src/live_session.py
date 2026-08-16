"""One pose frame in, quality, features and exercise events out.

The composition of filtering, features, pose quality and the exercise engine,
in one place. Both the desktop application and the browser bridge use it, so
there is a single assembly of the pipeline rather than two that could drift —
the same reason scoring lives in `src.evaluation` rather than being written out
twice.

This owns no camera, no window and no socket. It takes canonical pose frames
from wherever they came, which is what lets the browser act purely as a pose
source while the exercise engine stays in Python (Document 03 §7, ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import AppConfig, load_config
from src.exercises.base import ExerciseResult
from src.exercises.events import Event
from src.exercises.sit_to_stand import (
    SitToStandEngine,
    StsCalibration,
    StsState,
)
from src.movement.features import FeatureSet, FeatureExtractor
from src.movement.filtering import PoseFilter
from src.pose.models import PoseFrame
from src.pose.quality import PoseQualityAssessor, PoseQualityReport


@dataclass
class LiveUpdate:
    """Everything derived from one pose frame."""

    quality: PoseQualityReport
    features: FeatureSet
    events: list[Event] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality": self.quality.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }


class LiveSession:
    """Runs the movement pipeline over a stream of canonical pose frames."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        engine: Optional[SitToStandEngine] = None,
    ) -> None:
        """
        Args:
            config: Application configuration.
            engine: An exercise engine, already initialised. Optional: without
                one the session still reports pose quality and features but
                scores nothing, which is what the plain camera sandbox needs.
                The caller owns it, because the caller is what knows whether
                an exercise is being performed at all.
        """
        self._config = config or load_config()
        self._assessor = PoseQualityAssessor(self._config.pose_quality)
        self._filter = PoseFilter(self._config.filtering)
        self._extractor = FeatureExtractor(self._config.features)
        self._engine = engine

    def reset(self, calibration: Optional[StsCalibration] = None) -> list[Event]:
        """Begin a fresh attempt.

        Every stateful part is reset together. Resetting the engine but not the
        filter would carry the tail of the previous attempt into the new one,
        and the result would not be reproducible from the recording.
        """
        self._assessor.reset()
        self._filter.reset()
        self._extractor.reset()
        if self._engine is None:
            return []
        return self._engine.initialise(calibration)

    def update(self, pose: PoseFrame, score: bool = True) -> LiveUpdate:
        """Process one pose frame.

        Args:
            pose: The canonical pose to process.
            score: Whether to feed the exercise engine. False still yields
                quality and features, which a developer overlay needs before
                an exercise has been started, without anything being counted.
        """
        # Pose quality is judged on raw landmarks, because smoothing would hide
        # the jitter it exists to detect. Features derive from the filtered
        # stream, because thresholds must not be crossed by noise.
        quality = self._assessor.assess(pose)
        features = self._extractor.update(self._filter.apply(pose))
        events = (
            self._engine.update(pose, features, quality)
            if (self._engine and score)
            else []
        )
        return LiveUpdate(quality=quality, features=features, events=events)

    @property
    def scoring(self) -> bool:
        return self._engine is not None

    def stop(self) -> list[Event]:
        return self._engine.stop() if self._engine else []

    def result(self) -> Optional[ExerciseResult]:
        return self._engine.result() if self._engine else None

    @property
    def state(self) -> Optional[StsState]:
        return self._engine.state if self._engine else None

    @property
    def repetitions(self) -> Optional[int]:
        return self._engine.valid_repetitions if self._engine else None

    @property
    def calibrated(self) -> bool:
        return bool(self._engine and self._engine.calibration is not None)

    def status(self) -> dict[str, Any]:
        """A small summary suitable for sending to a display."""
        if self._engine is None:
            return {"state": None, "repetitions": None, "target": None,
                    "calibrated": False}
        return {
            "state": self._engine.state.value,
            "repetitions": self._engine.valid_repetitions,
            "target": self._engine.config.target_repetitions,
            "calibrated": self.calibrated,
        }
