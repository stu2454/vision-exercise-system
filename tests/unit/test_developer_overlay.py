"""Tests for the developer overlay."""

from __future__ import annotations

import numpy as np

from src.pose.models import LEFT_HIP, LEFT_KNEE, RIGHT_HIP, Landmark, PoseFrame
from src.pose.quality import PoseQualityAssessor, PoseQualityConfig
from src.ui.developer import DeveloperHud, confidence_colour, draw_developer_overlay


def blank_image(width: int = 320, height: int = 240) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def make_pose() -> PoseFrame:
    return PoseFrame(
        timestamp_ms=1000.0,
        person_confidence=0.9,
        landmarks={
            LEFT_HIP: Landmark(0.45, 0.55, 0.0, 0.9),
            RIGHT_HIP: Landmark(0.55, 0.55, 0.0, 0.9),
            LEFT_KNEE: Landmark(0.45, 0.75, 0.0, 0.4),
        },
        source="test",
    )


def assess(pose: PoseFrame):
    return PoseQualityAssessor(PoseQualityConfig()).assess(pose)


class TestOverlayDoesNotMutateTheFrame:
    def test_the_source_image_is_left_untouched(self):
        # The frame written to a video recording must not contain overlay
        # graphics, or the recording would no longer be raw input for replay.
        image = blank_image()
        original = image.copy()
        draw_developer_overlay(image, make_pose(), assess(make_pose()), DeveloperHud())
        assert np.array_equal(image, original)

    def test_the_returned_image_is_annotated(self):
        image = blank_image()
        annotated = draw_developer_overlay(
            image, make_pose(), assess(make_pose()), DeveloperHud()
        )
        assert annotated.shape == image.shape
        assert not np.array_equal(annotated, image)


class TestOverlayRobustness:
    def test_a_frame_with_no_person_still_renders(self):
        empty = PoseFrame(0.0, 0.0, {}, "test")
        annotated = draw_developer_overlay(
            blank_image(), empty, assess(empty), DeveloperHud()
        )
        assert annotated.shape == (240, 320, 3)

    def test_a_missing_quality_report_still_renders(self):
        annotated = draw_developer_overlay(
            blank_image(), make_pose(), None, DeveloperHud()
        )
        assert annotated.shape == (240, 320, 3)

    def test_partial_landmarks_do_not_break_skeleton_drawing(self):
        # Connections whose endpoints are absent are skipped, not guessed.
        pose = PoseFrame(0.0, 0.9, {LEFT_HIP: Landmark(0.4, 0.5, 0.0, 0.9)}, "test")
        annotated = draw_developer_overlay(blank_image(), pose, None, DeveloperHud())
        assert annotated.shape == (240, 320, 3)

    def test_landmarks_outside_the_frame_do_not_raise(self):
        pose = PoseFrame(
            0.0,
            0.9,
            {
                LEFT_HIP: Landmark(-0.4, 1.9, 0.0, 0.9),
                RIGHT_HIP: Landmark(1.4, -0.2, 0.0, 0.9),
            },
            "test",
        )
        draw_developer_overlay(blank_image(), pose, None, DeveloperHud())

    def test_skeleton_can_be_switched_off(self):
        pose = make_pose()
        with_skeleton = draw_developer_overlay(
            blank_image(), pose, None, DeveloperHud(show_skeleton=True)
        )
        without_skeleton = draw_developer_overlay(
            blank_image(), pose, None, DeveloperHud(show_skeleton=False)
        )
        assert not np.array_equal(with_skeleton, without_skeleton)


class TestConfidenceColour:
    def test_colour_changes_with_confidence_band(self):
        assert confidence_colour(0.9) != confidence_colour(0.45)
        assert confidence_colour(0.45) != confidence_colour(0.1)

    def test_colour_is_stable_within_a_band(self):
        assert confidence_colour(0.61) == confidence_colour(0.99)
