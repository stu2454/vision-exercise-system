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


@dataclass
class FrameSourceInfo:
    """Provenance and configuration of a frame source, for recording metadata."""

    kind: str
    description: str
    width: int
    height: int
    nominal_fps: float
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "width": self.width,
            "height": self.height,
            "nominal_fps": self.nominal_fps,
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
    """A source of images: a webcam, a video file, or a future equivalent."""

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
