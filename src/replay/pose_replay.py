"""Canonical pose-stream replay (Build 3).

Replays a recorded pose stream without running any pose inference, which tests

    pose -> filtering -> features -> exercise

with the pose-model variability removed (CLAUDE.md §17). The same recording
must always produce the same downstream result.

This module deliberately imports neither MediaPipe nor OpenCV. A test asserts
that, because the moment pose replay needs a vision library, the canonical
abstraction has stopped doing its job.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, TextIO

from src.pose.models import PoseFrame
from src.recording.pose_recorder import (
    FRAME_RECORD,
    METADATA_RECORD,
    PoseStreamMetadata,
)


class PoseStreamError(RuntimeError):
    """Raised when a pose stream is missing, malformed or truncated."""


@dataclass(frozen=True)
class PoseStreamRecord:
    """One frame from a recorded pose stream.

    Attributes:
        pose: The canonical pose as recorded.
        recorded_quality: The pose-quality verdict stored at record time, if
            any, as a plain dict. It is provenance for comparison against a
            re-run of the current quality logic, and must not be fed back into
            the pipeline as though it were freshly computed.
    """

    pose: PoseFrame
    recorded_quality: Optional[dict[str, Any]] = None


class PoseStreamSource:
    """Reads canonical pose frames back from a JSON Lines recording.

    This is not a `FrameSource`: it produces poses, not images. Keeping the
    two abstractions separate avoids pushing fake image buffers through the
    pipeline (CLAUDE.md §6).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._handle: Optional[TextIO] = None
        self._metadata: Optional[PoseStreamMetadata] = None
        self._index = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def metadata(self) -> PoseStreamMetadata:
        """Recording provenance. Valid only after `start`."""
        if self._metadata is None:
            raise PoseStreamError("Pose stream was not started.")
        return self._metadata

    def start(self) -> None:
        """Open the recording and read its metadata line."""
        if not self._path.exists():
            raise PoseStreamError(f"Pose stream not found: {self._path}")
        self._handle = self._path.open("r", encoding="utf-8")
        first = self._handle.readline()
        if not first.strip():
            self.stop()
            raise PoseStreamError(f"Pose stream is empty: {self._path}")
        try:
            record = json.loads(first)
        except json.JSONDecodeError as exc:
            self.stop()
            raise PoseStreamError(
                f"Pose stream metadata is not valid JSON: {self._path}"
            ) from exc
        if record.get("record") != METADATA_RECORD:
            self.stop()
            raise PoseStreamError(
                f"Pose stream does not begin with a metadata record: {self._path}"
            )
        self._metadata = PoseStreamMetadata.from_dict(record)
        self._index = 0

    def next_record(self) -> Optional[PoseStreamRecord]:
        """Return the next record, or None at end of stream."""
        if self._handle is None:
            raise PoseStreamError("Pose stream was not started.")
        while True:
            line = self._handle.readline()
            if not line:
                return None
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PoseStreamError(
                    f"Malformed record at line {self._index + 2} of {self._path}"
                ) from exc
            if record.get("record") != FRAME_RECORD:
                continue
            self._index += 1
            return PoseStreamRecord(
                pose=PoseFrame.from_dict(record["pose"]),
                recorded_quality=record.get("pose_quality"),
            )

    def next_pose(self) -> Optional[PoseFrame]:
        """Return the next pose frame, or None at end of stream."""
        record = self.next_record()
        return None if record is None else record.pose

    def records(self) -> Iterator[PoseStreamRecord]:
        """Iterate every record until the stream is exhausted."""
        while True:
            record = self.next_record()
            if record is None:
                return
            yield record

    def poses(self) -> Iterator[PoseFrame]:
        """Iterate every pose frame until the stream is exhausted."""
        for record in self.records():
            yield record.pose

    def stop(self) -> None:
        """Close the recording. Safe to call more than once."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "PoseStreamSource":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def read_pose_stream(
    path: Path | str,
) -> tuple[PoseStreamMetadata, list[PoseStreamRecord]]:
    """Read an entire pose stream into memory.

    Convenient for tests and short recordings. Use `PoseStreamSource` directly
    for long recordings.
    """
    with PoseStreamSource(path) as source:
        return source.metadata, list(source.records())
