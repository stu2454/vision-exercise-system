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


class TestPathResolution:
    def test_model_path_resolves_against_the_repository_root(self):
        config = load_config(DEFAULT_CONFIG_PATH)
        assert config.pose.resolved_model_path().is_absolute()
        assert config.pose.resolved_model_path().name.endswith(".task")

    def test_an_absolute_model_path_is_left_alone(self, tmp_path):
        path = tmp_path / "application.yaml"
        path.write_text(f"pose:\n  model_path: {tmp_path / 'm.task'}\n", encoding="utf-8")
        assert load_config(path).pose.resolved_model_path() == tmp_path / "m.task"
