"""Replay serialisation tests.

The project's central testability claim is that a recorded canonical pose
stream replays to exactly the same values, so downstream algorithm changes can
be compared on identical input (CLAUDE.md §17, ADR-008). These tests hold that
claim in place.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.pose.models import CANONICAL_LANDMARKS, Landmark, PoseFrame
from src.pose.quality import PoseQualityAssessor, PoseQualityConfig, PoseQualityStatus
from src.recording.pose_recorder import PoseStreamMetadata, PoseStreamWriter
from src.replay.pose_replay import (
    PoseStreamError,
    PoseStreamSource,
    read_pose_stream,
)


def make_pose(index: int) -> PoseFrame:
    """A moving pose with every canonical landmark populated."""
    offset = index / 100.0
    return PoseFrame(
        timestamp_ms=index * 33.3333,
        person_confidence=0.9 - index / 1000.0,
        landmarks={
            name: Landmark(
                x=0.4 + offset,
                y=0.5 - offset,
                z=None if name == "nose" else -0.1 - offset,
                confidence=0.95 - index / 500.0,
            )
            for name in CANONICAL_LANDMARKS
        },
        source="mediapipe:webcam:0",
        frame_index=index,
        image_width=1280,
        image_height=720,
    )


def make_metadata() -> PoseStreamMetadata:
    return PoseStreamMetadata.create(
        recording_id="dev_20260815_120000",
        pose_engine="mediapipe_pose_landmarker",
        pose_model_version="pose_landmarker_lite.task",
        pose_engine_detail="detection=0.5",
        camera_view="frontal_oblique",
        width=1280,
        height=720,
        nominal_fps=30.0,
        source={"kind": "webcam", "description": "webcam:0"},
        notes="synthetic fixture",
    )


@pytest.fixture
def recorded_stream(tmp_path):
    """Write a short pose stream with quality verdicts and return its path."""
    path = tmp_path / "recording.jsonl"
    assessor = PoseQualityAssessor(PoseQualityConfig())
    with PoseStreamWriter(path, make_metadata()) as writer:
        for index in range(20):
            pose = make_pose(index)
            writer.write(pose, assessor.assess(pose))
    return path


class TestRoundTrip:
    def test_every_pose_frame_survives_unchanged(self, recorded_stream):
        _, records = read_pose_stream(recorded_stream)
        assert len(records) == 20
        for index, record in enumerate(records):
            assert record.pose == make_pose(index)

    def test_metadata_survives_unchanged(self, recorded_stream):
        metadata, _ = read_pose_stream(recorded_stream)
        original = make_metadata()
        assert metadata.recording_id == original.recording_id
        assert metadata.pose_engine == original.pose_engine
        assert metadata.pose_model_version == original.pose_model_version
        assert metadata.camera_view == "frontal_oblique"
        assert metadata.nominal_resolution == "1280x720"
        assert metadata.nominal_fps == pytest.approx(30.0)
        assert metadata.application_version == original.application_version
        assert metadata.source["description"] == "webcam:0"

    def test_recorded_quality_is_preserved_alongside_the_pose(self, recorded_stream):
        _, records = read_pose_stream(recorded_stream)
        assert records[0].recorded_quality is not None
        assert records[0].recorded_quality["status"] in {
            status.value for status in PoseQualityStatus
        }

    def test_missing_depth_stays_missing(self, recorded_stream):
        _, records = read_pose_stream(recorded_stream)
        assert records[0].pose.landmarks["nose"].z is None
        assert records[0].pose.landmarks["left_hip"].z is not None

    def test_frame_order_and_timestamps_are_preserved(self, recorded_stream):
        _, records = read_pose_stream(recorded_stream)
        timestamps = [record.pose.timestamp_ms for record in records]
        assert timestamps == sorted(timestamps)
        assert timestamps[1] == pytest.approx(33.3333)


class TestReplayDeterminism:
    def test_two_replays_produce_identical_poses(self, recorded_stream):
        _, first = read_pose_stream(recorded_stream)
        _, second = read_pose_stream(recorded_stream)
        assert [record.pose for record in first] == [record.pose for record in second]

    def test_two_replays_produce_identical_quality_verdicts(self, recorded_stream):
        def replay() -> list[dict]:
            assessor = PoseQualityAssessor(PoseQualityConfig())
            with PoseStreamSource(recorded_stream) as source:
                return [assessor.assess(pose).to_dict() for pose in source.poses()]

        assert replay() == replay()

    def test_a_fresh_assessor_reproduces_the_recorded_verdicts(self, recorded_stream):
        # Re-running the current quality logic over the recording must agree
        # with what was stored at record time. When it stops agreeing, the
        # quality logic has changed and the change should be deliberate.
        assessor = PoseQualityAssessor(PoseQualityConfig())
        _, records = read_pose_stream(recorded_stream)
        for record in records:
            assert assessor.assess(record.pose).to_dict() == record.recorded_quality


class TestStreamingInterface:
    def test_source_iterates_lazily_to_the_end(self, recorded_stream):
        with PoseStreamSource(recorded_stream) as source:
            assert source.metadata.recording_id == "dev_20260815_120000"
            count = sum(1 for _ in source.poses())
        assert count == 20

    def test_next_pose_returns_none_at_the_end(self, recorded_stream):
        with PoseStreamSource(recorded_stream) as source:
            for _ in range(20):
                assert source.next_pose() is not None
            assert source.next_pose() is None

    def test_metadata_before_start_is_an_error(self, recorded_stream):
        source = PoseStreamSource(recorded_stream)
        with pytest.raises(PoseStreamError):
            _ = source.metadata


class TestMalformedStreams:
    def test_missing_file_is_reported_clearly(self, tmp_path):
        with pytest.raises(PoseStreamError, match="not found"):
            read_pose_stream(tmp_path / "absent.jsonl")

    def test_empty_file_is_reported_clearly(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        with pytest.raises(PoseStreamError, match="empty"):
            read_pose_stream(path)

    def test_a_stream_without_metadata_is_rejected(self, tmp_path):
        path = tmp_path / "headless.jsonl"
        path.write_text(
            json.dumps({"record": "frame", "pose": make_pose(0).to_dict()}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(PoseStreamError, match="metadata"):
            read_pose_stream(path)

    def test_a_truncated_final_line_is_reported(self, tmp_path, recorded_stream):
        # A recording interrupted by a crash should fail loudly at the broken
        # line rather than silently returning a short stream.
        truncated = tmp_path / "truncated.jsonl"
        text = recorded_stream.read_text(encoding="utf-8")
        truncated.write_text(text[: len(text) - 40], encoding="utf-8")
        with pytest.raises(PoseStreamError, match="Malformed"):
            read_pose_stream(truncated)


class TestArchitecturalBoundary:
    def test_pose_replay_does_not_import_a_vision_library(self):
        # Pose-stream replay must work with no pose engine installed at all.
        # Asserted in a subprocess so that other tests' imports cannot mask a
        # dependency creeping in.
        script = (
            "import sys;"
            "import src.replay.pose_replay;"
            "import src.pose.models;"
            "import src.pose.quality;"
            "leaked = [name for name in ('mediapipe', 'cv2')"
            " if name in sys.modules];"
            "print(','.join(leaked))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        assert result.stdout.strip() == "", (
            "pose replay must not depend on a vision library; "
            f"imported: {result.stdout.strip()}"
        )
