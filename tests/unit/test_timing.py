"""Tests for the timing helpers."""

from __future__ import annotations

import pytest

from src.timing import FpsMeter, RollingMean


class TestFpsMeter:
    def test_reports_nothing_until_two_frames_are_seen(self):
        meter = FpsMeter()
        assert meter.fps is None
        meter.tick()
        assert meter.fps is None

    def test_reports_a_rate_once_frames_arrive(self):
        meter = FpsMeter()
        meter.tick()
        meter.tick()
        assert meter.fps is not None
        assert meter.fps > 0

    def test_reset_clears_history(self):
        meter = FpsMeter()
        meter.tick()
        meter.tick()
        meter.reset()
        assert meter.fps is None

    def test_a_window_smaller_than_two_frames_is_rejected(self):
        with pytest.raises(ValueError):
            FpsMeter(window=1)


class TestRollingMean:
    def test_is_empty_before_any_value(self):
        assert RollingMean().mean is None

    def test_averages_the_values_added(self):
        mean = RollingMean()
        for value in (10.0, 20.0, 30.0):
            mean.add(value)
        assert mean.mean == pytest.approx(20.0)

    def test_ignores_none(self):
        mean = RollingMean()
        mean.add(10.0)
        mean.add(None)
        assert mean.mean == pytest.approx(10.0)

    def test_drops_values_outside_the_window(self):
        mean = RollingMean(window=2)
        for value in (100.0, 10.0, 20.0):
            mean.add(value)
        assert mean.mean == pytest.approx(15.0)
