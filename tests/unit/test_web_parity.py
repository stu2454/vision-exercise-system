"""The browser sandbox must agree with the Python implementation.

`web/canonical.js` restates the canonical landmark names, the MediaPipe index
map and the synthetic midpoints in JavaScript. Two implementations of one
definition drift, and if they do, a browser recording and a Python recording of
the same movement would give different results for reasons having nothing to do
with the movement.

These tests read the JavaScript as text and compare it with the Python source
of truth, so the drift is caught here rather than discovered in a comparison
that quietly means nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.pose.adapters.mediapipe_adapter import MEDIAPIPE_LANDMARK_MAP
from src.pose.models import MEASURED_LANDMARKS, PoseFrame
from src.recording.pose_recorder import PoseStreamMetadata
from src.replay.pose_replay import read_pose_stream
from src.version import APPLICATION_VERSION, POSE_STREAM_FORMAT_VERSION

WEB = Path(__file__).resolve().parents[2] / "web"

pytestmark = pytest.mark.skipif(
    not WEB.exists(), reason="browser sandbox not present"
)


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def js_landmark_map() -> dict[int, str]:
    """Extract MEDIAPIPE_LANDMARK_MAP from the JavaScript."""
    source = read("canonical.js")
    block = re.search(
        r"export const MEDIAPIPE_LANDMARK_MAP = \{(.*?)\n\};", source, re.S
    )
    assert block, "MEDIAPIPE_LANDMARK_MAP not found in canonical.js"
    constants = dict(
        re.findall(r'export const (\w+) = "([\w_]+)";', source)
    )
    mapping: dict[int, str] = {}
    for index, name in re.findall(r"(\d+):\s*([A-Z_]+)", block.group(1)):
        assert name in constants, f"{name} is used but not defined in canonical.js"
        mapping[int(index)] = constants[name]
    return mapping


class TestLandmarkMapParity:
    def test_the_index_map_matches_python_exactly(self):
        assert js_landmark_map() == MEDIAPIPE_LANDMARK_MAP

    def test_every_measured_landmark_is_named_in_the_javascript(self):
        source = read("canonical.js")
        names = set(re.findall(r'export const \w+ = "([\w_]+)";', source))
        assert set(MEASURED_LANDMARKS) <= names

    def test_the_javascript_declares_the_same_measured_set(self):
        source = read("canonical.js")
        block = re.search(
            r"export const MEASURED_LANDMARKS = \[(.*?)\n\];", source, re.S
        )
        assert block
        constants = dict(re.findall(r'export const (\w+) = "([\w_]+)";', source))
        declared = {
            constants[token]
            for token in re.findall(r"\b([A-Z][A-Z_]+)\b", block.group(1))
            if token in constants
        }
        assert declared == set(MEASURED_LANDMARKS)


class TestVersionParity:
    def test_application_version_matches(self):
        source = read("version.js")
        found = re.search(r'APPLICATION_VERSION = "([^"]+)"', source)
        assert found and found.group(1) == APPLICATION_VERSION

    def test_pose_stream_format_version_matches(self):
        # A browser recording claiming a different format version could not be
        # treated the same way by the reader.
        source = read("version.js")
        found = re.search(r'POSE_STREAM_FORMAT_VERSION = "([^"]+)"', source)
        assert found and found.group(1) == POSE_STREAM_FORMAT_VERSION


class TestRecordingInteroperability:
    """A browser-shaped recording must be readable by the Python reader."""

    @staticmethod
    def browser_jsonl() -> str:
        """The exact shape web/recorder.js produces."""
        metadata = {
            "record": "metadata",
            "recording_id": "web_20260817_101500",
            "recording_date": "2026-08-17T10:15:00.000Z",
            "application_version": APPLICATION_VERSION,
            "pose_engine": "mediapipe_tasks_vision",
            "pose_model_version": "pose_landmarker_lite.task",
            "pose_engine_detail": "Mozilla/5.0 …",
            "camera_view": "frontal",
            "nominal_resolution": "1280x720",
            "nominal_fps": 29.7,
            "measured_fps": 29.7,
            "source": {
                "kind": "browser_camera",
                "description": "browser:getUserMedia",
                "width": 1280,
                "height": 720,
                "measured_fps": 29.7,
                "effective_fps": 29.7,
            },
            "format_version": POSE_STREAM_FORMAT_VERSION,
            "notes": "",
        }
        lines = [json.dumps(metadata)]
        for index in range(5):
            pose = {
                "timestamp_ms": index * 33.6,
                "person_confidence": 0.91,
                "source": "mediapipe_tasks_vision:browser",
                "frame_index": index,
                "image_width": 1280,
                "image_height": 720,
                "landmarks": {
                    "left_hip": {
                        "x": 0.47, "y": 0.55, "z": -0.1, "confidence": 0.95,
                    },
                    "right_hip": {
                        "x": 0.53, "y": 0.55, "z": None, "confidence": 0.93,
                    },
                },
            }
            lines.append(json.dumps({"record": "frame", "pose": pose}))
        return "\n".join(lines) + "\n"

    def test_the_python_reader_accepts_a_browser_recording(self, tmp_path):
        path = tmp_path / "web_20260817_101500.jsonl"
        path.write_text(self.browser_jsonl(), encoding="utf-8")
        metadata, records = read_pose_stream(path)
        assert isinstance(metadata, PoseStreamMetadata)
        assert len(records) == 5
        assert all(isinstance(r.pose, PoseFrame) for r in records)

    def test_the_engine_is_distinguishable_from_the_python_one(self):
        # Comparing runtimes is the point, so a recording must say which
        # produced it.
        metadata, _ = self._read(self.browser_jsonl())
        assert metadata.pose_engine == "mediapipe_tasks_vision"
        assert metadata.pose_model_version == "pose_landmarker_lite.task"

    def test_the_measured_frame_rate_survives(self):
        metadata, _ = self._read(self.browser_jsonl())
        assert metadata.measured_fps == pytest.approx(29.7)
        assert metadata.effective_fps == pytest.approx(29.7)

    def test_landmarks_and_missing_depth_survive(self):
        _, records = self._read(self.browser_jsonl())
        pose = records[0].pose
        assert pose.get("left_hip").z == pytest.approx(-0.1)
        assert pose.get("right_hip").z is None
        assert pose.person_confidence == pytest.approx(0.91)

    @staticmethod
    def _read(text: str):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r.jsonl"
            path.write_text(text, encoding="utf-8")
            return read_pose_stream(path)


class TestScope:
    """The browser may display the engine's output, never compute it.

    Document 03 §7 and ADR-010: do not build both implementations while the
    movement model is still changing. Consuming a `rep_completed` event from
    the Python scorer is fine; deciding when one has occurred is not.

    The markers are the STS threshold names. Anyone porting the state machine
    or its calibration has to bring these with them, so their absence is a
    reliable sign the logic still lives in one place.
    """

    IMPLEMENTATION_MARKERS = (
        "rising_enter", "risingEnter",
        "standing_enter", "standingEnter",
        "standing_exit", "standingExit",
        "seated_enter", "seatedEnter",
        "minimum_dwell_ms", "minimumDwellMs",
        "seated_hip_height", "seatedHipHeight",
        "standing_hip_height", "standingHipHeight",
        "rapid_descent_ratio", "rapidDescentRatio",
    )

    def test_the_browser_does_not_implement_the_exercise_engine(self):
        for file in WEB.glob("*.js"):
            source = file.read_text(encoding="utf-8")
            for marker in self.IMPLEMENTATION_MARKERS:
                assert marker not in source, (
                    f"{file.name} contains {marker}; the browser is "
                    "reimplementing the exercise engine rather than "
                    "displaying its output"
                )

    def test_the_browser_delegates_scoring_to_python(self):
        # The positive half: it must actually be asking the scorer.
        bridge = read("bridge.js")
        assert "/api/frames" in bridge
        assert "/api/session" in bridge

    def test_no_movement_feature_is_computed_in_the_browser(self):
        # Filtering and features stay in Python too. Gesture geometry is the
        # deliberate exception, and is limited to elbow angle.
        for name in ("hip_height", "hipHeight", "ExponentialMovingAverage",
                     "hip_vertical_velocity", "stance_width"):
            for file in WEB.glob("*.js"):
                assert name not in file.read_text(encoding="utf-8"), (
                    f"{file.name} computes {name}; features belong in Python"
                )


class TestGestureParity:
    """The two runtimes must accept the same arm positions.

    If the browser's elbow range or hold durations differed from Python's, a
    participant would find the gesture working in one and not the other, and a
    recording made in one would not be comparable with a recording made in the
    other.
    """

    @staticmethod
    def js_gesture_defaults() -> dict[str, float]:
        source = read("gestures.js")
        block = re.search(
            r"export const GESTURE_DEFAULTS = \{(.*?)\n\};", source, re.S
        )
        assert block, "GESTURE_DEFAULTS not found in gestures.js"
        return {
            key: float(value)
            for key, value in re.findall(
                r"(\w+):\s*([\d.]+)", block.group(1)
            )
        }

    def test_the_elbow_range_matches(self):
        from src.movement.gestures import ArmRaiseConfig

        js = self.js_gesture_defaults()
        python = ArmRaiseConfig()
        assert js["minimumElbowAngle"] == pytest.approx(python.minimum_elbow_angle)
        assert js["maximumElbowAngle"] == pytest.approx(python.maximum_elbow_angle)

    def test_the_confidence_floor_matches(self):
        from src.movement.gestures import ArmRaiseConfig

        assert self.js_gesture_defaults()["minimumConfidence"] == pytest.approx(
            ArmRaiseConfig().minimum_confidence
        )

    def test_the_hold_durations_match(self):
        from src.config import AppConfig

        js = self.js_gesture_defaults()
        gestures = AppConfig().gestures
        assert js["startHoldMs"] == pytest.approx(gestures.start_hold_ms)
        assert js["stopHoldMs"] == pytest.approx(gestures.stop_hold_ms)
        assert js["settleSeconds"] == pytest.approx(gestures.settle_seconds)

    def test_the_weaker_gesture_still_carries_the_longer_hold(self):
        js = self.js_gesture_defaults()
        assert js["startHoldMs"] > js["stopHoldMs"]

    def test_the_browser_corrects_for_aspect_ratio(self):
        # The elbow angle must be computed in isotropic space. Without the
        # correction the browser would accept different arm positions from
        # Python — the error made twice already in this project.
        assert "aspectRatio" in read("geometry.js")
        assert "aspectRatio" in read("gestures.js")
        assert "DEFAULT_ASPECT = 16 / 9" in read("geometry.js")

    def test_the_start_gesture_waits_for_the_arms_to_come_down(self):
        # Both arms raised also satisfies the one-arm start condition, so
        # without a release guard finishing a recording immediately grants
        # itself a start and a new one begins by itself.
        gestures = read("gestures.js")
        assert "requireRelease" in gestures
        assert "blocked" in gestures
        assert "armGestures(true)" in read("app.js")

    def test_both_arms_are_required_to_stop(self):
        source = read("gestures.js")
        assert "requiredArms" in source
        assert 'new ArmRaiseDetector({}, 2)' in read("app.js")
