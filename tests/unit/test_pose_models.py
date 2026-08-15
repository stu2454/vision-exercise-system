"""Tests for the canonical pose representation."""

from __future__ import annotations

import pytest

from src.pose.models import (
    CANONICAL_LANDMARKS,
    HIP_CENTRE,
    LEFT_HIP,
    LEFT_SHOULDER,
    MEASURED_LANDMARKS,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    SHOULDER_CENTRE,
    Landmark,
    PoseFrame,
    with_synthetic_landmarks,
)


def make_landmark(x: float = 0.5, y: float = 0.5, z=0.0, confidence: float = 0.9):
    return Landmark(x=x, y=y, z=z, confidence=confidence)


class TestCanonicalLandmarkSet:
    def test_every_landmark_required_by_the_specification_is_present(self):
        # Document 03 §12 / CLAUDE.md §5 minimum set.
        required = {
            "nose",
            "left_shoulder",
            "right_shoulder",
            "left_elbow",
            "right_elbow",
            "left_wrist",
            "right_wrist",
            "left_hip",
            "right_hip",
            "left_knee",
            "right_knee",
            "left_ankle",
            "right_ankle",
            "left_heel",
            "right_heel",
            "left_foot",
            "right_foot",
        }
        assert required == set(MEASURED_LANDMARKS)

    def test_synthetic_landmarks_are_not_expected_from_the_engine(self):
        assert SHOULDER_CENTRE not in MEASURED_LANDMARKS
        assert HIP_CENTRE not in MEASURED_LANDMARKS
        assert SHOULDER_CENTRE in CANONICAL_LANDMARKS
        assert HIP_CENTRE in CANONICAL_LANDMARKS

    def test_landmark_names_are_unique(self):
        assert len(CANONICAL_LANDMARKS) == len(set(CANONICAL_LANDMARKS))


class TestSyntheticLandmarks:
    def test_hip_centre_is_the_midpoint_of_the_hips(self):
        landmarks = {
            LEFT_HIP: make_landmark(x=0.4, y=0.6, z=-0.2),
            RIGHT_HIP: make_landmark(x=0.6, y=0.5, z=-0.1),
        }
        result = with_synthetic_landmarks(landmarks)
        hip_centre = result[HIP_CENTRE]
        assert hip_centre.x == pytest.approx(0.5)
        assert hip_centre.y == pytest.approx(0.55)
        assert hip_centre.z == pytest.approx(-0.15)

    def test_synthetic_confidence_takes_the_weaker_source(self):
        landmarks = {
            LEFT_SHOULDER: make_landmark(confidence=0.95),
            RIGHT_SHOULDER: make_landmark(confidence=0.42),
        }
        result = with_synthetic_landmarks(landmarks)
        assert result[SHOULDER_CENTRE].confidence == pytest.approx(0.42)

    def test_missing_source_landmark_produces_no_synthetic_landmark(self):
        result = with_synthetic_landmarks({LEFT_HIP: make_landmark()})
        assert HIP_CENTRE not in result

    def test_missing_depth_produces_a_synthetic_landmark_without_depth(self):
        landmarks = {
            LEFT_HIP: make_landmark(z=None),
            RIGHT_HIP: make_landmark(z=0.3),
        }
        assert with_synthetic_landmarks(landmarks)[HIP_CENTRE].z is None

    def test_input_mapping_is_not_mutated(self):
        landmarks = {LEFT_HIP: make_landmark(), RIGHT_HIP: make_landmark()}
        with_synthetic_landmarks(landmarks)
        assert set(landmarks) == {LEFT_HIP, RIGHT_HIP}


class TestPoseFrameSerialisation:
    def test_round_trip_preserves_every_field(self):
        original = PoseFrame(
            timestamp_ms=1234.5,
            person_confidence=0.87,
            landmarks={
                LEFT_HIP: Landmark(0.4, 0.6, -0.2, 0.91),
                RIGHT_HIP: Landmark(0.6, 0.6, None, 0.88),
            },
            source="mediapipe:webcam:0",
            frame_index=42,
            image_width=1280,
            image_height=720,
        )
        restored = PoseFrame.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_of_a_frame_with_no_person(self):
        original = PoseFrame(
            timestamp_ms=10.0,
            person_confidence=0.0,
            landmarks={},
            source="mediapipe:webcam:0",
        )
        restored = PoseFrame.from_dict(original.to_dict())
        assert restored == original
        assert restored.has_person is False

    def test_has_person_is_true_when_landmarks_exist(self):
        pose = PoseFrame(1.0, 0.9, {LEFT_HIP: make_landmark()}, "test")
        assert pose.has_person is True

    def test_missing_reports_absent_landmarks_only(self):
        pose = PoseFrame(1.0, 0.9, {LEFT_HIP: make_landmark()}, "test")
        assert pose.missing([LEFT_HIP, RIGHT_HIP]) == [RIGHT_HIP]

    def test_get_returns_none_for_an_absent_landmark(self):
        pose = PoseFrame(1.0, 0.9, {}, "test")
        assert pose.get(LEFT_HIP) is None
