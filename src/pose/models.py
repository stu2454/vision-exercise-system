"""Canonical, vendor-neutral pose representation.

This module is the central technical abstraction of the project (Document 03
§12, ADR-007). Everything above the pose adapter layer consumes `PoseFrame`
and nothing else. No pose-engine-specific type, landmark index or field name
may appear here or in any module that depends on this one.

Coordinate basis
----------------
`x` and `y` are image-normalised to [0, 1] (Document 03 §13): x increases to
the right of the image, y increases *downwards* from the top edge. Callers
computing heights must therefore treat smaller y as higher in the frame.

Because x and y are each normalised by a different pixel dimension, angles and
distances computed directly in this space are distorted by the image aspect
ratio. `PoseFrame.image_width` / `image_height` are carried so the feature
layer (Build 4) can correct for this; they are not part of the minimum
representation in Document 03 §12 but are required to make it usable.

`z` is whatever depth estimate the engine supplied, or None. It must not be
assumed metrically accurate (Document 03 §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

NOSE = "nose"

LEFT_SHOULDER = "left_shoulder"
RIGHT_SHOULDER = "right_shoulder"
LEFT_ELBOW = "left_elbow"
RIGHT_ELBOW = "right_elbow"
LEFT_WRIST = "left_wrist"
RIGHT_WRIST = "right_wrist"
LEFT_HIP = "left_hip"
RIGHT_HIP = "right_hip"
LEFT_KNEE = "left_knee"
RIGHT_KNEE = "right_knee"
LEFT_ANKLE = "left_ankle"
RIGHT_ANKLE = "right_ankle"
LEFT_HEEL = "left_heel"
RIGHT_HEEL = "right_heel"
LEFT_FOOT = "left_foot"
RIGHT_FOOT = "right_foot"

SHOULDER_CENTRE = "shoulder_centre"
HIP_CENTRE = "hip_centre"

MEASURED_LANDMARKS: tuple[str, ...] = (
    NOSE,
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ELBOW,
    RIGHT_ELBOW,
    LEFT_WRIST,
    RIGHT_WRIST,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
    LEFT_HEEL,
    RIGHT_HEEL,
    LEFT_FOOT,
    RIGHT_FOOT,
)
"""Landmarks a pose engine is expected to supply (Document 03 §12)."""

SYNTHETIC_LANDMARKS: tuple[str, ...] = (SHOULDER_CENTRE, HIP_CENTRE)
"""Landmarks derived from measured landmarks rather than reported by an engine."""

CANONICAL_LANDMARKS: tuple[str, ...] = MEASURED_LANDMARKS + SYNTHETIC_LANDMARKS

SYNTHETIC_SOURCES: dict[str, tuple[str, str]] = {
    SHOULDER_CENTRE: (LEFT_SHOULDER, RIGHT_SHOULDER),
    HIP_CENTRE: (LEFT_HIP, RIGHT_HIP),
}
"""Which measured landmarks each synthetic landmark is the midpoint of."""

CANONICAL_CONNECTIONS: tuple[tuple[str, str], ...] = (
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (LEFT_ANKLE, LEFT_HEEL),
    (LEFT_HEEL, LEFT_FOOT),
    (LEFT_ANKLE, LEFT_FOOT),
    (RIGHT_HIP, RIGHT_KNEE),
    (RIGHT_KNEE, RIGHT_ANKLE),
    (RIGHT_ANKLE, RIGHT_HEEL),
    (RIGHT_HEEL, RIGHT_FOOT),
    (RIGHT_ANKLE, RIGHT_FOOT),
    (SHOULDER_CENTRE, HIP_CENTRE),
)
"""Skeleton edges for developer overlay drawing, in canonical names only."""


@dataclass(frozen=True)
class Landmark:
    """A single canonical body point.

    Attributes:
        x: Image-normalised horizontal position, 0.0 at the left image edge.
        y: Image-normalised vertical position, 0.0 at the top image edge.
        z: Engine-supplied depth estimate, or None. Not metrically validated.
        confidence: Engine-supplied confidence in [0, 1]. The precise meaning
            is engine-specific and is documented by each adapter.
    """

    x: float
    y: float
    z: Optional[float]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Landmark":
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            z=None if data.get("z") is None else float(data["z"]),
            confidence=float(data["confidence"]),
        )


@dataclass(frozen=True)
class PoseFrame:
    """One canonical pose observation.

    A frame in which no person was detected is represented by an empty
    `landmarks` mapping and a `person_confidence` of 0.0, rather than by None.
    Keeping the stream continuous means a recorded pose stream replays with
    the same frame timing as the original capture, and lets the pose-quality
    layer distinguish "person absent" from "stream ended".

    Attributes:
        timestamp_ms: Milliseconds from the start of the frame source, taken
            from a monotonic clock for live capture and from media time for
            file sources (Document 03 §24).
        person_confidence: Aggregate confidence that a trackable person is
            present, in [0, 1]. Derived; see each adapter for its definition.
        landmarks: Canonical landmark name -> Landmark. May be empty. May omit
            landmarks the engine could not supply.
        source: Human-readable provenance, e.g. "mediapipe:webcam:0".
        frame_index: Zero-based index of the originating frame, if known.
        image_width: Pixel width of the originating image, if known.
        image_height: Pixel height of the originating image, if known.
    """

    timestamp_ms: float
    person_confidence: float
    landmarks: dict[str, Landmark]
    source: str
    frame_index: Optional[int] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None

    @property
    def has_person(self) -> bool:
        """Whether any landmark was reported at all."""
        return bool(self.landmarks)

    def get(self, name: str) -> Optional[Landmark]:
        """Return a landmark by canonical name, or None if not present."""
        return self.landmarks.get(name)

    def missing(self, names: Iterable[str]) -> list[str]:
        """Return the requested canonical names that this frame does not carry."""
        return [name for name in names if name not in self.landmarks]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "person_confidence": self.person_confidence,
            "source": self.source,
            "frame_index": self.frame_index,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "landmarks": {
                name: landmark.to_dict() for name, landmark in self.landmarks.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PoseFrame":
        return cls(
            timestamp_ms=float(data["timestamp_ms"]),
            person_confidence=float(data["person_confidence"]),
            landmarks={
                name: Landmark.from_dict(value)
                for name, value in data.get("landmarks", {}).items()
            },
            source=str(data["source"]),
            frame_index=(
                None if data.get("frame_index") is None else int(data["frame_index"])
            ),
            image_width=(
                None if data.get("image_width") is None else int(data["image_width"])
            ),
            image_height=(
                None if data.get("image_height") is None else int(data["image_height"])
            ),
        )


def with_synthetic_landmarks(landmarks: dict[str, Landmark]) -> dict[str, Landmark]:
    """Return `landmarks` plus any synthetic landmarks that can be derived.

    A synthetic landmark is the midpoint of its two source landmarks and takes
    the *lower* of their confidences, so a midpoint is never more trusted than
    its weakest input. Sources with a None `z` produce a synthetic landmark
    with a None `z`. Synthetic landmarks whose sources are absent are simply
    not created.
    """
    result = dict(landmarks)
    for name, (first_name, second_name) in SYNTHETIC_SOURCES.items():
        first = landmarks.get(first_name)
        second = landmarks.get(second_name)
        if first is None or second is None:
            continue
        z = None
        if first.z is not None and second.z is not None:
            z = (first.z + second.z) / 2.0
        result[name] = Landmark(
            x=(first.x + second.x) / 2.0,
            y=(first.y + second.y) / 2.0,
            z=z,
            confidence=min(first.confidence, second.confidence),
        )
    return result
