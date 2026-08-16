"""Summarise a recorded canonical pose stream.

Answers the questions that matter before a recording is used for algorithm
work: is the participant in frame, how much of the take is scorable, and where
are the usable segments?

    python tools/inspect_recording.py recordings/dev_20260816_100337.jsonl

Timestamps are relative to camera start, not to when recording began, so a
take started part-way through a session does not begin at zero. Everything
here is labelled with real timestamps for that reason.

This reports what the pose data contains. It does not score exercises — that
is the exercise engine's job from Build 5 onwards.
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pose.models import HIP_CENTRE, PoseFrame  # noqa: E402
from src.replay.pose_replay import PoseStreamRecord, read_pose_stream  # noqa: E402

SCORABLE = ("GOOD", "DEGRADED")


@dataclass
class Segment:
    """A contiguous run of scorable frames."""

    start_s: float
    end_s: float
    frames: int

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def find_segments(
    records: list[PoseStreamRecord], minimum_s: float = 2.0
) -> list[Segment]:
    """Contiguous runs where pose quality permits scoring."""
    segments: list[Segment] = []
    start_index: Optional[int] = None
    for index, record in enumerate(records):
        scorable = record.recorded_quality is None or (
            record.recorded_quality.get("status") in SCORABLE
        )
        if scorable and start_index is None:
            start_index = index
        elif not scorable and start_index is not None:
            segments.append(_segment(records, start_index, index - 1))
            start_index = None
    if start_index is not None:
        segments.append(_segment(records, start_index, len(records) - 1))
    return [s for s in segments if s.duration_s >= minimum_s]


def _segment(records: list[PoseStreamRecord], first: int, last: int) -> Segment:
    return Segment(
        start_s=records[first].pose.timestamp_ms / 1000.0,
        end_s=records[last].pose.timestamp_ms / 1000.0,
        frames=last - first + 1,
    )


def timeline(records: list[PoseStreamRecord], width: int = 60) -> list[str]:
    """One character per second, labelled with real timestamps.

    A second counts as its worst frame, so the chart never suggests a second
    was clean when part of it was not.
    """
    buckets: dict[int, list[str]] = {}
    for record in records:
        second = int(record.pose.timestamp_ms // 1000)
        status = (record.recorded_quality or {}).get("status", "GOOD")
        buckets.setdefault(second, []).append(status)
    if not buckets:
        return []
    first, last = min(buckets), max(buckets)
    marks = []
    for second in range(first, last + 1):
        statuses = buckets.get(second)
        if not statuses:
            marks.append(" ")  # no frames recorded for this second
        elif "INSUFFICIENT" in statuses:
            marks.append(".")
        elif "DEGRADED" in statuses:
            marks.append("-")
        else:
            marks.append("#")
    lines = []
    for offset in range(0, len(marks), width):
        chunk = "".join(marks[offset : offset + width])
        lines.append(f"  {first + offset:4d}s |{chunk}")
    return lines


def framing(poses: list[PoseFrame]) -> list[str]:
    """How much of the body stayed inside the image."""
    rows = []
    for name in (
        "nose",
        "shoulder_centre",
        HIP_CENTRE,
        "left_knee",
        "left_ankle",
        "left_foot",
    ):
        ys = [p.landmarks[name].y for p in poses if name in p.landmarks]
        cs = [p.landmarks[name].confidence for p in poses if name in p.landmarks]
        if not ys:
            continue
        below = 100.0 * sum(1 for y in ys if y > 1.0) / len(ys)
        above = 100.0 * sum(1 for y in ys if y < 0.0) / len(ys)
        rows.append(
            f"  {name:16} y median {statistics.median(ys):5.2f}   "
            f"confidence {statistics.median(cs):4.2f}   "
            f"off-frame below {below:3.0f}%  above {above:3.0f}%"
        )
    return rows


def hip_trace(poses: list[PoseFrame], rows: int = 12, width: int = 100) -> list[str]:
    """Sparkline of hip height, the primary sit-to-stand signal."""
    ys = [
        p.landmarks[HIP_CENTRE].y for p in poses if HIP_CENTRE in p.landmarks
    ]
    if len(ys) < 10:
        return ["  (too few hip observations to plot)"]
    low, high = min(ys), max(ys)
    if high - low < 1e-6:
        return ["  (hip height did not vary)"]
    step = max(1, len(ys) // width)
    columns = ys[::step][:width]
    grid = [[" "] * len(columns) for _ in range(rows)]
    for x, y in enumerate(columns):
        # y increases downwards in image coordinates, so invert for display
        row = int((y - low) / (high - low) * (rows - 1))
        grid[row][x] = "*"
    out = ["  STANDING (hip high in body terms, low y)"]
    out += ["  |" + "".join(r) for r in grid]
    out.append("  SEATED")
    out.append(f"  hip y range {high - low:.3f} normalised units")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Pose stream (.jsonl).")
    parser.add_argument(
        "--min-segment",
        type=float,
        default=2.0,
        help="Shortest scorable run to report, in seconds.",
    )
    parser.add_argument(
        "--segment",
        type=int,
        default=None,
        help="Plot hip height for this segment number instead of the whole take.",
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"Pose stream not found: {args.path}", file=sys.stderr)
        return 1
    metadata, records = read_pose_stream(args.path)
    if not records:
        print("Recording contains no frames.", file=sys.stderr)
        return 1

    timestamps = [r.pose.timestamp_ms / 1000.0 for r in records]
    duration = timestamps[-1] - timestamps[0]
    true_fps = (len(records) - 1) / duration if duration > 0 else 0.0

    print(f"Recording      {metadata.recording_id}   format {metadata.format_version}")
    print(f"  engine       {metadata.pose_engine}  {metadata.pose_model_version}")
    print(f"  camera view  {metadata.camera_view}", end="")
    if metadata.camera_view == "unspecified":
        print("   <- set --camera-view; needed to compare views later")
    else:
        print()
    print(f"  resolution   {metadata.nominal_resolution}")
    claimed = metadata.nominal_fps
    measured = metadata.measured_fps
    print(
        f"  frame rate   claimed {claimed:.1f}"
        + (f"   measured {measured:.2f}" if measured else "   measured n/a (format 0.1)")
        + f"   actual in stream {true_fps:.2f}"
    )
    print(f"  frames       {len(records)}   duration {duration:.1f}s")
    print(f"  spans        {timestamps[0]:.1f}s -> {timestamps[-1]:.1f}s from camera start")

    counts = collections.Counter(
        (r.recorded_quality or {}).get("status", "UNKNOWN") for r in records
    )
    print("\nPose quality")
    for status in ("GOOD", "DEGRADED", "INSUFFICIENT"):
        n = counts.get(status, 0)
        print(f"  {status:14} {n:5d}  {100.0 * n / len(records):4.0f}%")
    scorable = counts.get("GOOD", 0) + counts.get("DEGRADED", 0)
    print(f"  scorable       {scorable:5d}  {100.0 * scorable / len(records):4.0f}%")

    reasons: collections.Counter = collections.Counter()
    problems: collections.Counter = collections.Counter()
    for record in records:
        quality = record.recorded_quality or {}
        for reason in quality.get("reasons", []):
            reasons[reason] += 1
        for key in ("missing_required", "low_confidence", "clipped"):
            for name in quality.get(key, []):
                problems[f"{name} ({key.replace('_', ' ')})"] += 1
    if problems:
        print("\nMost affected landmarks")
        for name, n in problems.most_common(6):
            print(f"  {name:40} {n:5d}  {100.0 * n / len(records):3.0f}%")

    print("\nQuality over time   ( # GOOD   - DEGRADED   . INSUFFICIENT )")
    for line in timeline(records):
        print(line)

    segments = find_segments(records, args.min_segment)
    print(f"\nScorable segments (at least {args.min_segment:.0f}s)")
    if not segments:
        print("  none")
    for index, segment in enumerate(segments, 1):
        print(
            f"  {index}. {segment.start_s:6.1f}s -> {segment.end_s:6.1f}s   "
            f"{segment.duration_s:5.1f}s   {segment.frames} frames"
        )
    total = sum(s.duration_s for s in segments)
    print(f"  usable total {total:.1f}s of {duration:.1f}s ({100.0 * total / duration:.0f}%)")

    poses = [r.pose for r in records if r.pose.has_person]
    print("\nFraming")
    for line in framing(poses):
        print(line)

    if segments:
        chosen = segments[args.segment - 1] if args.segment else max(
            segments, key=lambda s: s.duration_s
        )
        window = [
            r.pose
            for r in records
            if chosen.start_s <= r.pose.timestamp_ms / 1000.0 <= chosen.end_s
        ]
        print(f"\nHip height over {chosen.start_s:.1f}s -> {chosen.end_s:.1f}s")
        for line in hip_trace(window):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
