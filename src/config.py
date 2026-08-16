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

from src.movement.features import FeatureConfig
from src.movement.filtering import FilterSettings
from src.pose.quality import DEFAULT_REQUIRED_LANDMARKS, PoseQualityConfig

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "application.yaml"
EXERCISES_DIRECTORY = REPOSITORY_ROOT / "config" / "exercises"


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
class GestureConfig:
    """Participant-initiated start and stop signals.

    Attributes:
        start_hold_ms: How long one raised arm must be held to begin.
        stop_hold_ms: How long both raised arms must be held to finish.

            Shorter than the start hold, which is the opposite of what it
            was first set to. The reasoning behind the longer value was that
            a stop firing by accident ends the attempt, so it should demand
            more deliberation. The measurements say the deliberateness comes
            from the gesture itself, not from its duration: raising *both*
            arms is far stronger evidence of intent than raising one, and it
            qualified accidentally for 0.06 seconds across a 118 second
            session and not at all across a 77 second one.

            Meanwhile the long hold failed twice in practice. The
            participant held both arms for 1.49 seconds against a 1.50
            second threshold, then 1.00 seconds against a 1.00 second
            threshold, and each time gave up and reached for the keyboard --
            the exact thing the gesture exists to avoid.

            So the single-arm start, being the weaker signal, carries the
            longer hold.
        minimum_elbow_angle: Least elbow angle counting as a bent arm.
        maximum_elbow_angle: Greatest elbow angle counting as a bent arm.
        minimum_confidence: Least landmark confidence to judge an arm.
        settle_seconds: Pause between the start signal and the first
            measurement, to lower the arm and stand still.
    """

    start_hold_ms: float = 800.0
    stop_hold_ms: float = 600.0
    minimum_elbow_angle: float = 50.0
    maximum_elbow_angle: float = 130.0
    minimum_confidence: float = 0.60
    settle_seconds: float = 3.0

    def start_config(self) -> "ArmRaiseConfig":
        from src.movement.gestures import ArmRaiseConfig

        return ArmRaiseConfig(
            minimum_elbow_angle=self.minimum_elbow_angle,
            maximum_elbow_angle=self.maximum_elbow_angle,
            minimum_confidence=self.minimum_confidence,
            hold_ms=self.start_hold_ms,
        )

    def stop_config(self) -> "ArmRaiseConfig":
        from src.movement.gestures import ArmRaiseConfig

        return ArmRaiseConfig(
            minimum_elbow_angle=self.minimum_elbow_angle,
            maximum_elbow_angle=self.maximum_elbow_angle,
            minimum_confidence=self.minimum_confidence,
            hold_ms=self.stop_hold_ms,
        )


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
    filtering: FilterSettings = field(default_factory=FilterSettings)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)
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


def load_sts_config(path: Path | str | None = None) -> "StsConfig":
    """Load STS-001 parameters from versioned configuration.

    The YAML groups values by concern (state_machine, repetition, quality,
    calibration) for readability; `StsConfig` is flat. Mapping between them
    happens here rather than flattening the file, so the file stays legible
    to someone tuning thresholds.
    """
    from src.exercises.sit_to_stand import StsConfig

    config_path = Path(path) if path is not None else EXERCISES_DIRECTORY / "STS-001.yaml"
    if not config_path.exists():
        if path is not None:
            raise ConfigurationError(f"Exercise configuration not found: {config_path}")
        return StsConfig()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Could not parse {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{config_path} must contain a top-level mapping.")

    machine = _section(raw, "state_machine")
    repetition = _section(raw, "repetition")
    quality = _section(raw, "quality")
    calibration = _section(raw, "calibration")
    pose_quality = _section(raw, "pose_quality")

    try:
        config = StsConfig(
            target_repetitions=raw.get("target_repetitions"),
            rising_enter=float(machine.get("rising_enter", 0.25)),
            standing_enter=float(machine.get("standing_enter", 0.80)),
            standing_exit=float(machine.get("standing_exit", 0.65)),
            seated_enter=float(machine.get("seated_enter", 0.20)),
            minimum_dwell_ms=float(machine.get("minimum_dwell_ms", 100.0)),
            minimum_rise_velocity=float(machine.get("minimum_rise_velocity", 0.02)),
            minimum_rep_seconds=float(repetition.get("minimum_rep_seconds", 0.8)),
            maximum_rep_seconds=float(repetition.get("maximum_rep_seconds", 20.0)),
            rapid_descent_seconds=float(quality.get("rapid_descent_seconds", 0.20)),
            rapid_descent_ratio=float(quality.get("rapid_descent_ratio", 0.6)),
            rapid_descent_minimum_samples=int(
                quality.get("rapid_descent_minimum_samples", 3)
            ),
            calibration_minimum_travel=float(calibration.get("minimum_travel", 0.04)),
            calibration_low_percentile=float(calibration.get("low_percentile", 0.05)),
            calibration_high_percentile=float(calibration.get("high_percentile", 0.95)),
            calibration_window=int(calibration.get("window_frames", 300)),
            calibration_method=str(calibration.get("method", "cluster")),
            calibration_cluster_minimum_samples=int(
                calibration.get("cluster_minimum_samples", 30)
            ),
            calibration_refine_interval_frames=int(
                calibration.get("refine_interval_frames", 15)
            ),
            quality_recovery_frames=int(pose_quality.get("recovery_frames", 5)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid STS-001 configuration: {exc}") from exc

    try:
        config.validate()
    except ValueError as exc:
        raise ConfigurationError(f"Invalid STS-001 thresholds in {config_path}: {exc}") from exc
    return config


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
        filtering=_build(FilterSettings, _section(raw, "filtering"), "filtering"),
        features=_build(FeatureConfig, _section(raw, "features"), "features"),
        gestures=_build(GestureConfig, _section(raw, "gestures"), "gestures"),
        recording=_build(RecordingConfig, _section(raw, "recording"), "recording"),
        log_level=str(_section(raw, "application").get("log_level", "INFO")),
    )
