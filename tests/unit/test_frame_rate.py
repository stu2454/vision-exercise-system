"""Tests for frame-rate measurement.

These exist because of a real defect. A webcam advertised 15 fps through
`CAP_PROP_FPS` while delivering 29.4 fps. That claimed figure was written into
recording metadata and used as the frame rate of recorded video, and — because
replayed video derives its timestamps from the file's frame rate (ADR-011) —
it would have put a silent 2x error into every velocity feature computed from
a replay.

The rule these tests hold in place: a measured rate always beats a claimed one.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.camera.base import (
    MINIMUM_RATE_SAMPLES,
    Frame,
    FrameRateTracker,
    FrameSource,
    FrameSourceInfo,
)


class StubSource(FrameSource):
    """A frame source delivering frames at a chosen true rate."""

    def __init__(self, true_fps: float, claimed_fps: float, count: int = 60) -> None:
        self.true_fps = true_fps
        self.claimed_fps = claimed_fps
        self.count = count
        self._index = 0

    def start(self) -> None:
        self._index = 0
        self.reset_frame_rate()

    def next_frame(self):
        if self._index >= self.count:
            return None
        timestamp_ms = self._index * 1000.0 / self.true_fps
        frame = Frame(
            image=np.zeros((4, 4, 3), dtype=np.uint8),
            timestamp_ms=timestamp_ms,
            index=self._index,
        )
        self._index += 1
        self.observe_frame_rate(timestamp_ms)
        return frame

    def stop(self) -> None:
        pass

    def info(self) -> FrameSourceInfo:
        return FrameSourceInfo(
            kind="stub",
            description="stub",
            width=4,
            height=4,
            nominal_fps=self.claimed_fps,
            measured_fps=self.measured_fps,
        )


class TestFrameRateTracker:
    def test_reports_nothing_until_enough_samples(self):
        tracker = FrameRateTracker()
        for index in range(MINIMUM_RATE_SAMPLES - 1):
            tracker.observe(index * 33.3333)
        assert tracker.fps is None

    def test_measures_a_known_rate(self):
        tracker = FrameRateTracker()
        for index in range(60):
            tracker.observe(index * 1000.0 / 30.0)
        assert tracker.fps == pytest.approx(30.0, abs=0.01)

    def test_measures_an_irregular_rate_as_its_average(self):
        tracker = FrameRateTracker()
        timestamp = 0.0
        for index in range(60):
            timestamp += 30.0 if index % 2 else 40.0
            tracker.observe(timestamp)
        assert tracker.fps == pytest.approx(1000.0 / 35.0, abs=0.5)

    def test_reset_clears_measurement(self):
        tracker = FrameRateTracker()
        for index in range(30):
            tracker.observe(index * 33.3333)
        tracker.reset()
        assert tracker.fps is None

    def test_identical_timestamps_do_not_divide_by_zero(self):
        tracker = FrameRateTracker()
        for _ in range(30):
            tracker.observe(100.0)
        assert tracker.fps is None

    def test_only_recent_frames_count(self):
        # A rate that changes mid-session should converge on the new rate,
        # not average across the whole session.
        tracker = FrameRateTracker(window=20)
        timestamp = 0.0
        for _ in range(40):
            timestamp += 100.0
            tracker.observe(timestamp)
        for _ in range(40):
            timestamp += 20.0
            tracker.observe(timestamp)
        assert tracker.fps == pytest.approx(50.0, abs=1.0)


class TestEffectiveFps:
    def test_measured_rate_wins_over_a_wrong_claim(self):
        # The exact defect: claimed 15, actually 29.4.
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 15.0, measured_fps=29.4)
        assert info.effective_fps == pytest.approx(29.4)

    def test_falls_back_to_the_claim_before_measurement_exists(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 30.0, measured_fps=None)
        assert info.effective_fps == pytest.approx(30.0)

    def test_a_nonsense_measurement_is_ignored(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 30.0, measured_fps=0.0)
        assert info.effective_fps == pytest.approx(30.0)

    def test_disagreement_is_detectable(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 15.0, measured_fps=29.4)
        assert info.rate_disagreement == pytest.approx(1.96, abs=0.01)

    def test_agreement_is_close_to_one(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 30.0, measured_fps=29.9)
        assert info.rate_disagreement == pytest.approx(1.0, abs=0.01)

    def test_disagreement_is_unknown_without_a_measurement(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 30.0)
        assert info.rate_disagreement is None

    def test_the_effective_rate_is_recorded_in_metadata(self):
        info = FrameSourceInfo("webcam", "webcam:0", 1280, 720, 15.0, measured_fps=29.4)
        data = info.to_dict()
        assert data["nominal_fps"] == pytest.approx(15.0)
        assert data["measured_fps"] == pytest.approx(29.4)
        assert data["effective_fps"] == pytest.approx(29.4)


class TestSourceMeasuresItself:
    def test_a_source_measures_its_true_rate_not_its_claim(self):
        source = StubSource(true_fps=29.4, claimed_fps=15.0)
        with source:
            for _ in range(40):
                source.next_frame()
            info = source.info()
        assert info.nominal_fps == pytest.approx(15.0)
        assert info.measured_fps == pytest.approx(29.4, abs=0.1)
        assert info.effective_fps == pytest.approx(29.4, abs=0.1)

    def test_no_measurement_is_available_before_frames_flow(self):
        # This is why a recording must not open before frames have arrived.
        source = StubSource(true_fps=29.4, claimed_fps=15.0)
        source.start()
        assert source.info().measured_fps is None
        assert source.info().effective_fps == pytest.approx(15.0)

    def test_restarting_forgets_the_previous_measurement(self):
        source = StubSource(true_fps=29.4, claimed_fps=15.0)
        source.start()
        for _ in range(40):
            source.next_frame()
        source.start()
        assert source.measured_fps is None
