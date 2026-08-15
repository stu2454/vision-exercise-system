"""Raspberry Pi Camera Module frame source.

CSI cameras on Raspberry Pi OS Bookworm are driven by libcamera, not by V4L2
in a way `cv2.VideoCapture` can use. Opening index 0 with OpenCV on a Pi with
only a CSI camera attached fails, so the Pi Camera Module needs its own
FrameSource implementation.

This is exactly the substitution the frame-source abstraction exists for
(Document 03 §8): nothing above the camera layer changes, because everything
downstream consumes `Frame`.

`picamera2` is imported lazily inside `start()`. It only exists on a Pi, and
importing it at module scope would break every development machine.

Installing picamera2
--------------------
`picamera2` is not pip-installable in a normal virtual environment: it depends
on the libcamera Python bindings, which are built against the system libraries
and distributed only as Debian packages. On Pi OS Bookworm:

    sudo apt install -y python3-picamera2
    python -m venv --system-site-packages .venv

The `--system-site-packages` flag is required, or the venv cannot see
picamera2. See docs/raspberry-pi-setup.md.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

import numpy as np

from src.camera.base import Frame, FrameSource, FrameSourceError, FrameSourceInfo

DEFAULT_PICAMERA_FORMAT = "RGB888"
"""libcamera stream format requested from picamera2.

Despite the name, picamera2's ``RGB888`` delivers channels in blue-green-red
order in the resulting array, which is what OpenCV and therefore `Frame`
expect. ``BGR888`` delivers red-green-blue. The naming describes libcamera's
byte layout rather than the numpy channel order, and the two are reversed.

If captured images look colour-swapped — skin tones appearing blue — set
`camera.picamera_format` to ``BGR888`` in configuration. Pose estimation
degrades on swapped channels rather than failing outright, so this is worth
checking deliberately rather than assuming.
"""


class PiCameraFrameSource(FrameSource):
    """Captures frames from a Raspberry Pi Camera Module via picamera2.

    Timestamps come from `time.perf_counter` at the moment of capture,
    matching `WebcamFrameSource`, so live recordings from either camera carry
    the same kind of monotonic timing (Document 03 §24).

    Args:
        width: Requested capture width in pixels.
        height: Requested capture height in pixels.
        fps: Requested capture frame rate.
        mirror: Horizontally flip frames so the participant sees a mirror
            image, applied before pose estimation, as for the webcam source.
        picamera_format: libcamera stream format; see DEFAULT_PICAMERA_FORMAT.
        camera_factory: Injection point used by tests to supply a stand-in
            camera. Production code leaves this as None so that picamera2 is
            imported lazily.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
        mirror: bool = True,
        picamera_format: str = DEFAULT_PICAMERA_FORMAT,
        camera_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._width = width
        self._height = height
        self._fps = fps
        self._mirror = mirror
        self._format = picamera_format
        self._camera_factory = camera_factory
        self._camera: Any = None
        self._start_perf = 0.0
        self._index = 0

    def start(self) -> None:
        self._camera = self._create_camera()
        try:
            configuration = self._camera.create_video_configuration(
                main={"size": (self._width, self._height), "format": self._format},
                controls={"FrameRate": self._fps},
            )
            self._camera.configure(configuration)
            self._camera.start()
        except Exception as exc:
            self._release()
            raise FrameSourceError(
                "CAMERA_UNAVAILABLE", f"Could not start the Pi camera: {exc}"
            ) from exc
        self._start_perf = time.perf_counter()
        self._index = 0
        self.reset_frame_rate()

    def _create_camera(self) -> Any:
        if self._camera_factory is not None:
            return self._camera_factory()
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise FrameSourceError(
                "CAMERA_UNAVAILABLE",
                "picamera2 is not available. On Raspberry Pi OS install it with "
                "'sudo apt install -y python3-picamera2' and create the virtual "
                "environment with --system-site-packages. See "
                "docs/raspberry-pi-setup.md.",
            ) from exc
        try:
            return Picamera2()
        except Exception as exc:
            raise FrameSourceError(
                "CAMERA_UNAVAILABLE", f"Could not open the Pi camera: {exc}"
            ) from exc

    def next_frame(self) -> Optional[Frame]:
        if self._camera is None:
            raise FrameSourceError("CAMERA_UNAVAILABLE", "Pi camera was not started.")
        try:
            image = self._camera.capture_array()
        except Exception as exc:
            raise FrameSourceError(
                "CAMERA_UNAVAILABLE", f"Pi camera capture failed: {exc}"
            ) from exc
        if image is None:
            return None

        timestamp_ms = (time.perf_counter() - self._start_perf) * 1000.0
        image = self._to_three_channel(image)
        if self._mirror:
            image = image[:, ::-1, :]
        frame = Frame(
            image=np.ascontiguousarray(image),
            timestamp_ms=timestamp_ms,
            index=self._index,
        )
        self._index += 1
        self.observe_frame_rate(timestamp_ms)
        return frame

    @staticmethod
    def _to_three_channel(image: np.ndarray) -> np.ndarray:
        """Drop the alpha channel that XRGB formats include.

        Some libcamera configurations deliver four channels. The pose engine
        and the video recorder both expect three, so the extra channel is
        removed here rather than surprising them.
        """
        if image.ndim == 3 and image.shape[2] == 4:
            return image[:, :, :3]
        return image

    def stop(self) -> None:
        self._release()

    def _release(self) -> None:
        if self._camera is None:
            return
        camera, self._camera = self._camera, None
        for method in ("stop", "close"):
            action = getattr(camera, method, None)
            if action is None:
                continue
            try:
                action()
            except Exception:  # pragma: no cover - best-effort teardown
                # A camera that cannot be closed cleanly must not mask the
                # error that caused shutdown in the first place.
                pass

    def info(self) -> FrameSourceInfo:
        if self._camera is None:
            raise FrameSourceError("CAMERA_UNAVAILABLE", "Pi camera was not started.")
        return FrameSourceInfo(
            kind="picamera",
            description="picamera:csi",
            width=self._width,
            height=self._height,
            nominal_fps=self._fps,
            measured_fps=self.measured_fps,
            extra={
                "mirrored": self._mirror,
                "picamera_format": self._format,
            },
        )
