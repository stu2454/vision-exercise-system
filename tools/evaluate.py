"""Evaluate STS-001 against the regression dataset (Build 6).

    python tools/evaluate.py
    python tools/evaluate.py --json
    python tools/evaluate.py --case sts_gesture_001

No algorithm change should be judged by watching one successful
demonstration (Document 03 §29). Run this before and after a change and
compare the error profile, not just the percentage: a conservative miss and
an invented repetition are not equivalent failures.

Exits non-zero when any false repetition is detected, so this is usable as a
gate. A miss does not fail the run, because the preferred failure is the
conservative one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, load_sts_config  # noqa: E402
from src.evaluation import (  # noqa: E402
    DEFAULT_CASE_DIRECTORY,
    DEFAULT_SEARCH_PATHS,
    DatasetError,
    evaluate_dataset,
    load_cases,
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=DEFAULT_CASE_DIRECTORY, help="Case directory."
    )
    parser.add_argument(
        "--recordings",
        type=Path,
        action="append",
        default=None,
        help="Directory to search for recordings. May be repeated.",
    )
    parser.add_argument("--case", default=None, help="Evaluate one case by id.")
    parser.add_argument(
        "--exercise-config", type=Path, default=None, help="STS-001 configuration."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.cases)
    except DatasetError as exc:
        print(f"Dataset error: {exc}", file=sys.stderr)
        return 1

    if args.case:
        cases = [c for c in cases if c.case_id == args.case]
        if not cases:
            print(f"No case with id '{args.case}' in {args.cases}", file=sys.stderr)
            return 1

    if not cases:
        print(f"No cases found in {args.cases}", file=sys.stderr)
        return 1

    search_paths = args.recordings or list(DEFAULT_SEARCH_PATHS)
    report, skipped = evaluate_dataset(
        cases,
        search_paths=search_paths,
        config=load_config(),
        sts_config=load_sts_config(args.exercise_config),
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())
        if skipped:
            # Said plainly: a suite that silently reports on a subset is
            # worse than one that fails.
            print()
            print(f"Skipped {len(skipped)} case(s), recording not found:")
            for case in skipped:
                print(f"  {case.case_id:<26} {case.recording}")
            print(f"Searched: {', '.join(str(p) for p in search_paths)}")

    if not report.outcomes:
        print("\nNo cases could be evaluated.", file=sys.stderr)
        return 1
    return 1 if report.false_positives else 0


if __name__ == "__main__":
    raise SystemExit(main())
