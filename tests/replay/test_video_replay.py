"""Video record and replay tests.

Covers the interchangeability of frame sources: the same loop must be able to
consume a live camera or a recorded file (CLAUDE.md §17). The pose engine is
stubbed for the fast tests so that the frame plumbing is tested independently
of pose-model behaviour; a separate integration test exercises the real
engine.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.camera.base import Frame, FrameSourceError
from src.camera.video_file import VideoFileFrameSource
from src.pose.base import PoseEngine, PoseEngineInfo
from src.pose.models import LEFT_HIP, RIGHT_HIP, Landmark, PoseFrame, with_synthetic_landmarks
from src.pose.quality import PoseQualityAssessor, PoseQualityConfig
from src.recording.video_recorder import VideoRecorder, VideoRecorderError
from src.replay.video_replay import replay_video

FRAME_COUNT = 24
FRAME_WIDTH = 160
FRAME_HEIGHT = 120
FPS = 30.0


class StubPoseEngine(PoseEngine):
    """A deterministic stand-in for a real pose engine.

    Reports a hip position derived from the frame's mean brightness, so a
    replayed video produces a pose sequence that depends on image content
    without depending on a pose model.
    """

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.seen_timestamps: list[float] = []

    def start(self) -> None:
        self.started = True

    def estimate(self, frame: Frame, source: str) -> PoseFrame:
        self.seen_timestamps.append(frame.timestamp_ms)
        brightness = float(frame.image.mean()) / 255.0
        landmarks = with_synthetic_landmarks(
            {
                LEFT_HIP: Landmark(0.45, brightness, 0.0, 0.9),
                RIGHT_HIP: Landmark(0.55, brightness, 0.0, 0.9),
            }
        )
        return PoseFrame(
            timestamp_ms=frame.timestamp_ms,
            person_confidence=0.9,
            landmarks=landmarks,
            source=source,
            frame_index=frame.index,
            image_width=frame.width,
            image_height=frame.height,
        )

    def close(self) -> None:
        self.closed = True

    def info(self) -> PoseEngineInfo:
        return PoseEngineInfo(engine="stub", model_version="stub-1")


@pytest.fixture
def recorded_video(tmp_path) -> Path:
    """Write a short video whose frames get progressively brighter."""
    path = tmp_path / "clip.mp4"
    recorder = VideoRecorder(path, fps=FPS)
    for index in range(FRAME_COUNT):
        value = int(255 * index / FRAME_COUNT)
        image = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), value, dtype=np.uint8)
        recorder.write(Frame(image=image, timestamp_ms=index * 1000.0 / FPS, index=index))
    recorder.stop()
    return path


class TestVideoRecorder:
    def test_writes_a_readable_file(self, recorded_video):
        assert recorded_video.exists()
        assert recorded_video.stat().st_size > 0

    def test_rejects_a_frame_size_change_mid_recording(self, tmp_path):
        recorder = VideoRecorder(tmp_path / "mixed.mp4", fps=FPS)
        recorder.write(
            Frame(np.zeros((120, 160, 3), dtype=np.uint8), timestamp_ms=0.0, index=0)
        )
        with pytest.raises(VideoRecorderError, match="Frame size changed"):
            recorder.write(
                Frame(np.zeros((240, 320, 3), dtype=np.uint8), timestamp_ms=33.0, index=1)
            )
        recorder.stop()

    def test_stop_is_idempotent(self, tmp_path):
        recorder = VideoRecorder(tmp_path / "clip.mp4", fps=FPS)
        recorder.write(
            Frame(np.zeros((120, 160, 3), dtype=np.uint8), timestamp_ms=0.0, index=0)
        )
        recorder.stop()
        recorder.stop()
        assert recorder.is_recording is False


class TestVideoFileFrameSource:
    def test_reads_back_the_frames_that_were_written(self, recorded_video):
        with VideoFileFrameSource(recorded_video) as source:
            frames = list(source.frames())
        assert len(frames) == FRAME_COUNT
        assert frames[0].width == FRAME_WIDTH
        assert frames[0].height == FRAME_HEIGHT

    def test_frame_indices_are_sequential(self, recorded_video):
        with VideoFileFrameSource(recorded_video) as source:
            assert [frame.index for frame in source.frames()] == list(range(FRAME_COUNT))

    def test_timestamps_follow_the_file_frame_rate(self, recorded_video):
        with VideoFileFrameSource(recorded_video) as source:
            timestamps = [frame.timestamp_ms for frame in source.frames()]
        assert timestamps[0] == pytest.approx(0.0)
        assert timestamps[1] == pytest.approx(1000.0 / FPS)
        assert timestamps[-1] == pytest.approx((FRAME_COUNT - 1) * 1000.0 / FPS)

    def test_media_timestamps_are_strictly_increasing(self, recorded_video):
        # OpenCV repeats a media position on some containers; the source must
        # not pass a duplicated or backwards timestamp downstream, because
        # MediaPipe VIDEO mode and all velocity features assume time advances.
        with VideoFileFrameSource(recorded_video, timestamp_source="media") as source:
            timestamps = [frame.timestamp_ms for frame in source.frames()]
        assert len(timestamps) == FRAME_COUNT
        assert all(
            later > earlier for earlier, later in zip(timestamps, timestamps[1:])
        )

    def test_an_unknown_timestamp_source_is_rejected(self, recorded_video):
        with pytest.raises(ValueError, match="timestamp_source"):
            VideoFileFrameSource(recorded_video, timestamp_source="wallclock")

    def test_timestamps_are_identical_on_every_read(self, recorded_video):
        def read() -> list[float]:
            with VideoFileFrameSource(recorded_video) as source:
                return [frame.timestamp_ms for frame in source.frames()]

        assert read() == read()

    def test_describes_itself_for_recording_metadata(self, recorded_video):
        with VideoFileFrameSource(recorded_video) as source:
            info = source.info()
        assert info.kind == "video_file"
        assert info.width == FRAME_WIDTH
        assert info.nominal_fps == pytest.approx(FPS, abs=1.0)

    def test_a_missing_file_raises_a_coded_error(self, tmp_path):
        source = VideoFileFrameSource(tmp_path / "absent.mp4")
        with pytest.raises(FrameSourceError) as exc_info:
            source.start()
        assert exc_info.value.code == "VIDEO_UNAVAILABLE"


class TestVideoReplay:
    def test_produces_one_pose_per_frame(self, recorded_video):
        engine = StubPoseEngine()
        engine.start()
        steps = list(replay_video(recorded_video, engine))
        assert len(steps) == FRAME_COUNT
        assert all(step.pose.frame_index == step.frame.index for step in steps)

    def test_replaying_twice_gives_identical_poses(self, recorded_video):
        engine = StubPoseEngine()
        engine.start()
        first = [step.pose for step in replay_video(recorded_video, engine)]
        second = [step.pose for step in replay_video(recorded_video, engine)]
        assert first == second

    def test_quality_assessment_is_reset_between_replays(self, recorded_video):
        engine = StubPoseEngine()
        engine.start()
        assessor = PoseQualityAssessor(PoseQualityConfig())
        first = [step.quality.to_dict() for step in replay_video(recorded_video, engine, assessor)]
        second = [step.quality.to_dict() for step in replay_video(recorded_video, engine, assessor)]
        assert first == second

    def test_pose_source_records_the_engine_and_file(self, recorded_video):
        engine = StubPoseEngine()
        engine.start()
        step = next(iter(replay_video(recorded_video, engine)))
        assert step.pose.source == f"stub:video:{recorded_video.name}"


@pytest.mark.integration
class TestRealPoseEngineOverVideo:
    def test_video_frames_become_canonical_pose_frames(self, recorded_video):
        # A synthetic clip contains no person, so the useful assertion is that
        # the pipeline produces one well-formed canonical frame per video
        # frame and represents "no person" without crashing or returning None.
        mediapipe = pytest.importorskip("mediapipe")
        assert mediapipe is not None

        from src.config import load_config
        from src.pose.adapters.mediapipe_adapter import MediaPipePoseEngine

        model_path = load_config().pose.resolved_model_path()
        if not model_path.exists():
            pytest.skip(f"pose model not downloaded: {model_path}")

        engine = MediaPipePoseEngine(model_path)
        with engine:
            steps = list(replay_video(recorded_video, engine))

        assert len(steps) == FRAME_COUNT
        assert all(isinstance(step.pose, PoseFrame) for step in steps)
        assert all(step.pose.has_person is False for step in steps)
        assert all(step.inference_ms is not None for step in steps)
