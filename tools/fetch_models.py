"""Download the MediaPipe Pose Landmarker model bundles.

Model files are binaries of several megabytes and are not committed to the
repository (CLAUDE.md §30). Run this once after cloning:

    python tools/fetch_models.py

`lite` is the default for interactive frame rates; `full` is more accurate and
slower. Which is better for this project is an empirical question — compare
them on the same recording rather than by impression (CLAUDE.md §37).
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIRECTORY = REPOSITORY_ROOT / "models"

MODELS: dict[str, str] = {
    "lite": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    "full": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_full/float16/1/pose_landmarker_full.task"
    ),
    "heavy": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    ),
}


def fetch(variant: str, force: bool = False) -> Path:
    """Download one model variant, skipping it if already present."""
    url = MODELS[variant]
    destination = MODEL_DIRECTORY / f"pose_landmarker_{variant}.task"
    if destination.exists() and not force:
        print(f"  {variant:<6} already present  {destination.name}")
        return destination

    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    print(f"  {variant:<6} downloading      {url}")
    # Download to a temporary name so an interrupted download cannot leave a
    # truncated file that later looks like a valid model.
    temporary = destination.with_suffix(".task.partial")
    urllib.request.urlretrieve(url, temporary)
    temporary.replace(destination)
    size_mb = destination.stat().st_size / (1024 * 1024)
    print(f"  {variant:<6} saved            {destination.name} ({size_mb:.1f} MB)")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variants",
        nargs="*",
        default=["lite", "full"],
        choices=sorted(MODELS) + [],
        help="Model variants to download (default: lite full).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if present."
    )
    args = parser.parse_args(argv)

    print(f"Pose models -> {MODEL_DIRECTORY}")
    for variant in args.variants or ["lite", "full"]:
        try:
            fetch(variant, force=args.force)
        except (urllib.error.URLError, OSError) as exc:
            print(f"  {variant:<6} FAILED           {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
