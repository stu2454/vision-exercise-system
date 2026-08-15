"""MediaPipe Pose Landmarker adapter (Builds 1 and 2).

This is the only module in the project permitted to know MediaPipe landmark
indices, result objects or field names (Document 03 §11.1, ADR-007). MediaPipe
is an implementation detail; everything downstream sees `PoseFrame`.

Confidence semantics
--------------------
MediaPipe reports `visibility` (the landmark is in frame and not occluded) and
`presence` (the landmark exists in the image at all). We map `visibility` to
canonical `confidence`, falling back to `presence` where visibility is absent,
because occlusion is the failure mode that matters most for exercise scoring.

MediaPipe supplies no per-person detection score in the Tasks API, so
`person_confidence` is derived here as the mean confidence of the measured
canonical landmarks. It is a proxy, not a model output.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from src.camera.base import Frame
from src.pose.base import PoseEngine, PoseEngineError, PoseEngineInfo
from src.pose.models import (
    LEFT_ANKLE,
    LEFT_ELBOW,
    LEFT_FOOT,
    LEFT_HEEL,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    MEASURED_LANDMARKS,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_ELBOW,
    RIGHT_FOOT,
    RIGHT_HEEL,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    Landmark,
    PoseFrame,
    with_synthetic_landmarks,
)

MEDIAPIPE_LANDMARK_MAP: dict[int, str] = {
    0: NOSE,
    11: LEFT_SHOULDER,
    12: RIGHT_SHOULDER,
    13: LEFT_ELBOW,
    14: RIGHT_ELBOW,
    15: LEFT_WRIST,
    16: RIGHT_WRIST,
    23: LEFT_HIP,
    24: RIGHT_HIP,
    25: LEFT_KNEE,
    26: RIGHT_KNEE,
    27: LEFT_ANKLE,
    28: RIGHT_ANKLE,
    29: LEFT_HEEL,
    30: RIGHT_HEEL,
    31: LEFT_FOOT,
    32: RIGHT_FOOT,
}
"""MediaPipe BlazePose 33-point index -> canonical landmark name.

MediaPipe indices 31/32 are `left_foot_index` / `right_foot_index`, the toe
points; they are the closest available match for the canonical `left_foot` /
`right_foot`. Face and hand detail points (1-10, 17-22) have no canonical
equivalent and are discarded.
"""


def landmarks_to_canonical(
    mediapipe_landmarks: Sequence[Any],
) -> dict[str, Landmark]:
    """Convert one MediaPipe landmark list into canonical landmarks.

    Pure and free of MediaPipe imports, so it can be unit-tested against
    simple stand-in objects exposing x/y/z/visibility/presence.

    Indices beyond the known map are ignored, and a short landmark list yields
    only the landmarks it can supply, rather than raising. A pose engine that
    returns fewer points than expected is a pose-quality problem, and is
    reported by the pose-quality layer rather than as an exception here.
    """
    canonical: dict[str, Landmark] = {}
    for index, name in MEDIAPIPE_LANDMARK_MAP.items():
        if index >= len(mediapipe_landmarks):
            continue
        raw = mediapipe_landmarks[index]
        visibility = getattr(raw, "visibility", None)
        presence = getattr(raw, "presence", None)
        confidence = visibility if visibility is not None else presence
        z = getattr(raw, "z", None)
        canonical[name] = Landmark(
            x=float(raw.x),
            y=float(raw.y),
            z=None if z is None else float(z),
            confidence=0.0 if confidence is None else float(confidence),
        )
    return with_synthetic_landmarks(canonical)


def derive_person_confidence(landmarks: dict[str, Landmark]) -> float:
    """Mean confidence across measured canonical landmarks, or 0.0 if none."""
    confidences = [
        landmarks[name].confidence
        for name in MEASURED_LANDMARKS
        if name in landmarks
    ]
    if not confidences:
        return 0.0
    return float(sum(confidences) / len(confidences))


def empty_pose_frame(
    timestamp_ms: float, source: str, frame: Optional[Frame] = None
) -> PoseFrame:
    """Build the canonical representation of "no person detected"."""
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=0.0,
        landmarks={},
        source=source,
        frame_index=None if frame is None else frame.index,
        image_width=None if frame is None else frame.width,
        image_height=None if frame is None else frame.height,
    )


class MediaPipePoseEngine(PoseEngine):
    """Runs MediaPipe Pose Landmarker in VIDEO mode.

    VIDEO mode is used rather than LIVE_STREAM because it is synchronous and
    timestamp-driven: the same input frames and timestamps produce the same
    results on every run, which is what makes recorded video replay
    reproducible (Document 03 §26). LIVE_STREAM delivers results through a
    callback and may drop frames under load, which would not be reproducible.

    V0.1 tracks a single participant (`num_poses=1`, Document 03 §37).
    Multi-person detection is deliberately not enabled yet; distinguishing a
    genuine second person from a duplicate detection needs testing before any
    behaviour depends on it.
    """

    def __init__(
        self,
        model_path: Path | str,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        """
        Args:
            model_path: Path to a `.task` Pose Landmarker bundle.
            min_detection_confidence: MediaPipe person-detection threshold.
            min_presence_confidence: MediaPipe landmark-presence threshold.
            min_tracking_confidence: MediaPipe tracking-persistence threshold.
        """
        self._model_path = Path(model_path)
        self._min_detection_confidence = min_detection_confidence
        self._min_presence_confidence = min_presence_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._landmarker: Any = None
        self._mp: Any = None
        self._last_inference_ms: Optional[float] = None
        self._last_timestamp_ms = -1

    def start(self) -> None:
        if not self._model_path.exists():
            raise PoseEngineError(
                "POSE_ENGINE_FAILED",
                f"Pose model not found: {self._model_path}. "
                "Run tools/fetch_models.py to download it.",
            )
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
        except ImportError as exc:  # pragma: no cover - environment failure
            raise PoseEngineError(
                "POSE_ENGINE_FAILED", f"MediaPipe is not available: {exc}"
            ) from exc

        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(self._model_path)
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=self._min_detection_confidence,
            min_pose_presence_confidence=self._min_presence_confidence,
            min_tracking_confidence=self._min_tracking_confidence,
            output_segmentation_masks=False,
        )
        try:
            self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        except Exception as exc:  # pragma: no cover - model load failure
            raise PoseEngineError(
                "POSE_ENGINE_FAILED", f"Could not create pose landmarker: {exc}"
            ) from exc
        self._mp = mp
        self._last_timestamp_ms = -1

    def estimate(self, frame: Frame, source: str) -> PoseFrame:
        if self._landmarker is None or self._mp is None:
            raise PoseEngineError("POSE_ENGINE_FAILED", "Pose engine was not started.")

        # MediaPipe VIDEO mode requires strictly increasing integer millisecond
        # timestamps. Live capture can deliver two frames inside the same
        # millisecond, so nudge forward rather than let inference reject them.
        timestamp_ms = int(frame.timestamp_ms)
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        rgb = np.ascontiguousarray(frame.image[:, :, ::-1])
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        started = time.perf_counter()
        try:
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception as exc:  # pragma: no cover - inference failure
            raise PoseEngineError(
                "POSE_ENGINE_FAILED", f"Pose inference failed: {exc}"
            ) from exc
        self._last_inference_ms = (time.perf_counter() - started) * 1000.0

        pose_landmarks = getattr(result, "pose_landmarks", None) or []
        if not pose_landmarks:
            return empty_pose_frame(frame.timestamp_ms, source, frame)

        landmarks = landmarks_to_canonical(pose_landmarks[0])
        return PoseFrame(
            timestamp_ms=frame.timestamp_ms,
            person_confidence=derive_person_confidence(landmarks),
            landmarks=landmarks,
            source=source,
            frame_index=frame.index,
            image_width=frame.width,
            image_height=frame.height,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        self._mp = None

    def info(self) -> PoseEngineInfo:
        return PoseEngineInfo(
            engine="mediapipe_pose_landmarker",
            model_version=self._model_path.name,
            detail=(
                f"detection={self._min_detection_confidence} "
                f"presence={self._min_presence_confidence} "
                f"tracking={self._min_tracking_confidence}"
            ),
        )

    @property
    def last_inference_ms(self) -> Optional[float]:
        return self._last_inference_ms
