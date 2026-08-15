"""Tests for the pose-quality subsystem."""

from __future__ import annotations

import pytest

from src.pose.models import Landmark, PoseFrame
from src.pose.quality import (
    DEFAULT_REQUIRED_LANDMARKS,
    PoseQualityAssessor,
    PoseQualityConfig,
    PoseQualityStatus,
)

CONFIG = PoseQualityConfig(frames_to_worsen=1, frames_to_improve=1)
"""Hysteresis disabled, so instantaneous rules can be tested in isolation."""


def make_pose(
    confidence: float = 0.9,
    timestamp_ms: float = 0.0,
    x: float = 0.5,
    y: float = 0.5,
    omit: tuple[str, ...] = (),
    overrides: dict[str, Landmark] | None = None,
    person_confidence: float | None = None,
) -> PoseFrame:
    """Build a pose frame with all required landmarks unless told otherwise."""
    landmarks = {
        name: Landmark(x=x, y=y, z=0.0, confidence=confidence)
        for name in DEFAULT_REQUIRED_LANDMARKS
        if name not in omit
    }
    landmarks.update(overrides or {})
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=confidence if person_confidence is None else person_confidence,
        landmarks=landmarks,
        source="test",
    )


def settle(assessor: PoseQualityAssessor, pose_factory, frames: int = 10):
    """Feed repeated frames so hysteresis reaches a steady state."""
    report = None
    for index in range(frames):
        report = assessor.assess(pose_factory(index))
    assert report is not None
    return report


class TestInstantaneousStatus:
    def test_confident_complete_pose_is_good(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(make_pose(confidence=0.95))
        assert report.status is PoseQualityStatus.GOOD
        assert report.reasons == []
        assert report.scoring_permitted is True

    def test_no_person_is_insufficient(self):
        assessor = PoseQualityAssessor(CONFIG)
        empty = PoseFrame(0.0, 0.0, {}, "test")
        report = assessor.assess(empty)
        assert report.status is PoseQualityStatus.INSUFFICIENT
        assert report.reasons == ["person_not_detected"]
        assert report.scoring_permitted is False

    def test_missing_required_landmark_is_insufficient(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(make_pose(omit=("left_knee",)))
        assert report.status is PoseQualityStatus.INSUFFICIENT
        assert report.missing_required == ["left_knee"]
        assert "required_landmarks_missing" in report.reasons

    def test_required_landmark_below_minimum_confidence_is_insufficient(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(
            make_pose(overrides={"left_knee": Landmark(0.5, 0.5, 0.0, 0.1)})
        )
        assert report.status is PoseQualityStatus.INSUFFICIENT
        assert report.low_confidence == ["left_knee"]

    def test_required_landmark_between_thresholds_is_degraded(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(
            make_pose(overrides={"left_knee": Landmark(0.5, 0.5, 0.0, 0.45)})
        )
        assert report.status is PoseQualityStatus.DEGRADED
        assert report.uncertain == ["left_knee"]
        assert report.scoring_permitted is True

    def test_landmark_at_the_image_edge_is_degraded(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(
            make_pose(overrides={"left_ankle": Landmark(0.5, 0.995, 0.0, 0.9)})
        )
        assert report.status is PoseQualityStatus.DEGRADED
        assert report.clipped == ["left_ankle"]
        assert "required_landmarks_clipped" in report.reasons

    def test_low_person_confidence_is_insufficient(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(make_pose(confidence=0.9, person_confidence=0.1))
        assert report.status is PoseQualityStatus.INSUFFICIENT
        assert "person_confidence_below_floor" in report.reasons

    def test_reported_confidence_is_the_mean_of_required_landmarks(self):
        assessor = PoseQualityAssessor(CONFIG)
        report = assessor.assess(make_pose(confidence=0.8))
        assert report.confidence == pytest.approx(0.8)


class TestImplausibleMotion:
    def test_a_large_fast_jump_is_degraded(self):
        assessor = PoseQualityAssessor(CONFIG)
        assessor.assess(make_pose(timestamp_ms=0.0, x=0.2))
        # 0.6 normalised units in 33 ms is roughly 18 units/second.
        report = assessor.assess(make_pose(timestamp_ms=33.0, x=0.8))
        assert report.status is PoseQualityStatus.DEGRADED
        assert "implausible_landmark_motion" in report.reasons

    def test_ordinary_movement_is_not_flagged(self):
        assessor = PoseQualityAssessor(CONFIG)
        assessor.assess(make_pose(timestamp_ms=0.0, y=0.50))
        report = assessor.assess(make_pose(timestamp_ms=33.0, y=0.54))
        assert report.implausible_jumps == []
        assert report.status is PoseQualityStatus.GOOD

    def test_the_first_frame_is_never_flagged_as_a_jump(self):
        assessor = PoseQualityAssessor(CONFIG)
        assert assessor.assess(make_pose(x=0.9)).implausible_jumps == []

    def test_reset_clears_motion_history(self):
        assessor = PoseQualityAssessor(CONFIG)
        assessor.assess(make_pose(timestamp_ms=0.0, x=0.2))
        assessor.reset()
        report = assessor.assess(make_pose(timestamp_ms=33.0, x=0.8))
        assert report.implausible_jumps == []


class TestHysteresis:
    def test_status_starts_insufficient(self):
        assert PoseQualityAssessor().status is PoseQualityStatus.INSUFFICIENT

    def test_recovery_requires_sustained_good_frames(self):
        config = PoseQualityConfig(frames_to_worsen=2, frames_to_improve=5)
        assessor = PoseQualityAssessor(config)
        for _ in range(4):
            report = assessor.assess(make_pose(confidence=0.95))
            assert report.status is PoseQualityStatus.INSUFFICIENT
            assert report.instantaneous_status is PoseQualityStatus.GOOD
        assert assessor.assess(make_pose(confidence=0.95)).status is PoseQualityStatus.GOOD

    def test_a_single_bad_frame_does_not_stop_scoring(self):
        config = PoseQualityConfig(frames_to_worsen=2, frames_to_improve=5)
        assessor = PoseQualityAssessor(config)
        settle(assessor, lambda index: make_pose(timestamp_ms=index * 33.0))
        assert assessor.status is PoseQualityStatus.GOOD

        report = assessor.assess(PoseFrame(1000.0, 0.0, {}, "test"))
        assert report.instantaneous_status is PoseQualityStatus.INSUFFICIENT
        assert report.status is PoseQualityStatus.GOOD, "one dropped frame must not pause scoring"

    def test_sustained_loss_does_stop_scoring(self):
        config = PoseQualityConfig(frames_to_worsen=2, frames_to_improve=5)
        assessor = PoseQualityAssessor(config)
        settle(assessor, lambda index: make_pose(timestamp_ms=index * 33.0))

        assessor.assess(PoseFrame(1000.0, 0.0, {}, "test"))
        report = assessor.assess(PoseFrame(1033.0, 0.0, {}, "test"))
        assert report.status is PoseQualityStatus.INSUFFICIENT

    def test_flapping_between_two_statuses_does_not_change_the_report(self):
        config = PoseQualityConfig(frames_to_worsen=3, frames_to_improve=3)
        assessor = PoseQualityAssessor(config)
        settle(assessor, lambda index: make_pose(timestamp_ms=index * 33.0), frames=20)
        assert assessor.status is PoseQualityStatus.GOOD

        for index in range(10):
            bad = index % 2 == 0
            pose = make_pose(
                timestamp_ms=1000.0 + index * 33.0,
                overrides=(
                    {"left_knee": Landmark(0.5, 0.5, 0.0, 0.45)} if bad else {}
                ),
            )
            assert assessor.assess(pose).status is PoseQualityStatus.GOOD
