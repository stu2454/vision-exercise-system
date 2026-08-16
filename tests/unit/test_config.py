"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from src.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ConfigurationError,
    load_config,
)
from src.pose.quality import DEFAULT_REQUIRED_LANDMARKS


class TestDefaults:
    def test_a_missing_default_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DEFAULT_CONFIG_PATH", tmp_path / "absent.yaml")
        config = load_config()
        assert config == AppConfig()

    def test_an_explicitly_named_missing_file_is_an_error(self, tmp_path):
        with pytest.raises(ConfigurationError, match="not found"):
            load_config(tmp_path / "absent.yaml")

    def test_video_recording_is_off_by_default(self):
        assert AppConfig().recording.record_video is False


class TestShippedConfiguration:
    def test_the_repository_configuration_loads(self):
        config = load_config(DEFAULT_CONFIG_PATH)
        assert config.pose.engine == "mediapipe"
        assert config.camera.width > 0
        assert config.pose_quality.required_landmarks

    def test_the_repository_configuration_does_not_enable_video_recording(self):
        # Video capture must never be an ambient default (CLAUDE.md §28).
        assert load_config(DEFAULT_CONFIG_PATH).recording.record_video is False

    def test_the_repository_configuration_leaves_camera_view_unasserted(self):
        # Camera placement is an experimental variable, not a decided fact.
        assert load_config(DEFAULT_CONFIG_PATH).camera.view == "unspecified"


class TestParsing:
    def test_values_override_defaults(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(
            "camera:\n"
            "  device_index: 2\n"
            "  view: frontal_oblique\n"
            "pose:\n"
            "  min_tracking_confidence: 0.75\n",
            encoding="utf-8",
        )
        config = load_config(path)
        assert config.camera.device_index == 2
        assert config.camera.view == "frontal_oblique"
        assert config.pose.min_tracking_confidence == pytest.approx(0.75)
        assert config.camera.width == 1280, "unspecified values keep their defaults"

    def test_required_landmarks_become_a_tuple(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(
            "pose_quality:\n  required_landmarks:\n    - left_hip\n    - right_hip\n",
            encoding="utf-8",
        )
        assert load_config(path).pose_quality.required_landmarks == (
            "left_hip",
            "right_hip",
        )

    def test_omitted_required_landmarks_use_the_default_set(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text("pose_quality:\n  good_confidence: 0.7\n", encoding="utf-8")
        config = load_config(path)
        assert config.pose_quality.required_landmarks == DEFAULT_REQUIRED_LANDMARKS

    def test_an_unknown_key_is_rejected(self, tmp_path):
        # A silently ignored threshold is worse than a loud failure: the
        # developer would believe a parameter was in effect when it was not.
        path = tmp_path / "application.yaml"
        path.write_text("pose:\n  min_tracking_confidenc: 0.75\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="min_tracking_confidenc"):
            load_config(path)

    def test_a_non_mapping_section_is_rejected(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text("camera: 3\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="must be a mapping"):
            load_config(path)

    def test_invalid_yaml_is_reported_clearly(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text("camera: [unclosed\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Could not parse"):
            load_config(path)

    def test_an_empty_file_yields_defaults(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text("", encoding="utf-8")
        assert load_config(path) == AppConfig()


class TestCameraSource:
    def test_defaults_to_the_usb_webcam(self):
        assert AppConfig().camera.source == "webcam"

    def test_the_pi_camera_source_is_accepted(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(
            "camera:\n  source: picamera\n  picamera_format: BGR888\n", encoding="utf-8"
        )
        config = load_config(path)
        assert config.camera.source == "picamera"
        assert config.camera.picamera_format == "BGR888"

    def test_an_unknown_source_is_rejected(self, tmp_path):
        # A typo here would otherwise surface on the Pi as a camera that
        # silently opens the wrong device, or none at all.
        path = tmp_path / "application.yaml"
        path.write_text("camera:\n  source: picamera2\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Unknown camera source"):
            load_config(path)


class TestPathResolution:
    def test_model_path_resolves_against_the_repository_root(self):
        config = load_config(DEFAULT_CONFIG_PATH)
        assert config.pose.resolved_model_path().is_absolute()
        assert config.pose.resolved_model_path().name.endswith(".task")

    def test_an_absolute_model_path_is_left_alone(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(f"pose:\n  model_path: {tmp_path / 'm.task'}\n", encoding="utf-8")
        assert load_config(path).pose.resolved_model_path() == tmp_path / "m.task"


class TestGestureConfig:
    def test_the_weaker_gesture_carries_the_longer_hold(self):
        # One raised arm is weaker evidence of intent than two, so it is the
        # start that needs the longer hold. Both arms raised together
        # qualified accidentally for 0.06s across a 118 second session and
        # not at all across a 77 second one, while the long stop hold failed
        # twice in practice and sent the participant to the keyboard.
        gestures = AppConfig().gestures
        assert gestures.start_hold_ms > gestures.stop_hold_ms

    def test_the_stop_hold_is_within_what_a_person_actually_holds(self):
        # Measured twice: both arms held for 1.49s against a 1.50s
        # threshold, then 1.00s against a 1.00s threshold. Both missed.
        # Accidental qualification totalled 0.06s across 118 seconds and
        # none at all across 77 seconds, so the guard was far larger than
        # the risk.
        assert AppConfig().gestures.stop_hold_ms <= 800.0

    def test_start_and_stop_configs_differ_only_in_hold(self):
        gestures = AppConfig().gestures
        start, stop = gestures.start_config(), gestures.stop_config()
        assert start.hold_ms != stop.hold_ms
        assert start.minimum_elbow_angle == stop.minimum_elbow_angle
        assert start.minimum_confidence == stop.minimum_confidence

    def test_gesture_settings_load_from_configuration(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(
            "gestures:\n  start_hold_ms: 500.0\n  stop_hold_ms: 900.0\n",
            encoding="utf-8",
        )
        config = load_config(path)
        assert config.gestures.start_hold_ms == pytest.approx(500.0)
        assert config.gestures.start_config().hold_ms == pytest.approx(500.0)
        assert config.gestures.stop_config().hold_ms == pytest.approx(900.0)

    def test_the_shipped_configuration_keeps_the_holds_usable(self):
        gestures = load_config(DEFAULT_CONFIG_PATH).gestures
        assert 300.0 <= gestures.start_hold_ms <= 1200.0
        assert gestures.stop_hold_ms <= 800.0
        assert gestures.stop_hold_ms >= 400.0, "too short to be deliberate"
