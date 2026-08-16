"""Pose Sandbox — the movement-analysis workbench (Builds 0-3).

This module is the composition root: it is the one place permitted to know
about cameras, pose engines, recording, replay and the developer overlay at
the same time. Every layer below it stays unaware of the others.

Usage:

    python -m src.app live                     live webcam sandbox
    python -m src.app replay-video FILE        re-run pose inference on video
    python -m src.app replay-pose FILE         replay a canonical pose stream
    python -m src.app check                    verify the local setup

Interactive keys:

    r   start / stop recording
    s   toggle the skeleton overlay
    q   quit (Esc also works)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from src.camera.base import FrameSource, FrameSourceError, FrameSourceInfo
from src.camera.video_file import VideoFileFrameSource
from src.camera.webcam import WebcamFrameSource
from src.config import AppConfig, ConfigurationError, load_config, load_sts_config
from src.exercises.base import ExerciseResult
from src.exercises.events import Event, EventType
from src.exercises.sit_to_stand import SitToStandEngine
from src.movement.features import (
    HIP_HEIGHT,
    HIP_VERTICAL_VELOCITY,
    MEAN_KNEE_ANGLE,
    STANCE_WIDTH_NORMALISED,
    TRUNK_ANGLE,
    FeatureExtractor,
)
from src.movement.filtering import PoseFilter
from src.pose.adapters.mediapipe_adapter import MediaPipePoseEngine
from src.pose.base import PoseEngine, PoseEngineError
from src.pose.quality import PoseQualityAssessor
from src.recording.pose_recorder import (
    PoseStreamMetadata,
    PoseStreamWriter,
    new_recording_id,
)
from src.recording.video_recorder import VideoRecorder, VideoRecorderError
from src.replay.pose_replay import PoseStreamError, PoseStreamSource
from src.timing import FpsMeter, RollingMean
from src.ui.developer import DeveloperHud, draw_developer_overlay
from src.ui.framing import assess_framing
from src.version import APPLICATION_VERSION

LOGGER = logging.getLogger("vision_exercise")

WINDOW_NAME = "Vision Exercise System — Pose Sandbox"

_LOGGED_EVENTS = (
    EventType.CALIBRATED,
    EventType.REP_COMPLETED,
    EventType.PARTIAL_REP,
    EventType.INVALID_REP,
    EventType.QUALITY_FLAG,
    EventType.EXERCISE_COMPLETED,
)
"""Events worth surfacing to a developer watching a run."""

KEY_QUIT = {ord("q"), 27}
KEY_RECORD = ord("r")
KEY_SKELETON = ord("s")


@dataclass
class RecordingSession:
    """A pose stream, and optionally a video, being written together.

    Both files share a recording id so the pair can be reunited later.
    """

    recording_id: str
    pose_writer: PoseStreamWriter
    video_recorder: Optional[VideoRecorder] = None

    def stop(self) -> None:
        self.pose_writer.stop()
        if self.video_recorder is not None:
            self.video_recorder.stop()

    def describe(self) -> str:
        parts = [f"pose {self.pose_writer.frame_count} frames"]
        if self.video_recorder is not None:
            parts.append(f"video {self.video_recorder.frame_count} frames")
        return f"saved {self.recording_id}: {', '.join(parts)}"


def build_frame_source(
    config: AppConfig, device_index: Optional[int] = None
) -> FrameSource:
    """Create the configured live camera source.

    The only place a camera implementation is chosen. Everything downstream
    receives a FrameSource and cannot tell a USB webcam from a Pi Camera
    Module, which is what lets the same code run on both.
    """
    if config.camera.source == "picamera":
        # Imported here rather than at module scope: the module itself is
        # import-safe anywhere, but keeping the import local makes it obvious
        # that this path is only taken when configured.
        from src.camera.picamera import PiCameraFrameSource

        return PiCameraFrameSource(
            width=config.camera.width,
            height=config.camera.height,
            fps=config.camera.fps,
            mirror=config.camera.mirror,
            picamera_format=config.camera.picamera_format,
        )
    return WebcamFrameSource(
        device_index=(
            device_index if device_index is not None else config.camera.device_index
        ),
        width=config.camera.width,
        height=config.camera.height,
        fps=config.camera.fps,
        mirror=config.camera.mirror,
    )


def build_pose_engine(config: AppConfig) -> PoseEngine:
    """Create the configured pose engine.

    The only place an engine is chosen. Adding MoveNet later means adding a
    branch here and an adapter module, and changing nothing else.
    """
    if config.pose.engine != "mediapipe":
        raise ConfigurationError(
            f"Unknown pose engine '{config.pose.engine}'. Supported: mediapipe."
        )
    return MediaPipePoseEngine(
        model_path=config.pose.resolved_model_path(),
        min_detection_confidence=config.pose.min_detection_confidence,
        min_presence_confidence=config.pose.min_presence_confidence,
        min_tracking_confidence=config.pose.min_tracking_confidence,
    )


def start_recording(
    config: AppConfig,
    engine: PoseEngine,
    source_info: FrameSourceInfo,
    record_video: bool,
) -> RecordingSession:
    """Open a new recording, always for pose and optionally for video."""
    recording_id = new_recording_id()
    directory = config.recording.resolved_directory()
    engine_info = engine.info()

    # Always the measured rate where one exists. A webcam observed during
    # development advertised 15 fps while delivering 29.4, which would have
    # written video at half speed and put a 2x error into every velocity
    # feature derived from replaying it.
    fps = source_info.effective_fps or config.camera.fps
    disagreement = source_info.rate_disagreement
    if disagreement is not None and not 0.9 <= disagreement <= 1.1:
        LOGGER.warning(
            "camera_frame_rate_misreported claimed=%.1f measured=%.1f "
            "-- using measured",
            source_info.nominal_fps,
            source_info.measured_fps,
        )

    metadata = PoseStreamMetadata.create(
        recording_id=recording_id,
        pose_engine=engine_info.engine,
        pose_model_version=engine_info.model_version,
        pose_engine_detail=engine_info.detail,
        camera_view=config.camera.view,
        width=source_info.width,
        height=source_info.height,
        nominal_fps=source_info.nominal_fps,
        measured_fps=source_info.measured_fps,
        source=source_info.to_dict(),
    )
    pose_writer = PoseStreamWriter(directory / f"{recording_id}.jsonl", metadata)
    pose_writer.start()

    video_recorder = None
    if record_video:
        video_recorder = VideoRecorder(
            directory / f"{recording_id}.mp4",
            fps=fps,
            fourcc=config.recording.video_fourcc,
        )

    LOGGER.info(
        "recording_started id=%s video=%s fps=%.1f view=%s directory=%s",
        recording_id,
        record_video,
        fps,
        config.camera.view,
        directory,
    )
    if config.camera.view == "unspecified":
        # Camera placement is an experimental variable (Document 03 §10). A
        # recording that does not say where the camera was cannot take part
        # in a view comparison later.
        LOGGER.warning(
            "camera_view_unspecified -- set camera.view in configuration "
            "or pass --camera-view so this recording can be compared later"
        )
    return RecordingSession(recording_id, pose_writer, video_recorder)


def run_frame_loop(
    source: FrameSource,
    engine: PoseEngine,
    config: AppConfig,
    mode: str,
    headless: bool = False,
    max_frames: Optional[int] = None,
    record_video: bool = False,
    record_from_start: bool = False,
    setup_mode: bool = False,
    exercise: Optional[SitToStandEngine] = None,
) -> int:
    """Run the sandbox loop over any frame source.

    Shared by live capture and video replay: the only difference between them
    is which FrameSource is passed in, which is the point of the abstraction.

    Args:
        source: A started frame source.
        engine: A started pose engine.
        config: Application configuration.
        mode: Label shown on the developer overlay.
        headless: Process frames without opening a window. Used for smoke
            tests and for machines without a display.
        max_frames: Stop after this many frames, if given.
        record_video: Include video in any recording started.
        record_from_start: Begin recording as soon as the frame rate has been
            measured, rather than waiting for a keypress.

    Returns:
        The number of frames processed.
    """
    assessor = PoseQualityAssessor(config.pose_quality)
    pose_filter = PoseFilter(config.filtering)
    extractor = FeatureExtractor(config.features)
    fps_meter = FpsMeter()
    inference_mean = RollingMean()
    source_label = source.info().description
    hud = DeveloperHud(mode=mode, source_label=source_label, setup_mode=setup_mode)
    recording: Optional[RecordingSession] = None
    processed = 0

    try:
        for frame in source.frames():
            pose = engine.estimate(frame, source=f"{engine.info().engine}:{source_label}")
            report = assessor.assess(pose)
            # Pose quality is judged on raw landmarks, because smoothing would
            # hide the jitter that quality exists to detect. Features are
            # derived from the filtered stream, because thresholds must not be
            # crossed by noise (CLAUDE.md §8).
            features = extractor.update(pose_filter.apply(pose))

            if exercise is not None:
                for event in exercise.update(pose, features, report):
                    if event.event in _LOGGED_EVENTS:
                        LOGGER.info(
                            "%s%s %s",
                            event.event.value,
                            f" #{event.sequence}" if event.sequence else "",
                            event.payload or "",
                        )
                    if event.event is EventType.REP_COMPLETED:
                        hud.message = f"rep {event.sequence} complete"
            fps_meter.tick()
            inference_mean.add(engine.last_inference_ms)
            processed += 1

            # `source.info()` is read at the moment a recording opens, never
            # up front: the measured frame rate does not exist until frames
            # have actually flowed, and it is what the recording is written
            # with.
            if recording is None and record_from_start and source.measured_fps:
                recording = start_recording(config, engine, source.info(), record_video)

            if recording is not None:
                recording.pose_writer.write(pose, report)
                if recording.video_recorder is not None:
                    recording.video_recorder.write(frame)

            hud.frame_index = frame.index
            hud.timestamp_ms = frame.timestamp_ms
            hud.fps = fps_meter.fps
            hud.inference_ms = inference_mean.mean
            hud.recording_pose = recording is not None
            hud.recording_video = (
                recording is not None and recording.video_recorder is not None
            )
            hud.recording_id = "" if recording is None else recording.recording_id
            hud.recorded_frames = (
                0 if recording is None else recording.pose_writer.frame_count
            )
            if exercise is not None:
                hud.exercise_state = exercise.state.value
                hud.repetitions = exercise.valid_repetitions
                hud.calibrated = exercise.calibration is not None
            hud.features = {
                "hip_height": features.value(HIP_HEIGHT),
                "hip_velocity": features.value(HIP_VERTICAL_VELOCITY),
                "knee_angle": features.value(MEAN_KNEE_ANGLE),
                "trunk_angle": features.value(TRUNK_ANGLE),
                "stance_width": features.value(STANCE_WIDTH_NORMALISED),
            }

            if not headless:
                hint = assess_framing(pose, config.pose_quality.required_landmarks)
                annotated = draw_developer_overlay(
                    frame.image, pose, report, hud, framing=hint
                )
                cv2.imshow(WINDOW_NAME, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in KEY_QUIT:
                    break
                if key == KEY_SKELETON:
                    hud.show_skeleton = not hud.show_skeleton
                if key == KEY_RECORD:
                    if recording is None:
                        recording = start_recording(
                            config, engine, source.info(), record_video
                        )
                        hud.message = f"recording {recording.recording_id}"
                    else:
                        recording.stop()
                        hud.message = recording.describe()
                        LOGGER.info(hud.message)
                        recording = None

            if max_frames is not None and processed >= max_frames:
                break
    finally:
        if recording is not None:
            recording.stop()
            LOGGER.info(recording.describe())
        if not headless:
            cv2.destroyAllWindows()

    return processed


def command_live(args: argparse.Namespace, config: AppConfig) -> int:
    """Live webcam sandbox (Builds 0-3)."""
    source = build_frame_source(config, device_index=args.device)
    engine = build_pose_engine(config)
    with source, engine:
        info = source.info()
        LOGGER.info(
            "camera_started %s %dx%d @ %.1f fps",
            info.description,
            info.width,
            info.height,
            info.nominal_fps,
        )
        processed = run_frame_loop(
            source,
            engine,
            config,
            mode="LIVE",
            headless=args.headless,
            max_frames=args.max_frames,
            record_video=args.record_video or config.recording.record_video,
            record_from_start=args.record,
        )
    LOGGER.info("live_session_finished frames=%d", processed)
    return 0


def command_exercise(args: argparse.Namespace, config: AppConfig) -> int:
    """Run STS-001 against the live camera.

    Calibration comes from the participant's own movement, so the first
    sit-to-stand establishes the scale and is not counted. Stand and sit
    once before the repetitions you want scored.
    """
    sts_config = load_sts_config(args.exercise_config)
    if args.target is not None:
        sts_config = dataclasses.replace(sts_config, target_repetitions=args.target)

    source = build_frame_source(config, device_index=args.device)
    engine = build_pose_engine(config)
    exercise = SitToStandEngine(sts_config)
    exercise.initialise()

    with source, engine:
        print("STS-001 Sit to Stand.")
        print("The first sit-to-stand calibrates and is not counted.")
        print("Press r to record, q to finish.")
        processed = run_frame_loop(
            source,
            engine,
            config,
            mode="STS-001",
            headless=args.headless,
            max_frames=args.max_frames,
            record_video=args.record_video,
            record_from_start=args.record,
            exercise=exercise,
        )
    exercise.stop()
    _print_result(exercise.result(), args.json)
    LOGGER.info("exercise_finished frames=%d", processed)
    return 0


def command_score(args: argparse.Namespace, config: AppConfig) -> int:
    """Score a recorded pose stream with STS-001, running no pose inference.

    This is the reproducible path: the same recording must always produce the
    same result, so an algorithm change can be judged against a known
    recording rather than against a fresh demonstration (CLAUDE.md §17).
    """
    sts_config = load_sts_config(args.exercise_config)
    if args.target is not None:
        sts_config = dataclasses.replace(sts_config, target_repetitions=args.target)

    assessor = PoseQualityAssessor(config.pose_quality)
    pose_filter = PoseFilter(config.filtering)
    extractor = FeatureExtractor(config.features)
    exercise = SitToStandEngine(sts_config)
    exercise.initialise()

    events: list[Event] = []
    with PoseStreamSource(args.path) as stream:
        metadata = stream.metadata
        for pose in stream.poses():
            quality = assessor.assess(pose)
            features = extractor.update(pose_filter.apply(pose))
            events.extend(exercise.update(pose, features, quality))
    events.extend(exercise.stop())

    result = exercise.result()
    print(f"Recording   {metadata.recording_id}   view {metadata.camera_view}")
    print(f"Algorithm   STS-001 {result.exercise_algorithm_version}")
    print()
    for event_type in _LOGGED_EVENTS:
        count = sum(1 for e in events if e.event is event_type)
        if count:
            print(f"  {event_type.value:24} {count}")
    print()
    _print_result(result, args.json)

    if args.expect is not None:
        detected = result.valid_repetitions
        missed = max(0, args.expect - detected)
        false_positive = max(0, detected - args.expect)
        print(
            f"\nGround truth {args.expect}: detected {detected}, "
            f"missed {missed}, false positives {false_positive}"
        )
        # A false repetition is worse than a conservative miss
        # (Document 03 §49), so only that fails the check.
        return 1 if false_positive else 0
    return 0


def _print_result(result: ExerciseResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    print(f"Repetitions      {result.valid_repetitions}", end="")
    if result.target_repetitions:
        print(f" / {result.target_repetitions}")
    else:
        print()
    print(f"Partial          {result.partial_repetitions}")
    print(f"Duration         {result.duration_seconds:.1f}s")
    for name, value in result.metrics.items():
        if isinstance(value, (int, float)):
            print(f"  {name:32} {value}")
    if result.quality_flags:
        print(f"Quality flags    {result.quality_flags}")
    print(f"Pose quality     {result.pose_quality} (worst seen)")


def command_setup(args: argparse.Namespace, config: AppConfig) -> int:
    """Camera framing check, with no recording.

    Stand where you intend to exercise and adjust the camera until the banner
    reads GOOD POSITION, sitting and standing. The banner is sized to be read
    from across a room, which the ordinary HUD text is not.
    """
    source = build_frame_source(config, device_index=args.device)
    engine = build_pose_engine(config)
    with source, engine:
        print("Framing check. Stand where you will exercise, then sit and stand.")
        print("Adjust the camera until the banner reads GOOD POSITION for both.")
        print("Press q to finish.")
        processed = run_frame_loop(
            source,
            engine,
            config,
            mode="SETUP",
            headless=args.headless,
            max_frames=args.max_frames,
            record_video=False,
            record_from_start=False,
            setup_mode=True,
        )
    LOGGER.info("setup_finished frames=%d", processed)
    return 0


def command_replay_video(args: argparse.Namespace, config: AppConfig) -> int:
    """Re-run pose inference over a recorded video."""
    source = VideoFileFrameSource(args.path, realtime=args.realtime)
    engine = build_pose_engine(config)
    with source, engine:
        processed = run_frame_loop(
            source,
            engine,
            config,
            mode="REPLAY VIDEO",
            headless=args.headless,
            max_frames=args.max_frames,
            record_video=False,
            record_from_start=args.record,
        )
    LOGGER.info("video_replay_finished frames=%d", processed)
    return 0


def command_replay_pose(args: argparse.Namespace, config: AppConfig) -> int:
    """Replay a recorded canonical pose stream.

    Runs no pose inference at all: the skeleton is drawn on a blank canvas
    from canonical landmarks alone. This is the mode that proves the exercise
    pipeline is independent of the pose engine (CLAUDE.md §17).
    """
    assessor = PoseQualityAssessor(config.pose_quality)
    fps_meter = FpsMeter()
    processed = 0

    with PoseStreamSource(args.path) as stream:
        metadata = stream.metadata
        LOGGER.info(
            "pose_replay_started id=%s engine=%s model=%s view=%s",
            metadata.recording_id,
            metadata.pose_engine,
            metadata.pose_model_version,
            metadata.camera_view,
        )
        width, height = _canvas_size(metadata)
        hud = DeveloperHud(
            mode="REPLAY POSE",
            source_label=f"{metadata.recording_id} ({metadata.pose_engine})",
        )
        try:
            for pose in stream.poses():
                report = assessor.assess(pose)
                fps_meter.tick()
                processed += 1

                hud.frame_index = pose.frame_index or processed
                hud.timestamp_ms = pose.timestamp_ms
                hud.fps = fps_meter.fps

                if not args.headless:
                    canvas = np.zeros(
                        (pose.image_height or height, pose.image_width or width, 3),
                        dtype=np.uint8,
                    )
                    annotated = draw_developer_overlay(canvas, pose, report, hud)
                    cv2.imshow(WINDOW_NAME, annotated)
                    if (cv2.waitKey(_replay_delay_ms(args, metadata)) & 0xFF) in KEY_QUIT:
                        break
                if args.max_frames is not None and processed >= args.max_frames:
                    break
        finally:
            if not args.headless:
                cv2.destroyAllWindows()

    LOGGER.info("pose_replay_finished frames=%d", processed)
    return 0


def command_check(args: argparse.Namespace, config: AppConfig) -> int:
    """Report whether the local setup can run the sandbox.

    Checks configuration, the pose model and the camera separately, so a
    failure names which one is at fault rather than only that something is.
    """
    print(f"Vision Exercise System {APPLICATION_VERSION}")
    print(
        f"  platform        {platform.system()} {platform.machine()} "
        f"python {platform.python_version()}"
    )
    ok = True

    model_path = config.pose.resolved_model_path()
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"  pose model      OK    {model_path.name} ({size_mb:.1f} MB)")
    else:
        ok = False
        print(f"  pose model      MISSING  {model_path}")
        print("                  run: python tools/fetch_models.py")

    if model_path.exists():
        try:
            engine = build_pose_engine(config)
            engine.start()
            engine.close()
            print(f"  pose engine     OK    {config.pose.engine}")
        except (PoseEngineError, ConfigurationError) as exc:
            ok = False
            print(f"  pose engine     FAILED  {exc}")

    if args.skip_camera:
        print(f"  camera          SKIPPED  (configured source: {config.camera.source})")
    else:
        try:
            with build_frame_source(config) as camera:
                frame = camera.next_frame()
                info = camera.info()
            if frame is None:
                ok = False
                print("  camera          FAILED  opened but returned no frame")
            else:
                print(
                    f"  camera          OK    {info.description} "
                    f"{frame.width}x{frame.height} @ {info.nominal_fps:.0f} fps"
                )
        except FrameSourceError as exc:
            ok = False
            print(f"  camera          FAILED  [{exc.code}] {exc}")

    recordings = config.recording.resolved_directory()
    print(f"  recordings      {recordings}")
    print(f"  camera view     {config.camera.view}")
    return 0 if ok else 1


def _canvas_size(metadata: PoseStreamMetadata) -> tuple[int, int]:
    """Fallback canvas size for pose replay when frames carry no image size."""
    try:
        width_text, height_text = metadata.nominal_resolution.lower().split("x")
        return int(width_text), int(height_text)
    except (ValueError, AttributeError):
        return 1280, 720


def _replay_delay_ms(args: argparse.Namespace, metadata: PoseStreamMetadata) -> int:
    """Frame delay for pose replay: natural pace, or as fast as possible."""
    if not args.realtime:
        return 1
    fps = metadata.nominal_fps or 30.0
    return max(1, int(1000.0 / fps))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vision-exercise",
        description="Pose Sandbox — camera, pose, record and replay.",
    )
    parser.add_argument("--config", type=Path, default=None, help="Configuration file.")
    parser.add_argument(
        "--log-level", default=None, help="Override the configured log level."
    )
    subparsers = parser.add_subparsers(dest="command")

    live = subparsers.add_parser("live", help="Live webcam sandbox.")
    live.add_argument("--device", type=int, default=None, help="Camera index.")
    live.add_argument(
        "--camera-view",
        default=None,
        help="Camera placement recorded with the take, e.g. frontal, "
        "frontal_oblique, lateral. Overrides camera.view in configuration.",
    )
    live.add_argument(
        "--record", action="store_true", help="Start recording immediately."
    )
    live.add_argument(
        "--record-video",
        action="store_true",
        help="Include video in recordings, not only the pose stream.",
    )
    live.add_argument("--headless", action="store_true", help="Do not open a window.")
    live.add_argument("--max-frames", type=int, default=None, help="Stop after N frames.")
    live.set_defaults(handler=command_live)

    exercise = subparsers.add_parser(
        "exercise", help="Run STS-001 sit-to-stand against the live camera."
    )
    exercise.add_argument("--device", type=int, default=None, help="Camera index.")
    exercise.add_argument(
        "--camera-view", default=None, help="Camera placement recorded with the take."
    )
    exercise.add_argument(
        "--target", type=int, default=None, help="Target repetitions."
    )
    exercise.add_argument(
        "--exercise-config", type=Path, default=None, help="STS-001 configuration file."
    )
    exercise.add_argument(
        "--record", action="store_true", help="Record a pose stream from the start."
    )
    exercise.add_argument(
        "--record-video", action="store_true", help="Also record video."
    )
    exercise.add_argument("--json", action="store_true", help="Print the result as JSON.")
    exercise.add_argument("--headless", action="store_true", help="Do not open a window.")
    exercise.add_argument(
        "--max-frames", type=int, default=None, help="Stop after N frames."
    )
    exercise.set_defaults(handler=command_exercise)

    score = subparsers.add_parser(
        "score", help="Score a recorded pose stream with STS-001. No inference."
    )
    score.add_argument("path", type=Path, help="Pose stream (.jsonl).")
    score.add_argument("--target", type=int, default=None, help="Target repetitions.")
    score.add_argument(
        "--expect", type=int, default=None,
        help="Known repetition count. Exits non-zero on a false positive.",
    )
    score.add_argument(
        "--exercise-config", type=Path, default=None, help="STS-001 configuration file."
    )
    score.add_argument("--json", action="store_true", help="Print the result as JSON.")
    score.set_defaults(handler=command_score)

    setup = subparsers.add_parser(
        "setup", help="Camera framing check before recording. No recording made."
    )
    setup.add_argument("--device", type=int, default=None, help="Camera index.")
    setup.add_argument("--headless", action="store_true", help="Do not open a window.")
    setup.add_argument(
        "--max-frames", type=int, default=None, help="Stop after N frames."
    )
    setup.set_defaults(handler=command_setup)

    replay_video = subparsers.add_parser(
        "replay-video", help="Re-run pose inference over a recorded video."
    )
    replay_video.add_argument("path", type=Path, help="Video file.")
    replay_video.add_argument(
        "--record", action="store_true", help="Write a pose stream from the replay."
    )
    replay_video.add_argument(
        "--realtime", action="store_true", help="Play at the file's own frame rate."
    )
    replay_video.add_argument("--headless", action="store_true", help="Do not open a window.")
    replay_video.add_argument(
        "--max-frames", type=int, default=None, help="Stop after N frames."
    )
    replay_video.set_defaults(handler=command_replay_video)

    replay_pose = subparsers.add_parser(
        "replay-pose", help="Replay a canonical pose stream without pose inference."
    )
    replay_pose.add_argument("path", type=Path, help="Pose stream (.jsonl).")
    replay_pose.add_argument(
        "--realtime", action="store_true", help="Play at the recorded frame rate."
    )
    replay_pose.add_argument("--headless", action="store_true", help="Do not open a window.")
    replay_pose.add_argument(
        "--max-frames", type=int, default=None, help="Stop after N frames."
    )
    replay_pose.set_defaults(handler=command_replay_pose)

    check = subparsers.add_parser("check", help="Verify the local setup.")
    check.add_argument(
        "--skip-camera", action="store_true", help="Do not try to open the camera."
    )
    check.set_defaults(handler=command_check)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "handler", None) is None:
        parser.print_help()
        return 2

    try:
        config = load_config(args.config)
        camera_view = getattr(args, "camera_view", None)
        if camera_view:
            # Overriding per run beats editing configuration between takes,
            # which is how a multi-view session ends up mislabelled.
            config = dataclasses.replace(
                config, camera=dataclasses.replace(config.camera, view=camera_view)
            )
    except ConfigurationError as exc:
        print(f"[CONFIGURATION_INVALID] {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, (args.log_level or config.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(message)s",
    )

    try:
        return int(args.handler(args, config))
    except (FrameSourceError, PoseEngineError) as exc:
        print(f"[{exc.code}] {exc}", file=sys.stderr)
        return 1
    except (ConfigurationError, PoseStreamError, VideoRecorderError) as exc:
        print(f"[{getattr(exc, 'code', 'ERROR')}] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
