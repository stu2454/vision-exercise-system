"""Explicit development video recording (Build 3).

Video recording is a development and testing capability only. It is never on
by default, it must be started deliberately, and the developer overlay shows a
visible indicator while it runs (CLAUDE.md §18, §28; Document 03 §40).

Recorded video is written to a gitignored directory and must not be committed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2

from src.camera.base import Frame


class VideoRecorderError(RuntimeError):
    """Raised when a video file cannot be opened for writing."""


class VideoRecorder:
    """Writes frames to a local video file.

    The frame size is fixed by the first frame written; later frames of a
    different size are rejected rather than silently distorted, because a
    changed frame size means the recording no longer matches the pose stream
    captured alongside it.
    """

    def __init__(
        self, path: Path | str, fps: float = 30.0, fourcc: str = "mp4v"
    ) -> None:
        """
        Args:
            path: Output video path.
            fps: Frame rate written into the container. Should be the source's
                nominal rate; a wrong value makes replay timing wrong.
            fourcc: OpenCV codec identifier. "mp4v" is used because it is
                available in stock OpenCV wheels on all development platforms.
        """
        self._path = Path(path)
        self._fps = fps if fps > 0 else 30.0
        self._fourcc = fourcc
        self._writer: Optional[cv2.VideoWriter] = None
        self._size: Optional[tuple[int, int]] = None
        self._frame_count = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def start(self, width: int, height: int) -> None:
        """Open the output file for the given frame size."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(self._path),
            cv2.VideoWriter_fourcc(*self._fourcc),
            self._fps,
            (width, height),
        )
        if not writer.isOpened():
            writer.release()
            raise VideoRecorderError(
                f"Could not open video writer for {self._path} "
                f"with codec {self._fourcc}."
            )
        self._writer = writer
        self._size = (width, height)
        self._frame_count = 0

    def write(self, frame: Frame) -> None:
        """Append one frame. Starts the file if not already started."""
        if self._writer is None:
            self.start(frame.width, frame.height)
        if self._size != (frame.width, frame.height):
            raise VideoRecorderError(
                f"Frame size changed during recording: expected {self._size}, "
                f"received {(frame.width, frame.height)}."
            )
        assert self._writer is not None
        self._writer.write(frame.image)
        self._frame_count += 1

    def stop(self) -> None:
        """Finalise the file. Safe to call more than once."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def __enter__(self) -> "VideoRecorder":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
