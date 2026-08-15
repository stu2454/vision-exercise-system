"""Recorded-video replay through pose inference (Build 3).

Tests the path

    video -> pose -> features -> exercise

which pose-stream replay cannot cover, because it is the only replay mode that
re-runs the pose model. It is therefore how a pose-engine change or upgrade
gets detected (Document 03 §48).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from src.camera.base import Frame
from src.camera.video_file import VideoFileFrameSource
from src.pose.base import PoseEngine
from src.pose.models import PoseFrame
from src.pose.quality import PoseQualityAssessor, PoseQualityReport


@dataclass(frozen=True)
class ReplayStep:
    """One replayed frame and everything derived from it.

    Attributes:
        frame: The decoded video frame.
        pose: Canonical pose estimated from that frame.
        quality: Pose-quality verdict, if an assessor was supplied.
        inference_ms: Pose inference time for this frame, if reported.
    """

    frame: Frame
    pose: PoseFrame
    quality: Optional[PoseQualityReport] = None
    inference_ms: Optional[float] = None


def replay_video(
    path: Path | str,
    engine: PoseEngine,
    quality: Optional[PoseQualityAssessor] = None,
    realtime: bool = False,
) -> Iterator[ReplayStep]:
    """Yield pose estimates for every frame of a video file.

    The engine must already be started; this function never starts or closes
    it. Model loading is slow, so its lifecycle stays with the caller, who can
    then replay several files against one loaded model.

    Args:
        path: Video file to replay.
        engine: A started pose engine.
        quality: Optional assessor. Reset at the start of the replay so that
            each replay of the same file gives identical results.
        realtime: Pace playback for human viewing. Does not affect output.
    """
    if quality is not None:
        quality.reset()
    source_name = f"{engine.info().engine}:video:{Path(path).name}"
    with VideoFileFrameSource(path, realtime=realtime) as source:
        for frame in source.frames():
            pose = engine.estimate(frame, source=source_name)
            report = None if quality is None else quality.assess(pose)
            yield ReplayStep(
                frame=frame,
                pose=pose,
                quality=report,
                inference_ms=engine.last_inference_ms,
            )
