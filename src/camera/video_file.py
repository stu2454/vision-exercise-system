"""Recorded video frame source (Build 3)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import cv2

from src.camera.base import Frame, FrameSource, FrameSourceError, FrameSourceInfo


class VideoFileFrameSource(FrameSource):
    """Replays a video file as a frame source.

    Timestamps come from the file rather than from a clock. This is what makes
    replay reproducible: the same file produces the same timestamps on every
    run and on every machine, regardless of how fast the pose engine happens
    to run (Document 03 §26).

    Two timestamp strategies are available:

    ``index``
        Frame index divided by the file's frame rate. Exact for
        constant-frame-rate files, which is everything this project records
        itself, and identical on every backend. This is the default.
    ``media``
        The container's own presentation time. Correct for
        variable-frame-rate sources such as phone recordings, but OpenCV
        reports it inconsistently: with the default macOS backend the third
        frame of a file repeats the second frame's timestamp. A monotonic
        guard covers that, at the cost of a small timing error.

    `realtime=True` additionally sleeps between frames so a developer can
    watch the replay at natural speed. It changes only presentation pacing,
    never the timestamps handed downstream.
    """

    def __init__(
        self,
        path: Path | str,
        realtime: bool = False,
        timestamp_source: str = "index",
    ) -> None:
        """
        Args:
            path: Video file to replay.
            realtime: Pace playback to the file's frame rate for viewing.
            timestamp_source: "index" or "media"; see the class docstring.
        """
        if timestamp_source not in {"index", "media"}:
            raise ValueError(
                f"timestamp_source must be 'index' or 'media', got {timestamp_source!r}"
            )
        self._path = Path(path)
        self._realtime = realtime
        self._timestamp_source = timestamp_source
        self._capture: Optional[cv2.VideoCapture] = None
        self._index = 0
        self._last_timestamp_ms = -1.0
        self._playback_start_perf = 0.0
        self._fallback_fps = 30.0

    def start(self) -> None:
        if not self._path.exists():
            raise FrameSourceError(
                "VIDEO_UNAVAILABLE", f"Video file not found: {self._path}"
            )
        capture = cv2.VideoCapture(str(self._path))
        if not capture.isOpened():
            capture.release()
            raise FrameSourceError(
                "VIDEO_UNAVAILABLE", f"Could not open video file: {self._path}"
            )
        self._capture = capture
        self._index = 0
        self._last_timestamp_ms = -1.0
        self._playback_start_perf = time.perf_counter()
        self.reset_frame_rate()

    def next_frame(self) -> Optional[Frame]:
        if self._capture is None:
            raise FrameSourceError("VIDEO_UNAVAILABLE", "Video source was not started.")
        # Read media position before the frame is consumed, so it belongs to
        # the frame being returned rather than to the following one.
        position_ms = float(self._capture.get(cv2.CAP_PROP_POS_MSEC))
        ok, image = self._capture.read()
        if not ok or image is None:
            return None

        timestamp_ms = self._timestamp_for(position_ms)
        self._last_timestamp_ms = timestamp_ms

        if self._realtime:
            target = self._playback_start_perf + timestamp_ms / 1000.0
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)

        frame = Frame(image=image, timestamp_ms=timestamp_ms, index=self._index)
        self._index += 1
        self.observe_frame_rate(timestamp_ms)
        return frame

    def _timestamp_for(self, position_ms: float) -> float:
        """Timestamp for the frame just decoded, guaranteed to increase."""
        interval_ms = 1000.0 / self._nominal_fps()
        if self._timestamp_source == "index":
            return self._index * interval_ms
        # Media time: guard against containers that repeat or omit a position.
        if position_ms <= self._last_timestamp_ms:
            return max(self._last_timestamp_ms + interval_ms, 0.0)
        return position_ms

    def stop(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def info(self) -> FrameSourceInfo:
        if self._capture is None:
            raise FrameSourceError("VIDEO_UNAVAILABLE", "Video source was not started.")
        return FrameSourceInfo(
            kind="video_file",
            description=f"video:{self._path.name}",
            width=int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            nominal_fps=self._nominal_fps(),
            measured_fps=self.measured_fps,
            extra={
                "path": str(self._path),
                "frame_count": int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            },
        )

    def _nominal_fps(self) -> float:
        if self._capture is None:
            return self._fallback_fps
        fps = float(self._capture.get(cv2.CAP_PROP_FPS))
        return fps if fps > 0 else self._fallback_fps
