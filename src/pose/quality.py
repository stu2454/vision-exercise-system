"""Pose-quality assessment (Document 03 §14, CLAUDE.md §7).

Pose quality is a shared subsystem below the exercise layer, so that every
exercise handles tracking failure the same way instead of reinventing it.

The three operational states are:

    GOOD          scoring proceeds normally
    DEGRADED      scoring may continue; unreliable metrics should be suppressed
    INSUFFICIENT  scoring pauses; the participant is not penalised

Thresholds here are engineering parameters to be established experimentally,
not clinical thresholds. They live in configuration, not in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.pose.models import (
    LEFT_ANKLE,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    RIGHT_ANKLE,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    Landmark,
    PoseFrame,
)


class PoseQualityStatus(str, Enum):
    """Operational pose-quality state."""

    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


_SEVERITY: dict[PoseQualityStatus, int] = {
    PoseQualityStatus.GOOD: 0,
    PoseQualityStatus.DEGRADED: 1,
    PoseQualityStatus.INSUFFICIENT: 2,
}

DEFAULT_REQUIRED_LANDMARKS: tuple[str, ...] = (
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ANKLE,
    RIGHT_ANKLE,
)
"""Landmarks the sandbox treats as essential by default.

Chosen for lower-limb functional exercise: trunk orientation needs shoulders
and hips, and sit-to-stand and stepping need knees and ankles. Individual
exercises override this from their own configuration.
"""


@dataclass(frozen=True)
class PoseQualityConfig:
    """Tunable inputs to the pose-quality decision.

    Attributes:
        required_landmarks: Landmarks that must be usable for GOOD quality.
        good_confidence: At or above this, a landmark is fully trusted.
        minimum_confidence: Below this, a required landmark is unusable and
            quality is INSUFFICIENT. Between the two bounds, DEGRADED.
        person_confidence_floor: Below this aggregate confidence, treat the
            participant as not adequately detected.
        edge_margin: Normalised distance from an image edge within which a
            required landmark counts as clipped.
        max_jump_normalised_per_second: Landmark speed above which the motion
            is treated as implausible tracking noise rather than movement.
            Expressed in image-normalised units per second.
        frames_to_worsen: Consecutive frames of a worse instantaneous status
            before the reported status worsens.
        frames_to_improve: Consecutive frames of a better instantaneous status
            before the reported status improves.
    """

    required_landmarks: tuple[str, ...] = DEFAULT_REQUIRED_LANDMARKS
    good_confidence: float = 0.60
    minimum_confidence: float = 0.30
    person_confidence_floor: float = 0.30
    edge_margin: float = 0.02
    max_jump_normalised_per_second: float = 3.0
    frames_to_worsen: int = 2
    frames_to_improve: int = 5


@dataclass(frozen=True)
class PoseQualityReport:
    """The pose-quality verdict for one frame.

    Attributes:
        status: Reported status, after hysteresis.
        instantaneous_status: Status implied by this frame alone, before
            hysteresis. Useful in developer mode for seeing raw behaviour.
        confidence: Mean confidence of the required landmarks present.
        missing_required: Required landmarks absent from the frame.
        low_confidence: Required landmarks below `minimum_confidence`.
        uncertain: Required landmarks between the minimum and good bounds.
        clipped: Required landmarks at or beyond an image edge.
        implausible_jumps: Required landmarks that moved implausibly fast.
        reasons: Stable machine-readable reason codes for the instantaneous
            verdict, suitable for logging and event payloads.
    """

    status: PoseQualityStatus
    instantaneous_status: PoseQualityStatus
    confidence: float
    missing_required: list[str] = field(default_factory=list)
    low_confidence: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    clipped: list[str] = field(default_factory=list)
    implausible_jumps: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def scoring_permitted(self) -> bool:
        """Whether exercise scoring should proceed on this frame."""
        return self.status is not PoseQualityStatus.INSUFFICIENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "instantaneous_status": self.instantaneous_status.value,
            "confidence": self.confidence,
            "missing_required": list(self.missing_required),
            "low_confidence": list(self.low_confidence),
            "uncertain": list(self.uncertain),
            "clipped": list(self.clipped),
            "implausible_jumps": list(self.implausible_jumps),
            "reasons": list(self.reasons),
        }


class PoseQualityAssessor:
    """Assesses successive pose frames, with state for motion and hysteresis.

    Status changes are deliberately asymmetric: quality is allowed to worsen
    quickly but must improve steadily before scoring resumes. A single noisy
    frame should never restart scoring after tracking loss (CLAUDE.md §7, §13).
    """

    def __init__(self, config: Optional[PoseQualityConfig] = None) -> None:
        self._config = config or PoseQualityConfig()
        self._previous: Optional[PoseFrame] = None
        self._status = PoseQualityStatus.INSUFFICIENT
        self._candidate: Optional[PoseQualityStatus] = None
        self._candidate_frames = 0

    @property
    def config(self) -> PoseQualityConfig:
        return self._config

    @property
    def status(self) -> PoseQualityStatus:
        """Current reported status."""
        return self._status

    def reset(self) -> None:
        """Forget all history. Call when the frame source changes."""
        self._previous = None
        self._status = PoseQualityStatus.INSUFFICIENT
        self._candidate = None
        self._candidate_frames = 0

    def assess(self, pose: PoseFrame) -> PoseQualityReport:
        """Assess one pose frame and advance the hysteresis state."""
        instantaneous, details = self._assess_instantaneous(pose)
        status = self._apply_hysteresis(instantaneous)
        self._previous = pose
        return PoseQualityReport(
            status=status, instantaneous_status=instantaneous, **details
        )

    def _assess_instantaneous(
        self, pose: PoseFrame
    ) -> tuple[PoseQualityStatus, dict[str, Any]]:
        config = self._config
        details: dict[str, Any] = {
            "confidence": 0.0,
            "missing_required": [],
            "low_confidence": [],
            "uncertain": [],
            "clipped": [],
            "implausible_jumps": [],
            "reasons": [],
        }

        if not pose.has_person:
            details["missing_required"] = list(config.required_landmarks)
            details["reasons"] = ["person_not_detected"]
            return PoseQualityStatus.INSUFFICIENT, details

        confidences: list[float] = []
        for name in config.required_landmarks:
            landmark = pose.get(name)
            if landmark is None:
                details["missing_required"].append(name)
                continue
            confidences.append(landmark.confidence)
            if landmark.confidence < config.minimum_confidence:
                details["low_confidence"].append(name)
            elif landmark.confidence < config.good_confidence:
                details["uncertain"].append(name)
            if self._is_clipped(landmark):
                details["clipped"].append(name)
            if self._has_implausible_jump(name, landmark, pose):
                details["implausible_jumps"].append(name)

        details["confidence"] = (
            float(sum(confidences) / len(confidences)) if confidences else 0.0
        )

        reasons: list[str] = []
        insufficient = False
        if details["missing_required"]:
            reasons.append("required_landmarks_missing")
            insufficient = True
        if details["low_confidence"]:
            reasons.append("required_landmarks_low_confidence")
            insufficient = True
        if pose.person_confidence < config.person_confidence_floor:
            reasons.append("person_confidence_below_floor")
            insufficient = True

        degraded = False
        if details["uncertain"]:
            reasons.append("required_landmarks_uncertain")
            degraded = True
        if details["clipped"]:
            reasons.append("required_landmarks_clipped")
            degraded = True
        if details["implausible_jumps"]:
            reasons.append("implausible_landmark_motion")
            degraded = True

        details["reasons"] = reasons
        if insufficient:
            return PoseQualityStatus.INSUFFICIENT, details
        if degraded:
            return PoseQualityStatus.DEGRADED, details
        return PoseQualityStatus.GOOD, details

    def _is_clipped(self, landmark: Landmark) -> bool:
        margin = self._config.edge_margin
        return (
            landmark.x <= margin
            or landmark.x >= 1.0 - margin
            or landmark.y <= margin
            or landmark.y >= 1.0 - margin
        )

    def _has_implausible_jump(
        self, name: str, landmark: Landmark, pose: PoseFrame
    ) -> bool:
        if self._previous is None:
            return False
        previous = self._previous.get(name)
        if previous is None:
            return False
        elapsed_s = (pose.timestamp_ms - self._previous.timestamp_ms) / 1000.0
        if elapsed_s <= 0:
            return False
        displacement = (
            (landmark.x - previous.x) ** 2 + (landmark.y - previous.y) ** 2
        ) ** 0.5
        return displacement / elapsed_s > self._config.max_jump_normalised_per_second

    def _apply_hysteresis(self, instantaneous: PoseQualityStatus) -> PoseQualityStatus:
        if instantaneous is self._status:
            self._candidate = None
            self._candidate_frames = 0
            return self._status

        if instantaneous is not self._candidate:
            self._candidate = instantaneous
            self._candidate_frames = 0
        self._candidate_frames += 1

        worsening = _SEVERITY[instantaneous] > _SEVERITY[self._status]
        required = (
            self._config.frames_to_worsen
            if worsening
            else self._config.frames_to_improve
        )
        if self._candidate_frames >= required:
            self._status = instantaneous
            self._candidate = None
            self._candidate_frames = 0
        return self._status
