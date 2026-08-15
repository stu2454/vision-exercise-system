"""Measure pose-inference throughput on the current machine.

Answers the question that decides whether the Raspberry Pi 5 needs the AI HAT:

    how many frames per second can this machine actually run pose on?

Run the same recording on the development machine and on the Pi, and compare.
Benchmarking against a recording rather than a live camera matters: a live
camera caps the measurement at its own frame rate, which hides how much
headroom the processor has or has not got.

    python tools/benchmark.py recording.mp4
    python tools/benchmark.py --synthetic --frames 120
    python tools/benchmark.py recording.mp4 --model models/pose_landmarker_full.task

Reported latency is per frame, so the median and the 95th percentile matter
more than the mean: an occasional slow frame is what a participant notices.
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.camera.base import Frame  # noqa: E402
from src.camera.video_file import VideoFileFrameSource  # noqa: E402
from src.config import load_config  # noqa: E402
from src.pose.adapters.mediapipe_adapter import MediaPipePoseEngine  # noqa: E402
from src.pose.quality import PoseQualityAssessor  # noqa: E402
from src.version import APPLICATION_VERSION  # noqa: E402


def synthetic_frames(count: int, width: int, height: int, fps: float) -> Iterator[Frame]:
    """Generate frames with moving content but no person.

    Useful for measuring raw throughput where no recording is available. The
    numbers are optimistic: detecting nobody is cheaper than tracking someone,
    so treat synthetic results as an upper bound.
    """
    for index in range(count):
        image = np.zeros((height, width, 3), dtype=np.uint8)
        centre = int((index / max(count - 1, 1)) * (width - 60)) + 30
        image[height // 4 : 3 * height // 4, centre - 30 : centre + 30] = 200
        yield Frame(image=image, timestamp_ms=index * 1000.0 / fps, index=index)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(int(fraction * len(ordered)), len(ordered) - 1)
    return ordered[index]


def run(
    frames: Iterator[Frame],
    model_path: Path,
    warmup: int,
) -> tuple[list[float], list[float], int]:
    """Run inference over `frames`.

    Returns inference latencies, end-to-end frame latencies, and how many
    frames contained a detected person. The first `warmup` frames are excluded
    from the statistics: model loading and the first inference are far slower
    than the steady state and would otherwise dominate a short run.
    """
    engine = MediaPipePoseEngine(model_path)
    assessor = PoseQualityAssessor(load_config().pose_quality)
    inference_ms: list[float] = []
    total_ms: list[float] = []
    detected = 0

    with engine:
        for position, frame in enumerate(frames):
            started = time.perf_counter()
            pose = engine.estimate(frame, source="benchmark")
            assessor.assess(pose)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if position < warmup:
                continue
            if pose.has_person:
                detected += 1
            inference_ms.append(engine.last_inference_ms or 0.0)
            total_ms.append(elapsed_ms)
    return inference_ms, total_ms, detected


def report(
    label: str,
    model_path: Path,
    inference_ms: list[float],
    total_ms: list[float],
    detected: int,
) -> None:
    if not total_ms:
        print("No frames measured. Increase --frames or reduce --warmup.")
        return
    print()
    print(f"Vision Exercise System {APPLICATION_VERSION} — pose benchmark")
    print(f"  platform          {platform.system()} {platform.machine()}")
    print(f"  python            {platform.python_version()}")
    print(f"  model             {model_path.name}")
    print(f"  input             {label}")
    print(f"  frames measured   {len(total_ms)}")
    print(f"  person detected   {detected} of {len(total_ms)} frames")
    print()
    print("  pose inference    median {:6.1f} ms   p95 {:6.1f} ms   max {:6.1f} ms".format(
        statistics.median(inference_ms), percentile(inference_ms, 0.95), max(inference_ms)
    ))
    print("  frame total       median {:6.1f} ms   p95 {:6.1f} ms   max {:6.1f} ms".format(
        statistics.median(total_ms), percentile(total_ms, 0.95), max(total_ms)
    ))
    sustained = 1000.0 / statistics.median(total_ms)
    print()
    print(f"  sustained rate    {sustained:.1f} fps")
    print()
    # 30 fps is the capture target in Document 03 §9. Falling below it does
    # not make the system unusable; it makes movement timing coarser, which
    # matters most for velocity features and reaction-time exercises.
    if sustained >= 30:
        print("  At or above the 30 fps capture target.")
    elif sustained >= 15:
        print("  Below 30 fps. Usable for sit-to-stand; velocity features get coarser.")
    else:
        print("  Below 15 fps. Consider a lower capture resolution or the lite model")
        print("  before concluding that accelerator hardware is required.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="Video file to benchmark.")
    parser.add_argument(
        "--synthetic", action="store_true", help="Use generated frames instead of a file."
    )
    parser.add_argument("--frames", type=int, default=120, help="Synthetic frame count.")
    parser.add_argument("--width", type=int, default=1280, help="Synthetic frame width.")
    parser.add_argument("--height", type=int, default=720, help="Synthetic frame height.")
    parser.add_argument(
        "--warmup", type=int, default=5, help="Frames excluded from statistics."
    )
    parser.add_argument("--model", type=Path, default=None, help="Pose model override.")
    args = parser.parse_args(argv)

    config = load_config()
    model_path = args.model or config.pose.resolved_model_path()
    if not model_path.exists():
        print(f"Pose model not found: {model_path}", file=sys.stderr)
        print("Run: python tools/fetch_models.py", file=sys.stderr)
        return 1

    if args.synthetic or args.path is None:
        label = f"synthetic {args.width}x{args.height}"
        frames = synthetic_frames(args.frames, args.width, args.height, config.camera.fps)
        inference_ms, total_ms, detected = run(frames, model_path, args.warmup)
    else:
        if not args.path.exists():
            print(f"Video not found: {args.path}", file=sys.stderr)
            return 1
        label = args.path.name
        with VideoFileFrameSource(args.path) as source:
            inference_ms, total_ms, detected = run(
                source.frames(), model_path, args.warmup
            )

    report(label, model_path, inference_ms, total_ms, detected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
