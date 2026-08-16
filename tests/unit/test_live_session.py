"""Tests for the shared pipeline composition, and for the loop that uses it.

`LiveSession` exists so the desktop application and the browser bridge run one
assembly of filtering, features, quality and the exercise engine rather than
two that could drift.

The frame-loop test at the end exists because it was missing: a refactor left
`run_frame_loop` referring to an undefined name and the whole suite still
passed, because nothing exercised the live path. It needs no camera — a stub
frame source and a stub pose engine are enough.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.app import run_frame_loop
from src.camera.base import Frame, FrameSource, FrameSourceInfo
from src.config import load_config
from src.exercises.sit_to_stand import SitToStandEngine, StsCalibration, StsConfig
from src.live_session import LiveSession
from src.pose.base import PoseEngine, PoseEngineInfo
from src.pose.models import Landmark, PoseFrame, with_synthetic_landmarks

STEP_MS = 1000.0 / 30.0


def upright_pose(timestamp_ms: float, hip_y: float = 0.55) -> PoseFrame:
    landmarks = {
        "left_shoulder": Landmark(0.45, hip_y - 0.25, 0.0, 0.95),
        "right_shoulder": Landmark(0.55, hip_y - 0.25, 0.0, 0.95),
        "left_hip": Landmark(0.47, hip_y, 0.0, 0.95),
        "right_hip": Landmark(0.53, hip_y, 0.0, 0.95),
        "left_knee": Landmark(0.47, hip_y + 0.18, 0.0, 0.95),
        "right_knee": Landmark(0.53, hip_y + 0.18, 0.0, 0.95),
        "left_ankle": Landmark(0.47, hip_y + 0.36, 0.0, 0.95),
        "right_ankle": Landmark(0.53, hip_y + 0.36, 0.0, 0.95),
    }
    return PoseFrame(
        timestamp_ms=timestamp_ms,
        person_confidence=0.95,
        landmarks=with_synthetic_landmarks(landmarks),
        source="test",
        image_width=1280,
        image_height=720,
    )


class TestWithoutAnEngine:
    def test_quality_and_features_are_still_produced(self):
        # The plain camera sandbox needs these before any exercise starts.
        session = LiveSession(load_config())
        update = session.update(upright_pose(0.0))
        assert update.quality is not None
        assert update.features.value("hip_height") is not None
        assert update.events == []

    def test_it_reports_that_it_is_not_scoring(self):
        session = LiveSession(load_config())
        assert session.scoring is False
        assert session.repetitions is None
        assert session.result() is None

    def test_status_is_safe_to_serialise(self):
        import json

        json.dumps(LiveSession(load_config()).status())


class TestWithAnEngine:
    @staticmethod
    def session() -> LiveSession:
        engine = SitToStandEngine(StsConfig(target_repetitions=5))
        engine.initialise(
            StsCalibration(seated_hip_height=0.40, standing_hip_height=0.55,
                           source="explicit")
        )
        return LiveSession(load_config(), engine=engine)

    def test_it_reports_scoring_state(self):
        session = self.session()
        session.update(upright_pose(0.0))
        status = session.status()
        assert status["target"] == 5
        assert status["repetitions"] == 0
        assert status["state"] is not None

    def test_scoring_can_be_suppressed_for_a_frame(self):
        # The desktop loop computes quality and features for the overlay
        # before the start gesture, without anything being counted.
        session = self.session()
        for index in range(20):
            update = session.update(upright_pose(index * STEP_MS), score=False)
            assert update.events == []
        assert session.repetitions == 0

    def test_reset_clears_every_stateful_part(self):
        # Resetting the engine but not the filter would carry the tail of one
        # attempt into the next, and the result would stop being reproducible.
        session = self.session()
        for index in range(30):
            session.update(upright_pose(index * STEP_MS, hip_y=0.45))
        session.reset(
            StsCalibration(seated_hip_height=0.40, standing_hip_height=0.55,
                           source="explicit")
        )
        first = session.update(upright_pose(0.0, hip_y=0.60))
        fresh = self.session().update(upright_pose(0.0, hip_y=0.60))
        assert first.features.value("hip_height") == pytest.approx(
            fresh.features.value("hip_height")
        )


class StubSource(FrameSource):
    """A frame source that needs no camera."""

    def __init__(self, frames: int = 30) -> None:
        self.total = frames
        self.index = 0

    def start(self) -> None:
        self.index = 0
        self.reset_frame_rate()

    def next_frame(self):
        if self.index >= self.total:
            return None
        timestamp_ms = self.index * STEP_MS
        frame = Frame(
            image=np.zeros((720, 1280, 3), dtype=np.uint8),
            timestamp_ms=timestamp_ms,
            index=self.index,
        )
        self.index += 1
        self.observe_frame_rate(timestamp_ms)
        return frame

    def stop(self) -> None:
        pass

    def info(self) -> FrameSourceInfo:
        return FrameSourceInfo(
            kind="stub", description="stub", width=1280, height=720,
            nominal_fps=30.0, measured_fps=self.measured_fps,
        )


class StubPoseEngine(PoseEngine):
    """Returns a seated pose for every frame, needing no model."""

    def start(self) -> None:
        pass

    def estimate(self, frame: Frame, source: str) -> PoseFrame:
        pose = upright_pose(frame.timestamp_ms)
        return PoseFrame(
            timestamp_ms=pose.timestamp_ms,
            person_confidence=pose.person_confidence,
            landmarks=pose.landmarks,
            source=source,
            frame_index=frame.index,
            image_width=frame.width,
            image_height=frame.height,
        )

    def close(self) -> None:
        pass

    def info(self) -> PoseEngineInfo:
        return PoseEngineInfo(engine="stub", model_version="stub-1")


class TestFrameLoop:
    """The live loop, without a camera or a pose model.

    This is the test that was missing. A refactor left `run_frame_loop`
    referring to an undefined name, every one of 367 tests passed, and the
    fault only appeared when the command was run by hand.
    """

    def test_the_loop_runs_without_an_exercise(self):
        source = StubSource(30)
        engine = StubPoseEngine()
        with source, engine:
            processed = run_frame_loop(
                source, engine, load_config(), mode="TEST", headless=True
            )
        assert processed == 30

    def test_the_loop_runs_with_an_exercise(self):
        source = StubSource(30)
        pose_engine = StubPoseEngine()
        exercise = SitToStandEngine(StsConfig())
        exercise.initialise()
        with source, pose_engine:
            processed = run_frame_loop(
                source, pose_engine, load_config(), mode="TEST",
                headless=True, exercise=exercise,
            )
        assert processed == 30
        assert exercise.valid_repetitions == 0, "a static pose is not a repetition"

    def test_the_loop_stops_at_the_frame_limit(self):
        source = StubSource(200)
        engine = StubPoseEngine()
        with source, engine:
            processed = run_frame_loop(
                source, engine, load_config(), mode="TEST",
                headless=True, max_frames=25,
            )
        assert processed == 25
