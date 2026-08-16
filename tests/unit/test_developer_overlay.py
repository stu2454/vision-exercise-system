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


class TestFramingBanner:
    def test_the_banner_appears_when_framing_is_wrong(self):
        from src.pose.quality import DEFAULT_REQUIRED_LANDMARKS
        from src.ui.framing import assess_framing

        pose = make_pose()
        bad = assess_framing(pose, DEFAULT_REQUIRED_LANDMARKS)
        assert not bad.is_good, "fixture pose is not fully framed"
        without = draw_developer_overlay(blank_image(), pose, None, DeveloperHud())
        with_banner = draw_developer_overlay(
            blank_image(), pose, None, DeveloperHud(), framing=bad
        )
        assert not np.array_equal(without, with_banner)

    def test_the_banner_is_hidden_when_framing_is_good_outside_setup(self):
        from src.ui.framing import Framing, FramingHint

        good = FramingHint(status=Framing.GOOD, body_fill=0.8)
        plain = draw_developer_overlay(blank_image(), make_pose(), None, DeveloperHud())
        shown = draw_developer_overlay(
            blank_image(), make_pose(), None, DeveloperHud(), framing=good
        )
        assert np.array_equal(plain, shown)

    def test_setup_mode_shows_the_banner_even_when_good(self):
        # During setup the participant needs positive confirmation, not the
        # absence of a warning.
        from src.ui.framing import Framing, FramingHint

        good = FramingHint(status=Framing.GOOD, body_fill=0.8)
        plain = draw_developer_overlay(blank_image(), make_pose(), None, DeveloperHud())
        setup = draw_developer_overlay(
            blank_image(), make_pose(), None, DeveloperHud(setup_mode=True), framing=good
        )
        assert not np.array_equal(plain, setup)

    def test_the_banner_does_not_mutate_the_source_frame(self):
        from src.ui.framing import Framing, FramingHint

        image = blank_image()
        original = image.copy()
        draw_developer_overlay(
            image,
            make_pose(),
            None,
            DeveloperHud(setup_mode=True),
            framing=FramingHint(status=Framing.MOVE_BACK),
        )
        assert np.array_equal(image, original)


class TestConfidenceColour:
    def test_colour_changes_with_confidence_band(self):
        assert confidence_colour(0.9) != confidence_colour(0.45)
        assert confidence_colour(0.45) != confidence_colour(0.1)

    def test_colour_is_stable_within_a_band(self):
        assert confidence_colour(0.61) == confidence_colour(0.99)
