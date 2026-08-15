"""Tests for the Raspberry Pi Camera Module frame source.

picamera2 exists only on a Raspberry Pi, so the camera object is injected.
That covers the frame handling, the mirroring and the lifecycle. What it
cannot cover is whether libcamera returns the channel order we expect, which
has to be confirmed on the hardware itself — see docs/raspberry-pi-setup.md.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pytest

from src.camera.base import FrameSourceError
from src.camera.picamera import PiCameraFrameSource

WIDTH = 320
HEIGHT = 240


class FakePicamera2:
    """Stands in for picamera2.Picamera2."""

    def __init__(self, image: Optional[np.ndarray] = None) -> None:
        self.image = image
        self.configuration: Any = None
        self.started = False
        self.stopped = False
        self.closed = False

    def create_video_configuration(self, main=None, controls=None) -> dict:
        return {"main": main, "controls": controls}

    def configure(self, configuration) -> None:
        self.configuration = configuration

    def start(self) -> None:
        self.started = True

    def capture_array(self) -> Optional[np.ndarray]:
        return self.image

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def gradient_image(channels: int = 3) -> np.ndarray:
    """An image that is not left-right symmetric, so mirroring is detectable."""
    image = np.zeros((HEIGHT, WIDTH, channels), dtype=np.uint8)
    image[:, : WIDTH // 2] = 40
    image[:, WIDTH // 2 :] = 200
    return image


def make_source(image: Optional[np.ndarray] = None, **kwargs) -> PiCameraFrameSource:
    camera = FakePicamera2(gradient_image() if image is None else image)
    kwargs.setdefault("width", WIDTH)
    kwargs.setdefault("height", HEIGHT)
    kwargs.setdefault("mirror", False)
    return PiCameraFrameSource(camera_factory=lambda: camera, **kwargs)


class TestCapture:
    def test_produces_frames_of_the_requested_shape(self):
        with make_source() as source:
            frame = source.next_frame()
        assert frame is not None
        assert frame.width == WIDTH
        assert frame.height == HEIGHT

    def test_frame_indices_increment(self):
        with make_source() as source:
            indices = [source.next_frame().index for _ in range(3)]
        assert indices == [0, 1, 2]

    def test_timestamps_increase_from_zero(self):
        with make_source() as source:
            timestamps = [source.next_frame().timestamp_ms for _ in range(3)]
        assert timestamps[0] >= 0.0
        assert timestamps == sorted(timestamps)

    def test_a_four_channel_image_is_reduced_to_three(self):
        # Some libcamera configurations deliver XRGB; the recorder and the
        # pose engine both require three channels.
        with make_source(image=gradient_image(channels=4)) as source:
            frame = source.next_frame()
        assert frame.image.shape == (HEIGHT, WIDTH, 3)

    def test_a_null_capture_ends_the_stream(self):
        camera = FakePicamera2(image=None)
        with PiCameraFrameSource(camera_factory=lambda: camera) as source:
            assert source.next_frame() is None


class TestMirroring:
    def test_mirroring_flips_the_image_horizontally(self):
        with make_source(mirror=True) as source:
            mirrored = source.next_frame().image
        with make_source(mirror=False) as source:
            plain = source.next_frame().image
        assert not np.array_equal(mirrored, plain)
        assert np.array_equal(mirrored, plain[:, ::-1, :])

    def test_frames_are_contiguous_after_mirroring(self):
        # A reversed numpy view is not contiguous, and OpenCV's video writer
        # and MediaPipe's Image both require contiguous buffers.
        with make_source(mirror=True) as source:
            frame = source.next_frame()
        assert frame.image.flags["C_CONTIGUOUS"]


class TestConfiguration:
    def test_requested_size_format_and_rate_reach_the_camera(self):
        camera = FakePicamera2(gradient_image())
        source = PiCameraFrameSource(
            width=640,
            height=480,
            fps=24.0,
            picamera_format="BGR888",
            camera_factory=lambda: camera,
        )
        with source:
            pass
        assert camera.configuration["main"]["size"] == (640, 480)
        assert camera.configuration["main"]["format"] == "BGR888"
        assert camera.configuration["controls"]["FrameRate"] == 24.0

    def test_info_describes_the_source_for_recording_metadata(self):
        with make_source(mirror=True) as source:
            info = source.info()
        assert info.kind == "picamera"
        assert info.width == WIDTH
        assert info.extra["mirrored"] is True
        assert info.extra["picamera_format"] == "RGB888"


class TestLifecycle:
    def test_stop_releases_the_camera(self):
        camera = FakePicamera2(gradient_image())
        source = PiCameraFrameSource(camera_factory=lambda: camera)
        source.start()
        source.stop()
        assert camera.stopped and camera.closed

    def test_stop_is_idempotent(self):
        source = make_source()
        source.start()
        source.stop()
        source.stop()

    def test_capture_before_start_is_a_coded_error(self):
        source = make_source()
        with pytest.raises(FrameSourceError) as exc_info:
            source.next_frame()
        assert exc_info.value.code == "CAMERA_UNAVAILABLE"

    def test_info_before_start_is_a_coded_error(self):
        source = make_source()
        with pytest.raises(FrameSourceError) as exc_info:
            source.info()
        assert exc_info.value.code == "CAMERA_UNAVAILABLE"

    def test_a_camera_failure_during_start_is_wrapped(self):
        class BrokenCamera(FakePicamera2):
            def start(self) -> None:
                raise RuntimeError("libcamera pipeline busy")

        source = PiCameraFrameSource(camera_factory=lambda: BrokenCamera(None))
        with pytest.raises(FrameSourceError, match="Could not start"):
            source.start()


class TestWithoutPicamera2:
    def test_a_missing_picamera2_explains_how_to_install_it(self):
        # This runs the real import path. On any machine without picamera2 —
        # every development machine — it must fail with guidance rather than
        # a bare ImportError.
        pytest.importorskip
        try:
            import picamera2  # noqa: F401
        except ImportError:
            pass
        else:  # pragma: no cover - only on a Raspberry Pi
            pytest.skip("picamera2 is installed on this machine")

        source = PiCameraFrameSource()
        with pytest.raises(FrameSourceError) as exc_info:
            source.start()
        assert exc_info.value.code == "CAMERA_UNAVAILABLE"
        assert "system-site-packages" in str(exc_info.value)
