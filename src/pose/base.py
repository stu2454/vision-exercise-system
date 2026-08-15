"""Pose-engine abstraction.

A pose engine turns a `Frame` into a canonical `PoseFrame`. Which engine is in
use (MediaPipe, MoveNet, a depth camera, a future embedded platform) must not
be observable above this layer (Document 03 §2.2, §11.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.camera.base import Frame
from src.pose.models import PoseFrame


class PoseEngineError(RuntimeError):
    """Raised when a pose engine cannot be created or fails during inference."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PoseEngineInfo:
    """Identifies the engine and model that produced a pose stream.

    Persisted with every recording and session so that measurements can be
    traced to the software that produced them (Document 03 §2.5).
    """

    engine: str
    model_version: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "pose_engine": self.engine,
            "pose_model_version": self.model_version,
            "pose_engine_detail": self.detail,
        }


class PoseEngine(ABC):
    """Estimates canonical pose from images."""

    @abstractmethod
    def start(self) -> None:
        """Load the model. Raises PoseEngineError."""

    @abstractmethod
    def estimate(self, frame: Frame, source: str) -> PoseFrame:
        """Return the canonical pose for `frame`.

        Must always return a PoseFrame. When no person is detected the frame
        carries no landmarks and a person_confidence of 0.0, so that the
        output stream stays aligned with the input stream.

        Args:
            frame: The image to analyse.
            source: Provenance string recorded on the resulting PoseFrame.
        """

    @abstractmethod
    def close(self) -> None:
        """Release model resources. Safe to call more than once."""

    @abstractmethod
    def info(self) -> PoseEngineInfo:
        """Identify this engine and its model."""

    @property
    def last_inference_ms(self) -> Optional[float]:
        """Wall time of the most recent inference call, for developer display."""
        return None

    def __enter__(self) -> "PoseEngine":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
