"""Frame-source abstraction.

Live and recorded image inputs must be interchangeable (Document 03 §8,
CLAUDE.md §6). Everything above this layer receives `Frame` objects and never
asks where they came from.

A recorded *pose stream* is deliberately not a FrameSource: it carries no
images, and pretending otherwise would push empty image buffers through the
whole pipeline. Pose-stream replay uses its own source type in
`src.replay.pose_replay`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import numpy as np


@dataclass(frozen=True)
class Frame:
    """A single captured image and its timing metadata.

    Attributes:
        image: BGR image array as produced by OpenCV. Only the camera, pose
            and UI layers may touch this; exercise logic must not.
        timestamp_ms: Milliseconds from the start of this source. Monotonic
            and non-decreasing (Document 03 §24).
        index: Zero-based frame index within this source.
    """

    image: np.ndarray
    timestamp_ms: float
    index: int

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


MINIMUM_RATE_SAMPLES = 10
"""Frames needed before a measured frame rate is trusted."""


class FrameRateTracker:
    """Measures the real frame rate from delivered frame timestamps.

    Cameras routinely misreport their frame rate. A Logitech webcam observed
    during development advertised 15 fps through `CAP_PROP_FPS` while actually
    delivering 29.4 fps. That number is not cosmetic: it is written into
    recording metadata, used as the frame rate of recorded video, and used to
    derive timestamps when that video is replayed. Believing it would have put
    a silent 2x error into every velocity feature computed from replay.

    Measuring from frame timestamps rather than from a wall clock keeps this
    correct for every source: live sources timestamp frames as they arrive,
    and file sources carry media time.
    """

    def __init__(self, window: int = 120) -> None:
        self._window = window
        self._timestamps: deque[float] = deque(maxlen=window)

    def observe(self, timestamp_ms: float) -> None:
        self._timestamps.append(timestamp_ms)

    def reset(self) -> None:
        self._timestamps.clear()

    @property
    def samples(self) -> int:
        return len(self._timestamps)

    @property
    def fps(self) -> Optional[float]:
        """Measured frames per second, or None until enough frames are seen."""
        if len(self._timestamps) < MINIMUM_RATE_SAMPLES:
            return None
        elapsed_ms = self._timestamps[-1] - self._timestamps[0]
        if elapsed_ms <= 0:
            return None
        return (len(self._timestamps) - 1) * 1000.0 / elapsed_ms


@dataclass
class FrameSourceInfo:
    """Provenance and configuration of a frame source, for recording metadata.

    Attributes:
        nominal_fps: The frame rate the device or file claims. Frequently
            wrong for webcams.
        measured_fps: The frame rate actually observed, or None if too few
            frames have been delivered to measure one.
    """

    kind: str
    description: str
    width: int
    height: int
    nominal_fps: float
    measured_fps: Optional[float] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_fps(self) -> float:
        """The frame rate to record and to replay with.

        Prefers the measured rate whenever one exists, because it is an
        observation and `nominal_fps` is only a claim.
        """
        if self.measured_fps is not None and self.measured_fps > 0:
            return self.measured_fps
        return self.nominal_fps

    @property
    def rate_disagreement(self) -> Optional[float]:
        """Ratio of measured to nominal rate, or None if not measurable.

        A value far from 1.0 means the device misreports its frame rate and
        anything derived from `nominal_fps` alone would be wrong.
        """
        if self.measured_fps is None or self.nominal_fps <= 0:
            return None
        return self.measured_fps / self.nominal_fps

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "width": self.width,
            "height": self.height,
            "nominal_fps": self.nominal_fps,
            "measured_fps": self.measured_fps,
            "effective_fps": self.effective_fps,
            **self.extra,
        }


class FrameSourceError(RuntimeError):
    """Raised when a frame source cannot be opened or read.

    Carries a stable code from the Document 03 §36 error vocabulary so the UI
    can translate it without parsing message text.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FrameSource(ABC):
    """A source of images: a webcam, a video file, or a future equivalent.

    Implementations should call `observe_frame_rate` for each frame they
    deliver, and reset it in `start`, so `measured_fps` reflects reality
    rather than what the device claims.
    """

    _rate_tracker: Optional[FrameRateTracker] = None

    @property
    def _rates(self) -> FrameRateTracker:
        if self._rate_tracker is None:
            self._rate_tracker = FrameRateTracker()
        return self._rate_tracker

    def observe_frame_rate(self, timestamp_ms: float) -> None:
        """Record a delivered frame's timestamp for rate measurement."""
        self._rates.observe(timestamp_ms)

    def reset_frame_rate(self) -> None:
        """Forget measured timing. Call from `start`."""
        self._rates.reset()

    @property
    def measured_fps(self) -> Optional[float]:
        """Observed frame rate, or None until enough frames have arrived."""
        return self._rates.fps

    @abstractmethod
    def start(self) -> None:
        """Open the underlying device or file. Raises FrameSourceError."""

    @abstractmethod
    def next_frame(self) -> Optional[Frame]:
        """Return the next frame, or None when the source is exhausted.

        A None return means "no more frames will ever arrive" (end of file,
        camera closed). A source that is merely waiting should block.
        """

    @abstractmethod
    def stop(self) -> None:
        """Release the underlying device or file. Safe to call more than once."""

    @abstractmethod
    def info(self) -> FrameSourceInfo:
        """Describe this source. Valid only after `start`."""

    def frames(self) -> Iterator[Frame]:
        """Iterate frames until the source is exhausted."""
        while True:
            frame = self.next_frame()
            if frame is None:
                return
            yield frame

    def __enter__(self) -> "FrameSource":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
