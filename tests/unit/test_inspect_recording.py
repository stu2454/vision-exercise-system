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

from inspect_recording import find_segments, resolve_statuses, timeline  # noqa: E402

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


def segments_of(records, minimum_s: float = 2.0):
    """Segments, resolving quality the way the tool does."""
    return find_segments(records, resolve_statuses(records)[0], minimum_s=minimum_s)


class TestFindSegments:
    def test_a_wholly_good_take_is_one_segment(self):
        segments = segments_of(make_records(statuses(good=300)), minimum_s=1.0)
        assert len(segments) == 1
        assert segments[0].frames == 300

    def test_a_wholly_unusable_take_has_no_segments(self):
        assert segments_of(make_records(statuses(insufficient=300))) == []

    def test_degraded_frames_count_as_scorable(self):
        # DEGRADED means metrics may be unreliable, not that scoring stops.
        segments = segments_of(make_records(statuses(degraded=300)), minimum_s=1.0)
        assert len(segments) == 1

    def test_insufficient_frames_split_a_take(self):
        records = make_records(
            statuses(good=120) + statuses(insufficient=120) + statuses(good=120)
        )
        segments = segments_of(records, minimum_s=1.0)
        assert len(segments) == 2
        assert [s.frames for s in segments] == [120, 120]

    def test_short_segments_are_discarded(self):
        # Two seconds of visibility between two absences is not a usable take.
        records = make_records(
            statuses(good=15) + statuses(insufficient=60) + statuses(good=120)
        )
        segments = segments_of(records, minimum_s=2.0)
        assert len(segments) == 1
        assert segments[0].frames == 120

    def test_a_segment_running_to_the_end_is_closed(self):
        records = make_records(statuses(insufficient=60) + statuses(good=120))
        segments = segments_of(records, minimum_s=1.0)
        assert len(segments) == 1
        assert segments[0].frames == 120

    def test_timestamps_are_absolute_not_relative_to_the_segment(self):
        # Recordings begin at camera start, so a take can start well after 0.
        records = make_records(statuses(good=120), start_s=36.1)
        segment = segments_of(records, minimum_s=1.0)[0]
        assert segment.start_s == pytest.approx(36.1)
        assert segment.duration_s == pytest.approx(119 / FPS, abs=0.01)

    def test_quality_is_recomputed_when_the_recording_does_not_carry_it(self):
        # Browser recordings store no per-frame quality, because the quality
        # layer lives in Python. Reporting zeros for such a stream made it
        # look as though every frame had failed when nothing had been stored.
        records = make_records(statuses(good=120))
        bare = [PoseStreamRecord(pose=r.pose, recorded_quality=None) for r in records]
        resolved, recorded = resolve_statuses(bare)
        assert recorded is False, "must report that it recomputed"
        assert len(resolved) == len(bare)

    def test_recorded_quality_is_used_when_present(self):
        records = make_records(statuses(good=120))
        resolved, recorded = resolve_statuses(records)
        assert recorded is True
        assert set(resolved) == {"GOOD"}


class TestTimeline:
    def test_one_character_per_second_labelled_from_the_real_start(self):
        records = make_records(statuses(good=300), start_s=34.0)
        lines = timeline(records, resolve_statuses(records)[0], width=60)
        assert lines[0].startswith("    34s |")
        assert lines[0].count("#") == 10

    def test_a_second_takes_its_worst_frame(self):
        # 29 good frames and one lost frame within a second must not read as
        # a clean second.
        records = make_records(statuses(good=29) + statuses(insufficient=1))
        assert timeline(records, resolve_statuses(records)[0])[0].endswith(".")

    def test_degraded_shows_between_good_and_insufficient(self):
        records = make_records(statuses(good=29) + statuses(degraded=1))
        assert timeline(records, resolve_statuses(records)[0])[0].endswith("-")
