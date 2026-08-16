"""Tests for the recording inspection tool's segment logic.

Finding the scorable parts of a take is deterministic logic that algorithm
work will depend on, so it is tested rather than eyeballed. A take where the
participant walks to and from the camera is mostly unscorable, and picking the
wrong window would silently change every downstream measurement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from inspect_recording import find_segments, timeline  # noqa: E402

from src.pose.models import Landmark, PoseFrame  # noqa: E402
from src.replay.pose_replay import PoseStreamRecord  # noqa: E402

FPS = 30.0


def make_records(statuses: list[str], start_s: float = 0.0) -> list[PoseStreamRecord]:
    """One record per status, spaced at 30 fps from `start_s`."""
    records = []
    for index, status in enumerate(statuses):
        pose = PoseFrame(
            timestamp_ms=(start_s + index / FPS) * 1000.0,
            person_confidence=0.9,
            landmarks={"hip_centre": Landmark(0.5, 0.5, 0.0, 0.9)},
            source="test",
            frame_index=index,
        )
        records.append(PoseStreamRecord(pose=pose, recorded_quality={"status": status}))
    return records


def statuses(good: int = 0, degraded: int = 0, insufficient: int = 0) -> list[str]:
    return ["GOOD"] * good + ["DEGRADED"] * degraded + ["INSUFFICIENT"] * insufficient


class TestFindSegments:
    def test_a_wholly_good_take_is_one_segment(self):
        segments = find_segments(make_records(statuses(good=300)), minimum_s=1.0)
        assert len(segments) == 1
        assert segments[0].frames == 300

    def test_a_wholly_unusable_take_has_no_segments(self):
        assert find_segments(make_records(statuses(insufficient=300))) == []

    def test_degraded_frames_count_as_scorable(self):
        # DEGRADED means metrics may be unreliable, not that scoring stops.
        segments = find_segments(make_records(statuses(degraded=300)), minimum_s=1.0)
        assert len(segments) == 1

    def test_insufficient_frames_split_a_take(self):
        records = make_records(
            statuses(good=120) + statuses(insufficient=120) + statuses(good=120)
        )
        segments = find_segments(records, minimum_s=1.0)
        assert len(segments) == 2
        assert [s.frames for s in segments] == [120, 120]

    def test_short_segments_are_discarded(self):
        # Two seconds of visibility between two absences is not a usable take.
        records = make_records(
            statuses(good=15) + statuses(insufficient=60) + statuses(good=120)
        )
        segments = find_segments(records, minimum_s=2.0)
        assert len(segments) == 1
        assert segments[0].frames == 120

    def test_a_segment_running_to_the_end_is_closed(self):
        records = make_records(statuses(insufficient=60) + statuses(good=120))
        segments = find_segments(records, minimum_s=1.0)
        assert len(segments) == 1
        assert segments[0].frames == 120

    def test_timestamps_are_absolute_not_relative_to_the_segment(self):
        # Recordings begin at camera start, so a take can start well after 0.
        records = make_records(statuses(good=120), start_s=36.1)
        segment = find_segments(records, minimum_s=1.0)[0]
        assert segment.start_s == pytest.approx(36.1)
        assert segment.duration_s == pytest.approx(119 / FPS, abs=0.01)

    def test_a_missing_quality_record_is_treated_as_scorable(self):
        # Format 0.1 recordings may carry no quality verdict.
        records = make_records(statuses(good=120))
        bare = [PoseStreamRecord(pose=r.pose, recorded_quality=None) for r in records]
        assert len(find_segments(bare, minimum_s=1.0)) == 1


class TestTimeline:
    def test_one_character_per_second_labelled_from_the_real_start(self):
        records = make_records(statuses(good=300), start_s=34.0)
        lines = timeline(records, width=60)
        assert lines[0].startswith("    34s |")
        assert lines[0].count("#") == 10

    def test_a_second_takes_its_worst_frame(self):
        # 29 good frames and one lost frame within a second must not read as
        # a clean second.
        records = make_records(statuses(good=29) + statuses(insufficient=1))
        assert timeline(records)[0].endswith(".")

    def test_degraded_shows_between_good_and_insufficient(self):
        records = make_records(statuses(good=29) + statuses(degraded=1))
        assert timeline(records)[0].endswith("-")
