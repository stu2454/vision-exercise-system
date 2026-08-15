"""Tests for the MediaPipe -> canonical pose mapping.

The mapping is tested against stand-in landmark objects rather than a live
MediaPipe result, so these tests are fast, deterministic and do not need a
model file or a camera. That is only possible because the conversion is a pure
function, which is itself the property worth protecting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from src.pose.adapters.mediapipe_adapter import (
    MEDIAPIPE_LANDMARK_MAP,
    derive_person_confidence,
    empty_pose_frame,
    landmarks_to_canonical,
)
from src.pose.models import (
    HIP_CENTRE,
    LEFT_FOOT,
    LEFT_HIP,
    LEFT_SHOULDER,
    MEASURED_LANDMARKS,
    NOSE,
    RIGHT_HIP,
    SHOULDER_CENTRE,
    Landmark,
)


@dataclass
class FakeLandmark:
    """Stands in for a MediaPipe NormalizedLandmark."""

    x: float
    y: float
    z: float = 0.0
    visibility: Optional[float] = 0.9
    presence: Optional[float] = 0.9


def make_mediapipe_landmarks(
    count: int = 33, overrides: Optional[dict[int, FakeLandmark]] = None
) -> list[FakeLandmark]:
    """Build a full 33-point BlazePose landmark list with distinct values."""
    landmarks = [
        FakeLandmark(x=index / 100.0, y=index / 200.0, z=index / 1000.0)
        for index in range(count)
    ]
    for index, landmark in (overrides or {}).items():
        landmarks[index] = landmark
    return landmarks


class TestLandmarkMapping:
    def test_every_measured_canonical_landmark_is_mapped(self):
        assert set(MEDIAPIPE_LANDMARK_MAP.values()) == set(MEASURED_LANDMARKS)

    def test_no_mediapipe_index_is_mapped_twice(self):
        names = list(MEDIAPIPE_LANDMARK_MAP.values())
        assert len(names) == len(set(names))

    def test_known_indices_map_to_the_expected_names(self):
        assert MEDIAPIPE_LANDMARK_MAP[0] == NOSE
        assert MEDIAPIPE_LANDMARK_MAP[23] == LEFT_HIP
        assert MEDIAPIPE_LANDMARK_MAP[24] == RIGHT_HIP
        # 31/32 are MediaPipe's toe points, the closest match for foot.
        assert MEDIAPIPE_LANDMARK_MAP[31] == LEFT_FOOT

    def test_conversion_produces_every_canonical_landmark(self):
        result = landmarks_to_canonical(make_mediapipe_landmarks())
        assert set(MEASURED_LANDMARKS) <= set(result)
        assert SHOULDER_CENTRE in result
        assert HIP_CENTRE in result

    def test_coordinates_and_confidence_are_carried_across(self):
        landmarks = make_mediapipe_landmarks(
            overrides={23: FakeLandmark(x=0.31, y=0.62, z=-0.05, visibility=0.77)}
        )
        left_hip = landmarks_to_canonical(landmarks)[LEFT_HIP]
        assert left_hip == Landmark(x=0.31, y=0.62, z=-0.05, confidence=0.77)

    def test_face_and_hand_detail_points_are_discarded(self):
        result = landmarks_to_canonical(make_mediapipe_landmarks())
        # MediaPipe 1-10 (face) and 17-22 (hand detail) have no canonical
        # equivalent; only the 17 measured points plus 2 synthetic survive.
        assert len(result) == len(MEASURED_LANDMARKS) + 2

    def test_presence_is_used_when_visibility_is_absent(self):
        landmarks = make_mediapipe_landmarks(
            overrides={11: FakeLandmark(x=0.5, y=0.5, visibility=None, presence=0.64)}
        )
        assert landmarks_to_canonical(landmarks)[LEFT_SHOULDER].confidence == pytest.approx(0.64)

    def test_a_short_landmark_list_yields_what_it_can(self):
        # A truncated result is a pose-quality problem, not an exception.
        result = landmarks_to_canonical(make_mediapipe_landmarks(count=25))
        assert LEFT_HIP in result
        assert "left_knee" not in result

    def test_an_empty_landmark_list_yields_nothing(self):
        assert landmarks_to_canonical([]) == {}


class TestPersonConfidence:
    def test_is_the_mean_of_measured_landmark_confidences(self):
        landmarks = landmarks_to_canonical(
            make_mediapipe_landmarks(
                overrides={
                    index: FakeLandmark(x=0.5, y=0.5, visibility=0.5)
                    for index in range(33)
                }
            )
        )
        assert derive_person_confidence(landmarks) == pytest.approx(0.5)

    def test_ignores_synthetic_landmarks(self):
        # Synthetic landmarks are derived, so including them would double-count
        # the shoulders and hips.
        landmarks = {
            LEFT_HIP: Landmark(0.4, 0.5, 0.0, 1.0),
            RIGHT_HIP: Landmark(0.6, 0.5, 0.0, 0.0),
            HIP_CENTRE: Landmark(0.5, 0.5, 0.0, 0.0),
        }
        assert derive_person_confidence(landmarks) == pytest.approx(0.5)

    def test_is_zero_when_no_landmarks_are_present(self):
        assert derive_person_confidence({}) == 0.0


class TestEmptyPoseFrame:
    def test_represents_no_person_without_using_none(self):
        pose = empty_pose_frame(timestamp_ms=100.0, source="test")
        assert pose.has_person is False
        assert pose.person_confidence == 0.0
        assert pose.timestamp_ms == 100.0
        assert pose.landmarks == {}
