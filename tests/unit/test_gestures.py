"""Tests for the start-gesture detector.

The gesture exists so that nothing is measured until the participant is
standing where they intend to exercise. Its two failure modes matter in
opposite directions: firing on ordinary movement would start calibration at
the wrong moment, and failing to fire would strand the participant with their
arm in the air.
"""

from __future__ import annotations

import pytest

from src.movement.gestures import (
    ArmRaiseConfig,
    ArmRaiseDetector,
    arm_is_raised,
)
from src.pose.models import Landmark, PoseFrame

STEP_MS = 1000.0 / 30.0


def pose_with(timestamp_ms: float = 0.0, confidence: float = 0.9, **points) -> PoseFrame:
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=confidence,
        landmarks={
            name: Landmark(x=xy[0], y=xy[1], z=0.0, confidence=confidence)
            for name, xy in points.items()
        },
        source="test",
        image_width=1280,
        image_height=720,
    )


def raised_arm(timestamp_ms: float = 0.0, confidence: float = 0.9) -> PoseFrame:
    """Upper arm out, forearm up: roughly a right angle at the elbow."""
    return pose_with(
        timestamp_ms,
        confidence,
        left_shoulder=(0.45, 0.40),
        left_elbow=(0.32, 0.40),
        left_wrist=(0.32, 0.25),
    )


def arm_down(timestamp_ms: float = 0.0) -> PoseFrame:
    return pose_with(
        timestamp_ms,
        left_shoulder=(0.45, 0.40),
        left_elbow=(0.44, 0.55),
        left_wrist=(0.43, 0.70),
    )


class TestGeometry:
    def test_a_bent_raised_arm_is_recognised(self):
        assert arm_is_raised(raised_arm(), ArmRaiseConfig()) == "left"

    def test_an_arm_at_the_side_is_not(self):
        assert arm_is_raised(arm_down(), ArmRaiseConfig()) is None

    def test_a_straight_arm_overhead_is_not(self):
        # Excluded deliberately: it is close to arm positions that occur
        # naturally while standing up.
        straight = pose_with(
            left_shoulder=(0.45, 0.40),
            left_elbow=(0.45, 0.25),
            left_wrist=(0.45, 0.10),
        )
        assert arm_is_raised(straight, ArmRaiseConfig()) is None

    def test_a_bent_arm_below_the_shoulder_is_not(self):
        low = pose_with(
            left_shoulder=(0.45, 0.40),
            left_elbow=(0.32, 0.55),
            left_wrist=(0.32, 0.45),
        )
        assert arm_is_raised(low, ArmRaiseConfig()) is None

    def test_either_arm_is_accepted(self):
        # Mirroring makes the canonical side labels the opposite of the
        # participant's own, so the instruction cannot depend on one arm.
        right = pose_with(
            right_shoulder=(0.55, 0.40),
            right_elbow=(0.68, 0.40),
            right_wrist=(0.68, 0.25),
        )
        assert arm_is_raised(right, ArmRaiseConfig()) == "right"

    def test_low_confidence_landmarks_are_ignored(self):
        assert arm_is_raised(raised_arm(confidence=0.2), ArmRaiseConfig()) is None

    def test_a_frame_with_no_person_is_ignored(self):
        assert arm_is_raised(PoseFrame(0.0, 0.0, {}, "test"), ArmRaiseConfig()) is None

    def test_a_missing_wrist_is_ignored(self):
        partial = pose_with(left_shoulder=(0.45, 0.40), left_elbow=(0.32, 0.40))
        assert arm_is_raised(partial, ArmRaiseConfig()) is None

    def test_the_accepted_angle_range_is_configurable(self):
        strict = ArmRaiseConfig(minimum_elbow_angle=88.0, maximum_elbow_angle=92.0)
        assert arm_is_raised(raised_arm(), strict) == "left"
        impossible = ArmRaiseConfig(minimum_elbow_angle=170.0, maximum_elbow_angle=180.0)
        assert arm_is_raised(raised_arm(), impossible) is None


class TestHold:
    def test_it_does_not_fire_immediately(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=500))
        assert detector.update(raised_arm(0.0)).triggered is False

    def test_it_fires_once_the_hold_completes(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=500))
        fired = False
        for index in range(30):
            fired = fired or detector.update(raised_arm(index * STEP_MS)).triggered
        assert fired

    def test_it_fires_only_once(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=200))
        fires = sum(
            1 for index in range(60) if detector.update(raised_arm(index * STEP_MS)).triggered
        )
        assert fires == 1

    def test_lowering_the_arm_restarts_the_hold(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=500))
        for index in range(10):
            detector.update(raised_arm(index * STEP_MS))
        detector.update(arm_down(10 * STEP_MS))
        state = detector.update(raised_arm(11 * STEP_MS))
        assert state.held_ms == 0.0
        assert state.triggered is False

    def test_progress_reports_how_far_through_the_hold_it_is(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=1000))
        detector.update(raised_arm(0.0))
        state = detector.update(raised_arm(500.0))
        assert state.progress == pytest.approx(0.5)
        assert state.raised is True

    def test_progress_is_zero_when_no_arm_is_raised(self):
        detector = ArmRaiseDetector()
        assert detector.update(arm_down()).progress == 0.0

    def test_the_hold_is_timed_not_counted_in_frames(self):
        # Must behave the same at 15 fps as at 30.
        slow = ArmRaiseDetector(ArmRaiseConfig(hold_ms=600))
        fired_slow = False
        for index in range(12):  # 12 frames at 15 fps = 733 ms
            fired_slow = fired_slow or slow.update(raised_arm(index * 66.6)).triggered
        fast = ArmRaiseDetector(ArmRaiseConfig(hold_ms=600))
        fired_fast = False
        for index in range(12):  # 12 frames at 30 fps = 367 ms
            fired_fast = fired_fast or fast.update(raised_arm(index * 33.3)).triggered
        assert fired_slow and not fired_fast

    def test_reset_allows_it_to_fire_again(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=200))
        for index in range(30):
            detector.update(raised_arm(index * STEP_MS))
        detector.reset()
        fired = False
        for index in range(30, 60):
            fired = fired or detector.update(raised_arm(index * STEP_MS)).triggered
        assert fired


class TestAgainstExerciseMovement:
    def test_standing_up_does_not_trigger_the_gesture(self):
        # The arms swing forward and up during a sit-to-stand. If that read
        # as a start signal the exercise would restart mid-set.
        detector = ArmRaiseDetector()
        fired = False
        for index in range(120):
            # Arms forward and rising, but elbows nearly straight and wrists
            # never above the shoulders.
            y = 0.60 - index * 0.001
            pose = pose_with(
                index * STEP_MS,
                left_shoulder=(0.45, y),
                left_elbow=(0.42, y + 0.12),
                left_wrist=(0.40, y + 0.24),
            )
            fired = fired or detector.update(pose).triggered
        assert not fired


class TestStopGesture:
    def test_two_arms_are_required(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=100), required_arms=2)
        fired = False
        for index in range(30):
            fired = fired or detector.update(raised_arm(index * STEP_MS)).triggered
        assert not fired, "one arm must not finish the exercise"

    def test_both_arms_trigger_it(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=100), required_arms=2)
        fired = False
        for index in range(30):
            pose = pose_with(
                index * STEP_MS,
                left_shoulder=(0.45, 0.40),
                left_elbow=(0.32, 0.40),
                left_wrist=(0.32, 0.25),
                right_shoulder=(0.55, 0.40),
                right_elbow=(0.68, 0.40),
                right_wrist=(0.68, 0.25),
            )
            fired = fired or detector.update(pose).triggered
        assert fired

    def test_the_side_is_reported_as_both(self):
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=0), required_arms=2)
        pose = pose_with(
            0.0,
            left_shoulder=(0.45, 0.40),
            left_elbow=(0.32, 0.40),
            left_wrist=(0.32, 0.25),
            right_shoulder=(0.55, 0.40),
            right_elbow=(0.68, 0.40),
            right_wrist=(0.68, 0.25),
        )
        assert detector.update(pose).side == "both"

    def test_an_invalid_arm_count_is_rejected(self):
        with pytest.raises(ValueError, match="required_arms"):
            ArmRaiseDetector(required_arms=3)

    def test_the_stop_hold_can_be_longer_than_the_start_hold(self):
        # A stop that fires by accident ends the attempt, so it is worth
        # demanding more deliberation than a start.
        detector = ArmRaiseDetector(ArmRaiseConfig(hold_ms=1500), required_arms=2)
        both = pose_with(
            0.0,
            left_shoulder=(0.45, 0.40), left_elbow=(0.32, 0.40), left_wrist=(0.32, 0.25),
            right_shoulder=(0.55, 0.40), right_elbow=(0.68, 0.40), right_wrist=(0.68, 0.25),
        )
        detector.update(both)
        halfway = pose_with(
            750.0,
            left_shoulder=(0.45, 0.40), left_elbow=(0.32, 0.40), left_wrist=(0.32, 0.25),
            right_shoulder=(0.55, 0.40), right_elbow=(0.68, 0.40), right_wrist=(0.68, 0.25),
        )
        assert detector.update(halfway).triggered is False
