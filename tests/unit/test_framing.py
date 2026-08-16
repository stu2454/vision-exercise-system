"""Tests for camera framing assessment.

Written against the exact failure that spoiled two development recordings:
the participant's legs below the bottom edge, with the pose engine still
reporting extrapolated off-screen coordinates at near-zero confidence.
"""

from __future__ import annotations

import pytest

from src.pose.models import Landmark, PoseFrame
from src.pose.quality import DEFAULT_REQUIRED_LANDMARKS
from src.ui.framing import Framing, ankles_visible, assess_framing

REQUIRED = DEFAULT_REQUIRED_LANDMARKS


def make_pose(positions: dict[str, tuple[float, float]], confidence=0.9) -> PoseFrame:
    return PoseFrame(
        timestamp_ms=0.0,
        person_confidence=confidence,
        landmarks={
            name: Landmark(x=x, y=y, z=0.0, confidence=confidence)
            for name, (x, y) in positions.items()
        },
        source="test",
    )


def whole_body(top: float = 0.10, bottom: float = 0.92, x: float = 0.5) -> PoseFrame:
    """A pose spanning the frame vertically, as when properly framed."""
    names = list(REQUIRED) + ["nose"]
    step = (bottom - top) / (len(names) - 1)
    return make_pose({n: (x, top + i * step) for i, n in enumerate(names)})


class TestGoodFraming:
    def test_a_fully_visible_body_is_good(self):
        assert assess_framing(whole_body(), REQUIRED).status is Framing.GOOD

    def test_body_fill_is_reported(self):
        hint = assess_framing(whole_body(top=0.10, bottom=0.90), REQUIRED)
        assert hint.body_fill == pytest.approx(0.80)
        assert hint.is_good


class TestCutOff:
    def test_legs_below_the_frame_say_move_back(self):
        # The exact case from recording dev_20260816_100337: hips and below
        # past the bottom edge, still reported with coordinates.
        pose = whole_body(top=0.30, bottom=1.90)
        hint = assess_framing(pose, REQUIRED)
        assert hint.status is Framing.MOVE_BACK
        assert hint.cut_off_below

    def test_head_above_the_frame_says_move_back(self):
        hint = assess_framing(whole_body(top=-0.20, bottom=0.70), REQUIRED)
        assert hint.status is Framing.MOVE_BACK
        assert hint.cut_off_above

    def test_cut_off_at_both_ends_says_move_back(self):
        hint = assess_framing(whole_body(top=-0.10, bottom=1.10), REQUIRED)
        assert hint.status is Framing.MOVE_BACK

    def test_vertical_fit_takes_priority_over_being_off_centre(self):
        # Moving sideways cannot fix a body that does not fit vertically.
        pose = whole_body(top=0.30, bottom=1.90, x=0.005)
        assert assess_framing(pose, REQUIRED).status is Framing.MOVE_BACK


class TestLateral:
    def test_off_the_left_edge_points_across(self):
        hint = assess_framing(whole_body(x=0.005), REQUIRED)
        assert hint.status is Framing.MOVE_TO_CENTRE_RIGHT
        assert hint.outside_sides

    def test_off_the_right_edge_points_across(self):
        hint = assess_framing(whole_body(x=0.995), REQUIRED)
        assert hint.status is Framing.MOVE_TO_CENTRE_LEFT

    def test_no_left_or_right_wording_is_used(self):
        # Frames are mirrored, so "step left" is ambiguous to someone
        # watching themselves. Arrows are not.
        for status in (Framing.MOVE_TO_CENTRE_LEFT, Framing.MOVE_TO_CENTRE_RIGHT):
            from src.ui.framing import DISPLAY_TEXT

            text = DISPLAY_TEXT[status].lower()
            assert "left" not in text and "right" not in text


class TestDistance:
    def test_a_small_body_says_move_closer(self):
        hint = assess_framing(whole_body(top=0.45, bottom=0.65), REQUIRED)
        assert hint.status is Framing.MOVE_CLOSER
        assert hint.body_fill == pytest.approx(0.20)

    def test_the_threshold_is_configurable(self):
        pose = whole_body(top=0.40, bottom=0.70)
        assert assess_framing(pose, REQUIRED, minimum_body_fill=0.2).is_good
        assert not assess_framing(pose, REQUIRED, minimum_body_fill=0.5).is_good


class TestNoPerson:
    def test_an_empty_frame_says_stand_in_view(self):
        empty = PoseFrame(0.0, 0.0, {}, "test")
        assert assess_framing(empty, REQUIRED).status is Framing.NO_PERSON

    def test_a_pose_without_any_required_landmark_says_stand_in_view(self):
        pose = make_pose({"left_wrist": (0.5, 0.5)})
        assert assess_framing(pose, REQUIRED).status is Framing.NO_PERSON

    def test_a_partial_pose_is_still_judged(self):
        # Only some landmarks reported, and those that are sit below frame.
        pose = make_pose({"left_hip": (0.5, 1.4), "nose": (0.5, 0.4)})
        assert assess_framing(pose, REQUIRED).status is Framing.MOVE_BACK


class TestAnklesVisible:
    def test_true_when_both_ankles_are_inside(self):
        assert ankles_visible(make_pose({
            "left_ankle": (0.45, 0.90), "right_ankle": (0.55, 0.90)}))

    def test_false_when_an_ankle_is_below_the_frame(self):
        assert not ankles_visible(make_pose({
            "left_ankle": (0.45, 1.20), "right_ankle": (0.55, 0.90)}))

    def test_false_when_an_ankle_is_missing(self):
        assert not ankles_visible(make_pose({"left_ankle": (0.45, 0.90)}))
