"""Tests for the movement feature layer."""

from __future__ import annotations

import pytest

from src.movement.features import (
    HIP_HEIGHT,
    HIP_VERTICAL_VELOCITY,
    KNEE_ANGLE_ASYMMETRY,
    LEFT_KNEE_ANGLE,
    MEAN_KNEE_ANGLE,
    RIGHT_KNEE_ANGLE,
    STANCE_WIDTH,
    STANCE_WIDTH_NORMALISED,
    TORSO_LENGTH,
    TRUNK_ANGLE,
    TRUNK_LATERAL_DISPLACEMENT,
    FeatureConfig,
    FeatureExtractor,
)
from src.pose.models import Landmark, PoseFrame, with_synthetic_landmarks

STEP_MS = 1000.0 / 30.0


def standing(hip_y: float = 0.55, confidence: float = 0.9, timestamp_ms: float = 0.0,
             stance: float = 0.10, lean: float = 0.0) -> PoseFrame:
    """An upright pose with hips at `hip_y` and a given stance width."""
    landmarks = {
        "left_shoulder": Landmark(0.45 + lean, hip_y - 0.25, 0.0, confidence),
        "right_shoulder": Landmark(0.55 + lean, hip_y - 0.25, 0.0, confidence),
        "left_hip": Landmark(0.47, hip_y, 0.0, confidence),
        "right_hip": Landmark(0.53, hip_y, 0.0, confidence),
        "left_knee": Landmark(0.47, hip_y + 0.18, 0.0, confidence),
        "right_knee": Landmark(0.53, hip_y + 0.18, 0.0, confidence),
        "left_ankle": Landmark(0.50 - stance / 2, hip_y + 0.36, 0.0, confidence),
        "right_ankle": Landmark(0.50 + stance / 2, hip_y + 0.36, 0.0, confidence),
        "left_foot": Landmark(0.50 - stance / 2, hip_y + 0.40, 0.0, confidence),
        "right_foot": Landmark(0.50 + stance / 2, hip_y + 0.40, 0.0, confidence),
    }
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=confidence,
        landmarks=with_synthetic_landmarks(landmarks),
        source="test",
        image_width=1280,
        image_height=720,
    )


class TestHipHeight:
    def test_higher_hips_give_a_larger_height(self):
        # Image y increases downwards; "height" must not.
        extractor = FeatureExtractor()
        low = extractor.update(standing(hip_y=0.70)).value(HIP_HEIGHT)
        extractor.reset()
        high = extractor.update(standing(hip_y=0.50)).value(HIP_HEIGHT)
        assert high > low

    def test_it_is_the_complement_of_hip_y(self):
        value = FeatureExtractor().update(standing(hip_y=0.60)).value(HIP_HEIGHT)
        assert value == pytest.approx(0.40)


class TestHipVerticalVelocity:
    def test_the_first_frame_has_no_velocity(self):
        features = FeatureExtractor().update(standing(timestamp_ms=0.0))
        assert features.value(HIP_VERTICAL_VELOCITY) is None

    def test_rising_gives_a_positive_velocity(self):
        extractor = FeatureExtractor()
        extractor.update(standing(hip_y=0.60, timestamp_ms=0.0))
        features = extractor.update(standing(hip_y=0.50, timestamp_ms=STEP_MS))
        assert features.value(HIP_VERTICAL_VELOCITY) == pytest.approx(3.0, abs=0.01)

    def test_sitting_gives_a_negative_velocity(self):
        extractor = FeatureExtractor()
        extractor.update(standing(hip_y=0.50, timestamp_ms=0.0))
        features = extractor.update(standing(hip_y=0.60, timestamp_ms=STEP_MS))
        assert features.value(HIP_VERTICAL_VELOCITY) < 0

    def test_velocity_is_not_computed_across_a_long_gap(self):
        # A "velocity" measured across dropped frames is not a measurement of
        # movement.
        extractor = FeatureExtractor(FeatureConfig(maximum_elapsed_ms=250))
        extractor.update(standing(hip_y=0.60, timestamp_ms=0.0))
        features = extractor.update(standing(hip_y=0.50, timestamp_ms=2000.0))
        assert features.value(HIP_VERTICAL_VELOCITY) is None

    def test_velocity_is_not_computed_across_a_zero_interval(self):
        extractor = FeatureExtractor()
        extractor.update(standing(timestamp_ms=100.0))
        features = extractor.update(standing(timestamp_ms=100.0))
        assert features.value(HIP_VERTICAL_VELOCITY) is None

    def test_velocity_is_rate_based_not_per_frame(self):
        # Same displacement over twice the time is half the velocity.
        one = FeatureExtractor()
        one.update(standing(hip_y=0.60, timestamp_ms=0.0))
        fast = one.update(standing(hip_y=0.50, timestamp_ms=50.0)).value(
            HIP_VERTICAL_VELOCITY
        )
        two = FeatureExtractor()
        two.update(standing(hip_y=0.60, timestamp_ms=0.0))
        slow = two.update(standing(hip_y=0.50, timestamp_ms=100.0)).value(
            HIP_VERTICAL_VELOCITY
        )
        assert fast == pytest.approx(slow * 2, rel=0.01)


class TestKneeAngles:
    def test_a_straight_leg_is_near_one_hundred_and_eighty(self):
        # Knees sit at x = 0.47 / 0.53, so a stance of 0.06 puts the ankles
        # directly beneath them: the only genuinely straight leg the fixture
        # can make. A wider stance angles the shin outwards and legitimately
        # reads below 180.
        features = FeatureExtractor().update(standing(stance=0.06))
        assert features.value(LEFT_KNEE_ANGLE) == pytest.approx(180.0, abs=1.0)

    def test_a_wider_stance_angles_the_shin_outwards(self):
        narrow = FeatureExtractor().update(standing(stance=0.06))
        wide = FeatureExtractor().update(standing(stance=0.20))
        assert wide.value(LEFT_KNEE_ANGLE) < narrow.value(LEFT_KNEE_ANGLE)

    def test_mean_knee_angle_averages_both_sides(self):
        features = FeatureExtractor().update(standing())
        left = features.value(LEFT_KNEE_ANGLE)
        right = features.value(RIGHT_KNEE_ANGLE)
        assert features.value(MEAN_KNEE_ANGLE) == pytest.approx((left + right) / 2)

    def test_symmetric_posture_has_no_asymmetry(self):
        features = FeatureExtractor().update(standing())
        assert features.value(KNEE_ANGLE_ASYMMETRY) == pytest.approx(0.0, abs=1.0)

    def test_bending_one_knee_creates_asymmetry(self):
        pose = standing()
        bent = dict(pose.landmarks)
        bent["left_ankle"] = Landmark(0.60, 0.75, 0.0, 0.9)
        flexed = PoseFrame(0.0, 0.9, bent, "test", None, 1280, 720)
        features = FeatureExtractor().update(flexed)
        assert features.value(KNEE_ANGLE_ASYMMETRY) > 5.0


class TestTrunk:
    def test_an_upright_trunk_is_near_zero_degrees(self):
        features = FeatureExtractor().update(standing())
        assert features.value(TRUNK_ANGLE) == pytest.approx(0.0, abs=1.0)

    def test_leaning_tilts_the_trunk_angle(self):
        features = FeatureExtractor().update(standing(lean=0.08))
        assert abs(features.value(TRUNK_ANGLE)) > 5.0

    def test_lateral_displacement_is_zero_when_centred(self):
        features = FeatureExtractor().update(standing())
        assert features.value(TRUNK_LATERAL_DISPLACEMENT) == pytest.approx(0.0, abs=0.01)


class TestStance:
    def test_a_wider_stance_measures_wider(self):
        narrow = FeatureExtractor().update(standing(stance=0.05)).value(STANCE_WIDTH)
        wide = FeatureExtractor().update(standing(stance=0.20)).value(STANCE_WIDTH)
        assert wide > narrow

    def test_normalised_stance_is_independent_of_camera_distance(self):
        # The point of body-normalised units: the same posture at two
        # distances from the camera must give the same value.
        near = standing(hip_y=0.55, stance=0.20)
        far_landmarks = {
            name: Landmark(0.5 + (lm.x - 0.5) * 0.5, 0.5 + (lm.y - 0.5) * 0.5,
                           lm.z, lm.confidence)
            for name, lm in near.landmarks.items()
        }
        far = PoseFrame(0.0, 0.9, far_landmarks, "test", None, 1280, 720)

        near_raw = FeatureExtractor().update(near).value(STANCE_WIDTH)
        far_raw = FeatureExtractor().update(far).value(STANCE_WIDTH)
        near_norm = FeatureExtractor().update(near).value(STANCE_WIDTH_NORMALISED)
        far_norm = FeatureExtractor().update(far).value(STANCE_WIDTH_NORMALISED)

        assert far_raw == pytest.approx(near_raw / 2, rel=0.01)
        assert far_norm == pytest.approx(near_norm, rel=0.01)


class TestValidity:
    def test_low_confidence_makes_a_feature_invalid(self):
        features = FeatureExtractor(FeatureConfig(minimum_confidence=0.5)).update(
            standing(confidence=0.2)
        )
        assert features.get(HIP_HEIGHT).valid is False
        assert features.value(HIP_HEIGHT) is None

    def test_an_invalid_feature_still_reports_its_confidence(self):
        features = FeatureExtractor(FeatureConfig(minimum_confidence=0.5)).update(
            standing(confidence=0.2)
        )
        assert features.get(HIP_HEIGHT).confidence == pytest.approx(0.2)

    def test_a_missing_landmark_makes_dependent_features_invalid(self):
        pose = standing()
        without_ankles = {
            n: lm for n, lm in pose.landmarks.items() if "ankle" not in n
        }
        stripped = PoseFrame(0.0, 0.9, without_ankles, "test", None, 1280, 720)
        features = FeatureExtractor().update(stripped)
        assert features.value(STANCE_WIDTH) is None
        assert features.value(HIP_HEIGHT) is not None, "unrelated features survive"

    def test_an_empty_pose_yields_no_valid_features(self):
        features = FeatureExtractor().update(PoseFrame(0.0, 0.0, {}, "test"))
        assert features.valid_names() == []

    def test_confidence_takes_the_weakest_required_landmark(self):
        pose = standing(confidence=0.9)
        weakened = dict(pose.landmarks)
        weakened["left_ankle"] = Landmark(0.45, 0.91, 0.0, 0.4)
        pose = PoseFrame(0.0, 0.9, weakened, "test", None, 1280, 720)
        features = FeatureExtractor().update(pose)
        assert features.get(STANCE_WIDTH).confidence == pytest.approx(0.4)


class TestDeterminism:
    def test_reset_reproduces_the_same_features(self):
        extractor = FeatureExtractor()
        frames = [
            standing(hip_y=0.55 + i * 0.005, timestamp_ms=i * STEP_MS)
            for i in range(20)
        ]
        first = [extractor.update(f).to_dict() for f in frames]
        extractor.reset()
        second = [extractor.update(f).to_dict() for f in frames]
        assert first == second

    def test_features_declare_their_units(self):
        features = FeatureExtractor().update(standing())
        assert features.get(HIP_HEIGHT).units == "image_heights"
        assert features.get(HIP_VERTICAL_VELOCITY).units == "image_heights_per_second"
        assert features.get(LEFT_KNEE_ANGLE).units == "degrees"
        assert features.get(STANCE_WIDTH_NORMALISED).units == "torso_lengths"

    def test_torso_length_is_positive(self):
        assert FeatureExtractor().update(standing()).value(TORSO_LENGTH) > 0
