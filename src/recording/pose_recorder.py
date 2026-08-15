"""Canonical pose-stream recording (Build 3).

Recording is core infrastructure, not a debugging extra (CLAUDE.md §17,
ADR-008). A recorded canonical pose stream lets filtering, features and
exercise state machines be re-run against identical input, with none of the
frame-to-frame variability of re-running pose inference.

File format
-----------
JSON Lines, one JSON object per line:

    line 1   {"record": "metadata", ...}
    line 2+  {"record": "frame", "pose": {...}, "pose_quality": {...}}

Document 03 §25 sketches a single JSON object with a `frames` array but notes
that a line-oriented format is preferable for larger recordings. JSON Lines is
used here because it streams without holding the recording in memory and
because a recording interrupted by a crash remains readable up to the last
complete line.

Pose streams contain no images. They are far less privacy-exposing than video,
but they still describe a real person's movement and are written to a
gitignored directory (CLAUDE.md §28, §30).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO

from src.pose.models import PoseFrame
from src.pose.quality import PoseQualityReport
from src.version import APPLICATION_VERSION, POSE_STREAM_FORMAT_VERSION

METADATA_RECORD = "metadata"
FRAME_RECORD = "frame"


def new_recording_id(prefix: str = "dev") -> str:
    """Return a timestamped recording identifier.

    Deliberately carries no participant name (CLAUDE.md §18). Uses local time
    so that a developer can find a recording they just made; the metadata
    holds the authoritative UTC timestamp.
    """
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


@dataclass
class PoseStreamMetadata:
    """Provenance recorded alongside a canonical pose stream.

    Attributes:
        recording_id: Identifier shared with any video recorded at the same
            time, so the two files can be paired.
        recording_date: ISO-8601 UTC timestamp of when recording started.
        application_version: Version of this application.
        pose_engine: Engine that produced the stream.
        pose_model_version: Model bundle identifier.
        pose_engine_detail: Engine configuration summary.
        camera_view: Nominal camera placement, e.g. "frontal_oblique". Camera
            position is an experimental variable and must be recorded
            (Document 03 §10).
        nominal_resolution: Capture resolution as "WIDTHxHEIGHT".
        nominal_fps: Capture frame rate the device or file claimed. Kept for
            provenance; do not compute with it. Webcams misreport it.
        measured_fps: Capture frame rate actually observed before recording
            began, or None if it could not be measured. This is the rate any
            paired video was written at, and the one to trust.
        source: Frame-source description from `FrameSourceInfo.to_dict()`.
        format_version: Version of this file format.
        notes: Free-text developer note about the take.
    """

    recording_id: str
    recording_date: str
    application_version: str
    pose_engine: str
    pose_model_version: str
    pose_engine_detail: str = ""
    camera_view: str = "unspecified"
    nominal_resolution: str = ""
    nominal_fps: float = 0.0
    measured_fps: Optional[float] = None
    source: dict[str, Any] = field(default_factory=dict)
    format_version: str = POSE_STREAM_FORMAT_VERSION
    notes: str = ""

    @property
    def effective_fps(self) -> float:
        """The frame rate to compute with: measured where available."""
        if self.measured_fps is not None and self.measured_fps > 0:
            return self.measured_fps
        return self.nominal_fps

    @classmethod
    def create(
        cls,
        recording_id: str,
        pose_engine: str,
        pose_model_version: str,
        pose_engine_detail: str = "",
        camera_view: str = "unspecified",
        width: int = 0,
        height: int = 0,
        nominal_fps: float = 0.0,
        measured_fps: Optional[float] = None,
        source: Optional[dict[str, Any]] = None,
        notes: str = "",
    ) -> "PoseStreamMetadata":
        """Build metadata, stamping the current UTC time and app version."""
        return cls(
            recording_id=recording_id,
            recording_date=datetime.now(timezone.utc).isoformat(),
            application_version=APPLICATION_VERSION,
            pose_engine=pose_engine,
            pose_model_version=pose_model_version,
            pose_engine_detail=pose_engine_detail,
            camera_view=camera_view,
            nominal_resolution=f"{width}x{height}",
            nominal_fps=nominal_fps,
            measured_fps=measured_fps,
            source=source or {},
            notes=notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recording_id": self.recording_id,
            "recording_date": self.recording_date,
            "application_version": self.application_version,
            "pose_engine": self.pose_engine,
            "pose_model_version": self.pose_model_version,
            "pose_engine_detail": self.pose_engine_detail,
            "camera_view": self.camera_view,
            "nominal_resolution": self.nominal_resolution,
            "nominal_fps": self.nominal_fps,
            "measured_fps": self.measured_fps,
            "source": dict(self.source),
            "format_version": self.format_version,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PoseStreamMetadata":
        return cls(
            recording_id=str(data.get("recording_id", "")),
            recording_date=str(data.get("recording_date", "")),
            application_version=str(data.get("application_version", "")),
            pose_engine=str(data.get("pose_engine", "")),
            pose_model_version=str(data.get("pose_model_version", "")),
            pose_engine_detail=str(data.get("pose_engine_detail", "")),
            camera_view=str(data.get("camera_view", "unspecified")),
            nominal_resolution=str(data.get("nominal_resolution", "")),
            nominal_fps=float(data.get("nominal_fps", 0.0)),
            # Absent in format 0.1 recordings, which predate rate measurement.
            measured_fps=(
                None
                if data.get("measured_fps") is None
                else float(data["measured_fps"])
            ),
            source=dict(data.get("source", {})),
            format_version=str(data.get("format_version", "")),
            notes=str(data.get("notes", "")),
        )


class PoseStreamWriter:
    """Writes canonical pose frames to a JSON Lines file."""

    def __init__(self, path: Path | str, metadata: PoseStreamMetadata) -> None:
        self._path = Path(path)
        self._metadata = metadata
        self._handle: Optional[TextIO] = None
        self._frame_count = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def start(self) -> None:
        """Create the file and write the metadata line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("w", encoding="utf-8")
        record = {"record": METADATA_RECORD, **self._metadata.to_dict()}
        self._handle.write(json.dumps(record) + "\n")
        self._frame_count = 0

    def write(
        self, pose: PoseFrame, quality: Optional[PoseQualityReport] = None
    ) -> None:
        """Append one pose frame, with its pose-quality verdict if available."""
        if self._handle is None:
            raise RuntimeError("PoseStreamWriter.start() was not called.")
        record: dict[str, Any] = {"record": FRAME_RECORD, "pose": pose.to_dict()}
        if quality is not None:
            record["pose_quality"] = quality.to_dict()
        self._handle.write(json.dumps(record) + "\n")
        self._frame_count += 1

    def stop(self) -> None:
        """Flush and close the file. Safe to call more than once."""
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "PoseStreamWriter":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
