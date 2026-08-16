"""Movement feature extraction (Build 4).

Exercise engines consume named features rather than raw landmarks (CLAUDE.md
§9, Document 03 §16). This layer is where landmark geometry becomes quantities
a state machine can reason about, and where the honesty about what those
quantities do and do not mean lives.

Every feature declares:

    name          what it is
    units         the coordinate basis it is expressed in
    requires      which canonical landmarks it needs
    valid         whether this frame's value can be used
    confidence    how much the landmarks behind it were trusted

Units used here:

``image_heights``
    Isotropic normalised space; see `src.movement.geometry`. Resolution
    independent, but scaled by how far away the participant is standing.
``image_heights_per_second``
    Rate of change of the above.
``torso_lengths``
    Divided by the participant's own shoulder-centre-to-hip-centre distance.
    Tolerant of camera distance, which image_heights is not, and the basis
    preferred for participant-relative thresholds (Document 03 §13).
``degrees``
    Angles projected into the image plane, not anatomical joint angles.

No feature here is a validated clinical measurement. Repetition counting built
on hip height is a Level 1 measure; trunk angle and asymmetry derived from
these are Level 2 at best and must not be presented as clinical fact
(Document 04, CLAUDE.md §10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from src.movement.geometry import (
    Point,
    angle_at,
    aspect_ratio,
    distance,
    point_of,
    tilt_from_vertical,
)
from src.pose.models import (
    HIP_CENTRE,
    LEFT_ANKLE,
    LEFT_FOOT,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    RIGHT_ANKLE,
    RIGHT_FOOT,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    SHOULDER_CENTRE,
    PoseFrame,
)

# Feature names, so nothing downstream spells one wrong in a string literal.
HIP_HEIGHT = "hip_height"
HIP_VERTICAL_VELOCITY = "hip_vertical_velocity"
HIP_CENTRE_X = "hip_centre_x"
HIP_CENTRE_Y = "hip_centre_y"
SHOULDER_CENTRE_X = "shoulder_centre_x"
SHOULDER_CENTRE_Y = "shoulder_centre_y"
TORSO_LENGTH = "torso_length"
LEFT_KNEE_ANGLE = "left_knee_angle"
RIGHT_KNEE_ANGLE = "right_knee_angle"
MEAN_KNEE_ANGLE = "mean_knee_angle"
KNEE_ANGLE_ASYMMETRY = "knee_angle_asymmetry"
TRUNK_ANGLE = "trunk_angle"
TRUNK_LATERAL_DISPLACEMENT = "trunk_lateral_displacement"
STANCE_WIDTH = "stance_width"
STANCE_WIDTH_NORMALISED = "stance_width_normalised"
LEFT_FOOT_SPEED = "left_foot_speed"
RIGHT_FOOT_SPEED = "right_foot_speed"
BODY_CENTRE_X = "body_centre_x"
BODY_CENTRE_Y = "body_centre_y"

MINIMUM_ELAPSED_MS = 1.0
"""Shortest gap over which a rate of change is computed.

Below this, division by the interval amplifies landmark noise into
implausible velocities rather than measuring movement.
"""


@dataclass(frozen=True)
class FeatureValue:
    """One derived quantity and everything needed to judge it."""

    name: str
    value: Optional[float]
    units: str
    confidence: float = 0.0
    valid: bool = True
    requires: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "units": self.units,
            "confidence": self.confidence,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class FeatureSet:
    """Every feature derived from one pose frame."""

    timestamp_ms: float
    features: dict[str, FeatureValue] = field(default_factory=dict)

    def get(self, name: str) -> Optional[FeatureValue]:
        return self.features.get(name)

    def value(self, name: str) -> Optional[float]:
        """The numeric value, or None if absent or invalid.

        Invalid features return None rather than a stale or implausible
        number, so a caller cannot use one without noticing.
        """
        feature = self.features.get(name)
        if feature is None or not feature.valid:
            return None
        return feature.value

    def valid_names(self) -> list[str]:
        return sorted(n for n, f in self.features.items() if f.valid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "features": {n: f.to_dict() for n, f in self.features.items()},
        }


@dataclass(frozen=True)
class FeatureConfig:
    """Thresholds governing when a feature is considered usable.

    Attributes:
        minimum_confidence: Landmark confidence below which a feature derived
            from it is marked invalid.
        maximum_elapsed_ms: Longest gap across which a rate of change is
            computed. A larger gap means frames were dropped, and a velocity
            measured across a tracking loss is not a measurement of movement.
    """

    minimum_confidence: float = 0.30
    maximum_elapsed_ms: float = 250.0


class FeatureExtractor:
    """Derives movement features from successive pose frames.

    Stateful, because velocities need the previous frame. `reset` must be
    called between replays, or a second pass over the same recording would
    begin with the tail of the first and produce different numbers.
    """

    def __init__(self, config: Optional[FeatureConfig] = None) -> None:
        self._config = config or FeatureConfig()
        self._previous: Optional[PoseFrame] = None
        self._previous_features: Optional[FeatureSet] = None

    @property
    def config(self) -> FeatureConfig:
        return self._config

    def reset(self) -> None:
        self._previous = None
        self._previous_features = None

    def update(self, pose: PoseFrame) -> FeatureSet:
        """Derive every feature available from `pose`."""
        features: dict[str, FeatureValue] = {}
        aspect = aspect_ratio(pose)

        def confidence_of(names: Iterable[str]) -> float:
            values = [
                pose.landmarks[n].confidence for n in names if n in pose.landmarks
            ]
            return min(values) if values else 0.0

        def add(
            name: str,
            value: Optional[float],
            units: str,
            requires: tuple[str, ...],
        ) -> None:
            confidence = confidence_of(requires)
            present = all(n in pose.landmarks for n in requires)
            valid = (
                value is not None
                and present
                and confidence >= self._config.minimum_confidence
            )
            features[name] = FeatureValue(
                name=name,
                value=value,
                units=units,
                confidence=confidence,
                valid=valid,
                requires=requires,
            )

        hip = point_of(pose, HIP_CENTRE, aspect)
        shoulder = point_of(pose, SHOULDER_CENTRE, aspect)

        # Positions. Hip height inverts y so that larger means higher, which
        # is what every reader expects of something called a height; image
        # coordinates increase downwards.
        add(HIP_CENTRE_X, hip[0] if hip else None, "image_heights", (HIP_CENTRE,))
        add(HIP_CENTRE_Y, hip[1] if hip else None, "image_heights", (HIP_CENTRE,))
        add(HIP_HEIGHT, (1.0 - hip[1]) if hip else None, "image_heights", (HIP_CENTRE,))
        add(
            SHOULDER_CENTRE_X,
            shoulder[0] if shoulder else None,
            "image_heights",
            (SHOULDER_CENTRE,),
        )
        add(
            SHOULDER_CENTRE_Y,
            shoulder[1] if shoulder else None,
            "image_heights",
            (SHOULDER_CENTRE,),
        )

        torso = distance(shoulder, hip) if (shoulder and hip) else None
        add(
            TORSO_LENGTH,
            torso,
            "image_heights",
            (SHOULDER_CENTRE, HIP_CENTRE),
        )

        # Body centre: midway between shoulders and hips, a more stable
        # whole-body reference than either alone.
        if shoulder and hip:
            add(BODY_CENTRE_X, (shoulder[0] + hip[0]) / 2.0, "image_heights",
                (SHOULDER_CENTRE, HIP_CENTRE))
            add(BODY_CENTRE_Y, (shoulder[1] + hip[1]) / 2.0, "image_heights",
                (SHOULDER_CENTRE, HIP_CENTRE))
        else:
            add(BODY_CENTRE_X, None, "image_heights", (SHOULDER_CENTRE, HIP_CENTRE))
            add(BODY_CENTRE_Y, None, "image_heights", (SHOULDER_CENTRE, HIP_CENTRE))

        # Knee angles.
        left_knee = self._joint_angle(pose, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, aspect)
        right_knee = self._joint_angle(pose, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE, aspect)
        add(LEFT_KNEE_ANGLE, left_knee, "degrees", (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE))
        add(RIGHT_KNEE_ANGLE, right_knee, "degrees",
            (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE))

        knee_requires = (
            LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE
        )
        both_knees = left_knee is not None and right_knee is not None
        add(
            MEAN_KNEE_ANGLE,
            (left_knee + right_knee) / 2.0 if both_knees else None,
            "degrees",
            knee_requires,
        )
        # Asymmetry is a Level 2 measure: computable, not validated.
        add(
            KNEE_ANGLE_ASYMMETRY,
            abs(left_knee - right_knee) if both_knees else None,
            "degrees",
            knee_requires,
        )

        # Trunk.
        add(
            TRUNK_ANGLE,
            tilt_from_vertical(hip, shoulder) if (hip and shoulder) else None,
            "degrees",
            (SHOULDER_CENTRE, HIP_CENTRE),
        )
        add(
            TRUNK_LATERAL_DISPLACEMENT,
            (shoulder[0] - hip[0]) if (hip and shoulder) else None,
            "image_heights",
            (SHOULDER_CENTRE, HIP_CENTRE),
        )

        # Stance.
        left_ankle = point_of(pose, LEFT_ANKLE, aspect)
        right_ankle = point_of(pose, RIGHT_ANKLE, aspect)
        stance = (
            abs(left_ankle[0] - right_ankle[0])
            if (left_ankle and right_ankle)
            else None
        )
        add(STANCE_WIDTH, stance, "image_heights", (LEFT_ANKLE, RIGHT_ANKLE))
        add(
            STANCE_WIDTH_NORMALISED,
            stance / torso if (stance is not None and torso) else None,
            "torso_lengths",
            (LEFT_ANKLE, RIGHT_ANKLE, SHOULDER_CENTRE, HIP_CENTRE),
        )

        # Rates of change, which need the previous frame.
        elapsed_ms = self._elapsed(pose)
        add(
            HIP_VERTICAL_VELOCITY,
            self._vertical_velocity(pose, HIP_CENTRE, elapsed_ms, aspect),
            "image_heights_per_second",
            (HIP_CENTRE,),
        )
        add(
            LEFT_FOOT_SPEED,
            self._speed(pose, LEFT_FOOT, elapsed_ms, aspect),
            "image_heights_per_second",
            (LEFT_FOOT,),
        )
        add(
            RIGHT_FOOT_SPEED,
            self._speed(pose, RIGHT_FOOT, elapsed_ms, aspect),
            "image_heights_per_second",
            (RIGHT_FOOT,),
        )

        result = FeatureSet(timestamp_ms=pose.timestamp_ms, features=features)
        self._previous = pose
        self._previous_features = result
        return result

    def _elapsed(self, pose: PoseFrame) -> Optional[float]:
        """Milliseconds since the previous usable frame, or None."""
        if self._previous is None:
            return None
        elapsed = pose.timestamp_ms - self._previous.timestamp_ms
        if elapsed < MINIMUM_ELAPSED_MS:
            return None
        if elapsed > self._config.maximum_elapsed_ms:
            return None
        return elapsed

    def _joint_angle(
        self, pose: PoseFrame, proximal: str, joint: str, distal: str, aspect: float
    ) -> Optional[float]:
        a = point_of(pose, proximal, aspect)
        b = point_of(pose, joint, aspect)
        c = point_of(pose, distal, aspect)
        if not (a and b and c):
            return None
        return angle_at(a, b, c)

    def _vertical_velocity(
        self, pose: PoseFrame, name: str, elapsed_ms: Optional[float], aspect: float
    ) -> Optional[float]:
        """Upward speed in image heights per second; positive is rising."""
        if elapsed_ms is None or self._previous is None:
            return None
        now = point_of(pose, name, aspect)
        before = point_of(self._previous, name, aspect)
        if not (now and before):
            return None
        # y increases downwards, so a decrease in y is upward movement.
        return (before[1] - now[1]) * 1000.0 / elapsed_ms

    def _speed(
        self, pose: PoseFrame, name: str, elapsed_ms: Optional[float], aspect: float
    ) -> Optional[float]:
        if elapsed_ms is None or self._previous is None:
            return None
        now = point_of(pose, name, aspect)
        before = point_of(self._previous, name, aspect)
        if not (now and before):
            return None
        return distance(before, now) * 1000.0 / elapsed_ms
