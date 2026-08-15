"""Live webcam frame source (Build 0)."""

from __future__ import annotations

import time
from typing import Optional

import cv2

from src.camera.base import Frame, FrameSource, FrameSourceError, FrameSourceInfo


class WebcamFrameSource(FrameSource):
    """Captures frames from a locally attached camera via OpenCV.

    Timestamps come from `time.perf_counter` at the moment the frame is read,
    expressed as milliseconds since `start()`. A monotonic clock is required
    because wall-clock time can step backwards and would corrupt movement
    timing (Document 03 §24).

    Requested resolution and frame rate are hints. Cameras frequently supply
    something else, so `info()` reports what the device actually granted.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
        mirror: bool = True,
    ) -> None:
        """
        Args:
            device_index: OpenCV camera index.
            width: Requested capture width in pixels.
            height: Requested capture height in pixels.
            fps: Requested capture frame rate.
            mirror: Horizontally flip frames so the participant sees a mirror
                image. Applied before pose estimation, so left/right landmark
                names refer to the participant's own left and right only when
                the participant faces the camera. Recorded video and pose data
                are both mirrored consistently.
        """
        self._device_index = device_index
        self._requested_width = width
        self._requested_height = height
        self._requested_fps = fps
        self._mirror = mirror
        self._capture: Optional[cv2.VideoCapture] = None
        self._start_perf: float = 0.0
        self._index = 0

    def start(self) -> None:
        capture = cv2.VideoCapture(self._device_index)
        if not capture.isOpened():
            capture.release()
            raise FrameSourceError(
                "CAMERA_UNAVAILABLE",
                f"Could not open camera at index {self._device_index}.",
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._requested_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._requested_height)
        capture.set(cv2.CAP_PROP_FPS, self._requested_fps)
        self._capture = capture
        self._start_perf = time.perf_counter()
        self._index = 0
        self.reset_frame_rate()

    def next_frame(self) -> Optional[Frame]:
        if self._capture is None:
            raise FrameSourceError("CAMERA_UNAVAILABLE", "Camera was not started.")
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        timestamp_ms = (time.perf_counter() - self._start_perf) * 1000.0
        if self._mirror:
            image = cv2.flip(image, 1)
        frame = Frame(image=image, timestamp_ms=timestamp_ms, index=self._index)
        self._index += 1
        self.observe_frame_rate(timestamp_ms)
        return frame

    def stop(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def info(self) -> FrameSourceInfo:
        if self._capture is None:
            raise FrameSourceError("CAMERA_UNAVAILABLE", "Camera was not started.")
        reported_fps = float(self._capture.get(cv2.CAP_PROP_FPS)) or self._requested_fps
        return FrameSourceInfo(
            kind="webcam",
            description=f"webcam:{self._device_index}",
            width=int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            nominal_fps=reported_fps,
            measured_fps=self.measured_fps,
            extra={
                "device_index": self._device_index,
                "mirrored": self._mirror,
                "requested_width": self._requested_width,
                "requested_height": self._requested_height,
                "requested_fps": self._requested_fps,
            },
        )
