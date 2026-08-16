"""Tests for temporal filtering."""

from __future__ import annotations

import math

import pytest

from src.movement.filtering import (
    ExponentialMovingAverageFilter,
    FilterSettings,
    MovingMedianFilter,
    OneEuroFilter,
    PassThroughFilter,
    PoseFilter,
    make_filter,
)
from src.pose.models import Landmark, PoseFrame

FPS = 30.0
STEP_MS = 1000.0 / FPS


def noisy_hold(count: int, value: float = 0.5, noise: float = 0.01) -> list[float]:
    """A held posture with alternating jitter, the case filtering exists for."""
    return [value + (noise if i % 2 else -noise) for i in range(count)]


def make_pose(y: float, timestamp_ms: float, names=("hip_centre",)) -> PoseFrame:
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=0.9,
        landmarks={n: Landmark(0.5, y, 0.0, 0.9) for n in names},
        source="test",
        image_width=1280,
        image_height=720,
    )


class TestPassThrough:
    def test_returns_input_unchanged(self):
        f = PassThroughFilter()
        assert [f.update(v, i * STEP_MS) for i, v in enumerate([0.1, 0.9, 0.2])] == [
            0.1,
            0.9,
            0.2,
        ]


class TestExponentialMovingAverage:
    def test_first_sample_passes_through(self):
        assert ExponentialMovingAverageFilter(80).update(0.42, 0.0) == pytest.approx(0.42)

    def test_jitter_is_reduced(self):
        raw = noisy_hold(60)
        f = ExponentialMovingAverageFilter(80)
        out = [f.update(v, i * STEP_MS) for i, v in enumerate(raw)]
        tail = out[30:]
        assert max(tail) - min(tail) < (max(raw) - min(raw)) / 3

    def test_it_converges_on_a_step(self):
        f = ExponentialMovingAverageFilter(80)
        f.update(0.0, 0.0)
        for i in range(1, 60):
            value = f.update(1.0, i * STEP_MS)
        assert value == pytest.approx(1.0, abs=0.01)

    def test_smoothing_is_time_based_not_frame_based(self):
        # The same elapsed time must give the same result whether it arrived
        # as few slow frames or many fast ones. Capture rate drifts between
        # 27.9 and 29.9 fps in this project's recordings.
        slow = ExponentialMovingAverageFilter(100)
        fast = ExponentialMovingAverageFilter(100)
        slow.update(0.0, 0.0)
        fast.update(0.0, 0.0)
        for i in range(1, 11):
            slow_value = slow.update(1.0, i * 20.0)
        for i in range(1, 41):
            fast_value = fast.update(1.0, i * 5.0)
        assert slow_value == pytest.approx(fast_value, abs=0.01)

    def test_a_larger_time_constant_smooths_more(self):
        raw = noisy_hold(60)
        light = ExponentialMovingAverageFilter(20)
        heavy = ExponentialMovingAverageFilter(200)
        l = [light.update(v, i * STEP_MS) for i, v in enumerate(raw)][30:]
        h = [heavy.update(v, i * STEP_MS) for i, v in enumerate(raw)][30:]
        assert (max(h) - min(h)) < (max(l) - min(l))

    def test_reset_forgets_history(self):
        f = ExponentialMovingAverageFilter(80)
        f.update(0.0, 0.0)
        f.reset()
        assert f.update(1.0, STEP_MS) == pytest.approx(1.0)

    def test_repeated_timestamps_do_not_divide_by_zero(self):
        f = ExponentialMovingAverageFilter(80)
        f.update(0.5, 100.0)
        assert f.update(0.9, 100.0) == pytest.approx(0.5)

    def test_a_non_positive_time_constant_is_rejected(self):
        with pytest.raises(ValueError):
            ExponentialMovingAverageFilter(0)


class TestMovingMedian:
    def test_a_single_outlier_is_rejected_entirely(self):
        f = MovingMedianFilter(5)
        for value in [0.5, 0.5, 0.5]:
            f.update(value, 0.0)
        assert f.update(9.9, 0.0) == pytest.approx(0.5)

    def test_it_tracks_a_sustained_change(self):
        f = MovingMedianFilter(3)
        for value in [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]:
            out = f.update(value, 0.0)
        assert out == pytest.approx(1.0)

    def test_an_invalid_window_is_rejected(self):
        with pytest.raises(ValueError):
            MovingMedianFilter(0)


class TestOneEuro:
    def test_first_sample_passes_through(self):
        assert OneEuroFilter().update(0.3, 0.0) == pytest.approx(0.3)

    def test_it_smooths_a_held_posture(self):
        raw = noisy_hold(60)
        f = OneEuroFilter(min_cutoff_hz=0.5)
        out = [f.update(v, i * STEP_MS) for i, v in enumerate(raw)][30:]
        assert max(out) - min(out) < (max(raw) - min(raw))

    def test_it_lags_less_than_a_fixed_filter_during_fast_movement(self):
        # The property that justifies its extra parameters.
        ramp = [i / 30.0 for i in range(30)]
        euro = OneEuroFilter(min_cutoff_hz=0.5, beta=2.0)
        ema = ExponentialMovingAverageFilter(200)
        euro_out = [euro.update(v, i * STEP_MS) for i, v in enumerate(ramp)]
        ema_out = [ema.update(v, i * STEP_MS) for i, v in enumerate(ramp)]
        assert abs(euro_out[-1] - ramp[-1]) < abs(ema_out[-1] - ramp[-1])


class TestMakeFilter:
    def test_builds_each_known_filter(self):
        assert isinstance(make_filter("none"), PassThroughFilter)
        assert isinstance(
            make_filter("exponential_moving_average", time_constant_ms=50),
            ExponentialMovingAverageFilter,
        )
        assert isinstance(make_filter("moving_median", window=3), MovingMedianFilter)

    def test_an_unknown_filter_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown filter"):
            make_filter("kalman")

    def test_settings_build_the_configured_filter(self):
        assert isinstance(FilterSettings(kind="one_euro").build(), OneEuroFilter)
        assert isinstance(FilterSettings(kind="none").build(), PassThroughFilter)

    def test_settings_reject_an_unknown_filter(self):
        with pytest.raises(ValueError, match="Unknown filter"):
            FilterSettings(kind="nonsense").build()


class TestPoseFilter:
    def test_it_smooths_landmark_positions(self):
        pf = PoseFilter(FilterSettings(time_constant_ms=100))
        out = [
            pf.apply(make_pose(y, i * STEP_MS)).landmarks["hip_centre"].y
            for i, y in enumerate(noisy_hold(60))
        ][30:]
        assert max(out) - min(out) < 0.01

    def test_confidence_is_left_unsmoothed(self):
        # Confidence is evidence about this frame; blurring it would slow the
        # pose-quality layer's reaction to tracking loss.
        pf = PoseFilter()
        pose = PoseFrame(
            0.0, 0.9, {"hip_centre": Landmark(0.5, 0.5, 0.0, 0.2)}, "test"
        )
        assert pf.apply(pose).landmarks["hip_centre"].confidence == pytest.approx(0.2)

    def test_metadata_is_preserved(self):
        pf = PoseFilter()
        out = pf.apply(make_pose(0.5, 33.0))
        assert out.timestamp_ms == pytest.approx(33.0)
        assert out.image_width == 1280
        assert out.source == "test"

    def test_a_frame_without_a_person_passes_through(self):
        pf = PoseFilter()
        empty = PoseFrame(10.0, 0.0, {}, "test")
        assert pf.apply(empty) is empty

    def test_state_is_discarded_across_a_long_gap(self):
        # Averaging across a tracking loss would fabricate movement.
        pf = PoseFilter(FilterSettings(time_constant_ms=200, max_gap_ms=250))
        for i in range(30):
            pf.apply(make_pose(0.2, i * STEP_MS))
        resumed = pf.apply(make_pose(0.8, 30 * STEP_MS + 2000.0))
        assert resumed.landmarks["hip_centre"].y == pytest.approx(0.8)

    def test_a_short_gap_keeps_smoothing(self):
        pf = PoseFilter(FilterSettings(time_constant_ms=200, max_gap_ms=250))
        for i in range(30):
            pf.apply(make_pose(0.2, i * STEP_MS))
        resumed = pf.apply(make_pose(0.8, 30 * STEP_MS + 60.0))
        assert resumed.landmarks["hip_centre"].y < 0.5

    def test_reset_makes_replay_reproducible(self):
        pf = PoseFilter(FilterSettings(time_constant_ms=100))
        frames = [make_pose(y, i * STEP_MS) for i, y in enumerate(noisy_hold(40))]
        first = [pf.apply(f).landmarks["hip_centre"].y for f in frames]
        pf.reset()
        second = [pf.apply(f).landmarks["hip_centre"].y for f in frames]
        assert first == second

    def test_missing_depth_stays_missing(self):
        pf = PoseFilter()
        pose = PoseFrame(0.0, 0.9, {"nose": Landmark(0.5, 0.5, None, 0.9)}, "test")
        assert pf.apply(pose).landmarks["nose"].z is None

    def test_bypass_leaves_data_untouched(self):
        pf = PoseFilter(FilterSettings(kind="none"))
        for i, y in enumerate(noisy_hold(10)):
            out = pf.apply(make_pose(y, i * STEP_MS))
        assert out.landmarks["hip_centre"].y == pytest.approx(noisy_hold(10)[-1])
