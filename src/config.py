"""Versioned configuration loading (Document 03 §33, CLAUDE.md §24).

Engineering parameters belong in `config/`, not scattered through Python
modules. Values here are implementation parameters to be established
experimentally; they are not clinical thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from src.pose.quality import DEFAULT_REQUIRED_LANDMARKS, PoseQualityConfig

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "application.yaml"


class ConfigurationError(RuntimeError):
    """Raised when configuration is missing or invalid.

    Uses the CONFIGURATION_INVALID code from the Document 03 §36 vocabulary.
    """

    code = "CONFIGURATION_INVALID"


CAMERA_SOURCES = ("webcam", "picamera")


@dataclass(frozen=True)
class CameraConfig:
    """Camera capture settings and the camera-placement metadata.

    Camera placement is an unresolved experimental variable (Document 03 §10),
    so `view`, `nominal_height_cm` and `nominal_distance_m` are recorded with
    every recording rather than assumed.

    Attributes:
        source: "webcam" for a USB camera through OpenCV, or "picamera" for a
            Raspberry Pi Camera Module through picamera2. A CSI camera cannot
            be opened by OpenCV on Pi OS Bookworm, so this is a real choice
            rather than a detail.
        device_index: OpenCV camera index. Ignored when source is "picamera".
        picamera_format: libcamera stream format. Ignored for "webcam". See
            `src.camera.picamera.DEFAULT_PICAMERA_FORMAT` for why the naming
            is counter-intuitive.
    """

    source: str = "webcam"
    device_index: int = 0
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    mirror: bool = True
    picamera_format: str = "RGB888"
    view: str = "unspecified"
    nominal_height_cm: Optional[float] = None
    nominal_distance_m: Optional[float] = None

    def __post_init__(self) -> None:
        if self.source not in CAMERA_SOURCES:
            raise ConfigurationError(
                f"Unknown camera source '{self.source}'. "
                f"Supported: {', '.join(CAMERA_SOURCES)}."
            )


@dataclass(frozen=True)
class PoseConfig:
    """Pose-engine selection and thresholds."""

    engine: str = "mediapipe"
    model_path: str = "models/pose_landmarker_lite.task"
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    def resolved_model_path(self, root: Path = REPOSITORY_ROOT) -> Path:
        """Return the model path, resolved relative to the repository root."""
        path = Path(self.model_path)
        return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class RecordingConfig:
    """Development recording settings.

    `record_video` defaults to false: video capture is an explicit developer
    action, never an ambient default (CLAUDE.md §28).
    """

    directory: str = "recordings"
    record_video: bool = False
    video_fourcc: str = "mp4v"

    def resolved_directory(self, root: Path = REPOSITORY_ROOT) -> Path:
        path = Path(self.directory)
        return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class AppConfig:
    """Complete application configuration."""

    camera: CameraConfig = field(default_factory=CameraConfig)
    pose: PoseConfig = field(default_factory=PoseConfig)
    pose_quality: PoseQualityConfig = field(default_factory=PoseQualityConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    log_level: str = "INFO"


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name) or {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section '{name}' must be a mapping.")
    return value


def _build(cls: type, data: dict[str, Any], section: str) -> Any:
    """Construct a config dataclass, rejecting unknown keys.

    Unknown keys are an error rather than a warning: a silently ignored
    threshold is a parameter the developer believes is in effect when it is
    not, which is exactly the failure this configuration layer exists to
    prevent.
    """
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigurationError(
            f"Unknown key(s) in configuration section '{section}': "
            f"{', '.join(unknown)}"
        )
    try:
        return cls(**data)
    except TypeError as exc:
        raise ConfigurationError(f"Invalid '{section}' configuration: {exc}") from exc


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML, falling back to documented defaults.

    Args:
        path: Configuration file. Defaults to `config/application.yaml`. A
            missing default file is not an error, so the sandbox runs on a
            fresh checkout; a missing explicitly requested file is an error.
    """
    explicit = path is not None
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        if explicit:
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        return AppConfig()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Could not parse {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{config_path} must contain a top-level mapping.")

    quality_data = dict(_section(raw, "pose_quality"))
    required = quality_data.get("required_landmarks")
    quality_data["required_landmarks"] = (
        tuple(required) if required else DEFAULT_REQUIRED_LANDMARKS
    )

    return AppConfig(
        camera=_build(CameraConfig, _section(raw, "camera"), "camera"),
        pose=_build(PoseConfig, _section(raw, "pose"), "pose"),
        pose_quality=_build(PoseQualityConfig, quality_data, "pose_quality"),
        recording=_build(RecordingConfig, _section(raw, "recording"), "recording"),
        log_level=str(_section(raw, "application").get("log_level", "INFO")),
    )
