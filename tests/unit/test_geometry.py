"""Tests for movement geometry.

The aspect-ratio correction here exists because of a real error: comparing
normalised x with normalised y on 1280x720 recordings compressed horizontal
distances by 0.5625 and led to the wrong conclusion about camera view for
every take. These tests pin that correction down.
"""

from __future__ import annotations

import math

import pytest

from src.movement.geometry import (
    DEFAULT_ASPECT,
    angle_at,
    aspect_ratio,
    distance,
    midpoint,
    point_of,
    tilt_from_vertical,
    to_point,
)
from src.pose.models import Landmark, PoseFrame


def make_pose(width=1280, height=720, **landmarks) -> PoseFrame:
    return PoseFrame(
        timestamp_ms=0.0,
        person_confidence=0.9,
        landmarks={
            name: Landmark(x=xy[0], y=xy[1], z=0.0, confidence=0.9)
            for name, xy in landmarks.items()
        },
        source="test",
        image_width=width,
        image_height=height,
    )


class TestAspectCorrection:
    def test_uses_the_frames_own_dimensions(self):
        assert aspect_ratio(make_pose(1280, 720)) == pytest.approx(16 / 9)
        assert aspect_ratio(make_pose(640, 640)) == pytest.approx(1.0)

    def test_falls_back_when_size_is_unknown(self):
        pose = PoseFrame(0.0, 0.9, {}, "test")
        assert aspect_ratio(pose) == pytest.approx(DEFAULT_ASPECT)

    def test_horizontal_distance_is_expanded_to_match_vertical(self):
        # The defect: on 16:9, a normalised horizontal span is 0.5625 of the
        # true relative size compared with the same vertical span.
        aspect = 16 / 9
        horizontal = distance(
            to_point(Landmark(0.0, 0.5, 0.0, 1.0), aspect),
            to_point(Landmark(0.5, 0.5, 0.0, 1.0), aspect),
        )
        vertical = distance(
            to_point(Landmark(0.5, 0.0, 0.0, 1.0), aspect),
            to_point(Landmark(0.5, 0.5, 0.0, 1.0), aspect),
        )
        assert horizontal / vertical == pytest.approx(16 / 9)

    def test_the_same_movement_measures_the_same_at_any_resolution(self):
        hd = make_pose(1280, 720, a=(0.4, 0.5), b=(0.6, 0.5))
        uhd = make_pose(1920, 1080, a=(0.4, 0.5), b=(0.6, 0.5))
        assert distance(point_of(hd, "a"), point_of(hd, "b")) == pytest.approx(
            distance(point_of(uhd, "a"), point_of(uhd, "b"))
        )

    def test_a_square_frame_needs_no_correction(self):
        pose = make_pose(720, 720, a=(0.2, 0.2))
        assert point_of(pose, "a") == pytest.approx((0.2, 0.2))


class TestPointOf:
    def test_returns_none_for_a_missing_landmark(self):
        assert point_of(make_pose(), "absent") is None

    def test_midpoint_is_halfway(self):
        assert midpoint((0.0, 0.0), (1.0, 2.0)) == pytest.approx((0.5, 1.0))


class TestAngleAt:
    def test_a_right_angle_measures_ninety_degrees(self):
        assert angle_at((0.0, 1.0), (0.0, 0.0), (1.0, 0.0)) == pytest.approx(90.0)

    def test_a_straight_limb_measures_one_hundred_and_eighty(self):
        assert angle_at((0.0, 1.0), (0.0, 0.0), (0.0, -1.0)) == pytest.approx(180.0)

    def test_a_folded_limb_measures_zero(self):
        assert angle_at((0.0, 1.0), (0.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    def test_is_independent_of_limb_length(self):
        short = angle_at((0.0, 0.1), (0.0, 0.0), (0.1, 0.0))
        long = angle_at((0.0, 9.0), (0.0, 0.0), (9.0, 0.0))
        assert short == pytest.approx(long)

    def test_a_degenerate_triangle_returns_none(self):
        assert angle_at((0.0, 0.0), (0.0, 0.0), (1.0, 0.0)) is None

    def test_uncorrected_coordinates_would_give_a_wrong_angle(self):
        # Demonstrates why the correction matters: the same knee measured
        # with and without it differs by degrees, not rounding.
        aspect = 16 / 9
        hip = Landmark(0.50, 0.50, 0.0, 1.0)
        knee = Landmark(0.50, 0.70, 0.0, 1.0)
        ankle = Landmark(0.60, 0.90, 0.0, 1.0)
        corrected = angle_at(
            to_point(hip, aspect), to_point(knee, aspect), to_point(ankle, aspect)
        )
        raw = angle_at((hip.x, hip.y), (knee.x, knee.y), (ankle.x, ankle.y))
        assert abs(corrected - raw) > 5.0


class TestTiltFromVertical:
    def test_upright_is_zero(self):
        assert tilt_from_vertical((0.0, 1.0), (0.0, 0.0)) == pytest.approx(0.0)

    def test_leaning_towards_increasing_x_is_positive(self):
        assert tilt_from_vertical((0.0, 1.0), (1.0, 0.0)) == pytest.approx(45.0)

    def test_leaning_the_other_way_is_negative(self):
        assert tilt_from_vertical((0.0, 1.0), (-1.0, 0.0)) == pytest.approx(-45.0)

    def test_a_zero_length_trunk_returns_none(self):
        assert tilt_from_vertical((0.5, 0.5), (0.5, 0.5)) is None

    def test_magnitude_matches_the_geometry(self):
        angle = tilt_from_vertical((0.0, 1.0), (0.5, 0.0))
        assert angle == pytest.approx(math.degrees(math.atan2(0.5, 1.0)))
