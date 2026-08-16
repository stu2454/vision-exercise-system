"""Regression dataset and evaluation (Build 6).

Algorithm changes are judged against a fixed set of recordings with known
outcomes, not against a fresh demonstration (Document 03 §29, CLAUDE.md §20).
A single count-accuracy percentage hides the behaviour that matters, so the
error profile is reported in parts: missed, false, partial, unscorable.

Ground truth lives in case files, separate from anything the algorithm
produces (Document 03 §27). Nothing here writes to them.

Recordings themselves are not part of this module's contract. Case files
reference them by name and the loader searches configured directories, so a
dataset can be shared without the movement data, or kept entirely local.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from src.config import AppConfig, ConfigurationError, load_config, load_sts_config
from src.exercises.base import ExerciseResult
from src.exercises.events import Event, EventType
from src.exercises.sit_to_stand import SitToStandEngine, StsConfig
from src.movement.features import FeatureExtractor
from src.movement.filtering import PoseFilter
from src.movement.gestures import ArmRaiseDetector
from src.pose.quality import PoseQualityAssessor, PoseQualityStatus
from src.replay.pose_replay import PoseStreamMetadata, PoseStreamSource

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASE_DIRECTORY = REPOSITORY_ROOT / "test_data" / "regression"
DEFAULT_SEARCH_PATHS = (
    REPOSITORY_ROOT / "test_data" / "pose",
    REPOSITORY_ROOT / "recordings",
)


class DatasetError(RuntimeError):
    """Raised when a case file is missing or malformed."""


@dataclass(frozen=True)
class RegressionCase:
    """One recording with a known outcome.

    Attributes:
        case_id: Stable identifier, used in reports.
        recording: File name of the pose stream.
        exercise_id: Which exercise the expectations describe.
        true_repetitions: Repetitions the participant actually performed.
            Human-observed, and the authority against which the algorithm is
            judged.
        partial_repetitions: Repetitions begun but not completed.
        camera_view: Where the camera was, an open experimental variable.
        hand_support_reps: Repetitions performed using hand support.
        use_gestures: Whether the recording is delimited by start and stop
            gestures. Scoring must treat it the same way the live session
            did, or the comparison is against a different thing.
        notes: What makes this case worth keeping.
    """

    case_id: str
    recording: str
    exercise_id: str = "STS-001"
    true_repetitions: int = 0
    partial_repetitions: int = 0
    camera_view: str = "unspecified"
    hand_support_reps: tuple[int, ...] = ()
    use_gestures: bool = True
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: Path) -> "RegressionCase":
        try:
            return cls(
                case_id=str(data["case_id"]),
                recording=str(data["recording"]),
                exercise_id=str(data.get("exercise_id", "STS-001")),
                true_repetitions=int(data.get("true_repetitions", 0)),
                partial_repetitions=int(data.get("partial_repetitions", 0)),
                camera_view=str(data.get("camera_view", "unspecified")),
                hand_support_reps=tuple(data.get("hand_support_reps", ()) or ()),
                use_gestures=bool(data.get("use_gestures", True)),
                notes=str(data.get("notes", "")),
            )
        except KeyError as exc:
            raise DatasetError(f"{source}: missing required key {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise DatasetError(f"{source}: invalid value ({exc})") from exc


@dataclass
class ScoredStream:
    """What scoring one pose stream produced."""

    result: ExerciseResult
    events: list[Event]
    metadata: PoseStreamMetadata
    frames: int = 0
    started_at_ms: Optional[float] = None
    stopped_at_ms: Optional[float] = None
    processing_ms_per_frame: float = 0.0

    def count(self, event_type: EventType) -> int:
        return sum(1 for event in self.events if event.event is event_type)


def score_pose_stream(
    path: Path | str,
    config: Optional[AppConfig] = None,
    sts_config: Optional[StsConfig] = None,
    use_gestures: bool = True,
) -> ScoredStream:
    """Run the full pipeline over a recorded pose stream.

    The single scoring path, shared by the `score` command, the evaluation
    tool and the regression tests. Duplicating it would let them drift, and
    then a passing regression suite would say nothing about what the command
    actually does.

    Runs no pose inference, so the same recording always gives the same
    result (CLAUDE.md §17).
    """
    config = config or load_config()
    sts_config = sts_config or load_sts_config()

    assessor = PoseQualityAssessor(config.pose_quality)
    pose_filter = PoseFilter(config.filtering)
    extractor = FeatureExtractor(config.features)
    engine = SitToStandEngine(sts_config)
    engine.initialise()

    gestures = config.gestures
    start_gesture = ArmRaiseDetector(gestures.start_config()) if use_gestures else None
    stop_gesture = (
        ArmRaiseDetector(gestures.stop_config(), required_arms=2) if use_gestures else None
    )
    awaiting_start = start_gesture is not None
    settle_until_ms: Optional[float] = None
    started_at_ms: Optional[float] = None
    stopped_at_ms: Optional[float] = None

    events: list[Event] = []
    frames = 0
    elapsed_s = 0.0

    with PoseStreamSource(path) as stream:
        metadata = stream.metadata
        for pose in stream.poses():
            if awaiting_start and start_gesture is not None:
                if settle_until_ms is None:
                    if start_gesture.update(pose).triggered:
                        settle_until_ms = (
                            pose.timestamp_ms + gestures.settle_seconds * 1000.0
                        )
                elif pose.timestamp_ms >= settle_until_ms:
                    engine.initialise()
                    awaiting_start = False
                    started_at_ms = pose.timestamp_ms
                if awaiting_start:
                    continue
            if stop_gesture is not None and stop_gesture.update(pose).triggered:
                stopped_at_ms = pose.timestamp_ms
                break

            began = time.perf_counter()
            quality = assessor.assess(pose)
            features = extractor.update(pose_filter.apply(pose))
            events.extend(engine.update(pose, features, quality))
            elapsed_s += time.perf_counter() - began
            frames += 1

    events.extend(engine.stop())
    return ScoredStream(
        result=engine.result(),
        events=events,
        metadata=metadata,
        frames=frames,
        started_at_ms=started_at_ms,
        stopped_at_ms=stopped_at_ms,
        processing_ms_per_frame=(elapsed_s * 1000.0 / frames) if frames else 0.0,
    )


@dataclass
class CaseOutcome:
    """How the algorithm did on one case.

    Missed and false repetitions are counted separately and never netted off
    against each other. A case that misses one and invents one is not the
    same as a case that gets both right, and a single accuracy figure would
    call them identical (Document 03 §49).
    """

    case: RegressionCase
    scored: ScoredStream

    @property
    def detected(self) -> int:
        return self.scored.result.valid_repetitions

    @property
    def missed(self) -> int:
        return max(0, self.case.true_repetitions - self.detected)

    @property
    def false_positives(self) -> int:
        return max(0, self.detected - self.case.true_repetitions)

    @property
    def exact(self) -> bool:
        return self.detected == self.case.true_repetitions

    @property
    def pose_loss_events(self) -> int:
        return self.scored.count(EventType.POSE_QUALITY_INSUFFICIENT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.case_id,
            "camera_view": self.case.camera_view,
            "true_repetitions": self.case.true_repetitions,
            "detected": self.detected,
            "missed": self.missed,
            "false_positives": self.false_positives,
            "partial_detected": self.scored.result.partial_repetitions,
            "partial_expected": self.case.partial_repetitions,
            "pose_loss_events": self.pose_loss_events,
            "frames": self.scored.frames,
            "processing_ms_per_frame": round(self.scored.processing_ms_per_frame, 3),
            "metrics": self.scored.result.metrics,
        }


@dataclass
class DatasetReport:
    """Aggregate performance over a dataset."""

    outcomes: list[CaseOutcome] = field(default_factory=list)
    algorithm_version: str = ""

    @property
    def true_repetitions(self) -> int:
        return sum(o.case.true_repetitions for o in self.outcomes)

    @property
    def detected(self) -> int:
        return sum(o.detected for o in self.outcomes)

    @property
    def missed(self) -> int:
        return sum(o.missed for o in self.outcomes)

    @property
    def false_positives(self) -> int:
        return sum(o.false_positives for o in self.outcomes)

    @property
    def exact_cases(self) -> int:
        return sum(1 for o in self.outcomes if o.exact)

    @property
    def count_accuracy(self) -> float:
        """Correctly detected repetitions as a percentage of true ones."""
        if not self.true_repetitions:
            return 0.0
        correct = self.true_repetitions - self.missed
        return 100.0 * correct / self.true_repetitions

    @property
    def mean_processing_ms(self) -> float:
        values = [o.scored.processing_ms_per_frame for o in self.outcomes]
        return statistics.mean(values) if values else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": self.algorithm_version,
            "cases": len(self.outcomes),
            "true_repetitions": self.true_repetitions,
            "detected": self.detected,
            "missed": self.missed,
            "false_positives": self.false_positives,
            "count_accuracy": round(self.count_accuracy, 1),
            "exact_cases": self.exact_cases,
            "mean_processing_ms_per_frame": round(self.mean_processing_ms, 3),
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    def format_text(self) -> str:
        lines = [
            f"STS-001 algorithm {self.algorithm_version}",
            f"Cases: {len(self.outcomes)}",
            "",
            f"{'case':<26}{'view':<18}{'true':>5}{'det':>5}{'miss':>6}{'false':>7}{'loss':>6}",
        ]
        for outcome in sorted(self.outcomes, key=lambda o: o.case.case_id):
            flag = "" if outcome.exact else "  <--"
            lines.append(
                f"{outcome.case.case_id:<26}{outcome.case.camera_view:<18}"
                f"{outcome.case.true_repetitions:>5}{outcome.detected:>5}"
                f"{outcome.missed:>6}{outcome.false_positives:>7}"
                f"{outcome.pose_loss_events:>6}{flag}"
            )
        lines += [
            "",
            f"True repetitions:      {self.true_repetitions:>5}",
            f"Detected correctly:    {self.true_repetitions - self.missed:>5}",
            f"Missed:                {self.missed:>5}",
            f"False positives:       {self.false_positives:>5}",
            "",
            f"Count agreement:       {self.count_accuracy:>5.1f}%",
            f"Exact cases:           {self.exact_cases}/{len(self.outcomes)}",
            f"Processing:            {self.mean_processing_ms:.2f} ms/frame",
        ]
        if self.false_positives:
            lines += [
                "",
                "False repetitions present. A conservative miss is preferable to",
                "a repetition the participant did not perform (Document 03 §49).",
            ]
        return "\n".join(lines)


def load_cases(directory: Path | str = DEFAULT_CASE_DIRECTORY) -> list[RegressionCase]:
    """Load every case file in `directory`."""
    path = Path(directory)
    if not path.exists():
        return []
    cases = []
    for file in sorted(path.glob("*.yaml")):
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise DatasetError(f"Could not parse {file}: {exc}") from exc
        if not isinstance(data, dict):
            raise DatasetError(f"{file} must contain a mapping.")
        cases.append(RegressionCase.from_dict(data, file))
    return cases


def find_recording(
    case: RegressionCase, search_paths: Iterable[Path] = DEFAULT_SEARCH_PATHS
) -> Optional[Path]:
    """Locate the pose stream for a case, or None if it is not present.

    Absence is not an error. Recordings are movement data and may be kept
    outside the repository, so a case whose recording is unavailable is
    skipped rather than failing the suite.
    """
    for directory in search_paths:
        candidate = Path(directory) / case.recording
        if candidate.exists():
            return candidate
    return None


def evaluate_case(
    case: RegressionCase,
    path: Path,
    config: Optional[AppConfig] = None,
    sts_config: Optional[StsConfig] = None,
) -> CaseOutcome:
    """Score one case."""
    scored = score_pose_stream(
        path, config=config, sts_config=sts_config, use_gestures=case.use_gestures
    )
    return CaseOutcome(case=case, scored=scored)


def evaluate_dataset(
    cases: Iterable[RegressionCase],
    search_paths: Iterable[Path] = DEFAULT_SEARCH_PATHS,
    config: Optional[AppConfig] = None,
    sts_config: Optional[StsConfig] = None,
) -> tuple[DatasetReport, list[RegressionCase]]:
    """Score every case whose recording can be found.

    Returns the report and the cases that were skipped for want of a
    recording, so a caller can say so rather than quietly reporting on less
    than it appears to.
    """
    config = config or load_config()
    sts_config = sts_config or load_sts_config()
    outcomes: list[CaseOutcome] = []
    skipped: list[RegressionCase] = []
    for case in cases:
        path = find_recording(case, search_paths)
        if path is None:
            skipped.append(case)
            continue
        outcomes.append(evaluate_case(case, path, config, sts_config))
    from src.exercises.sit_to_stand import ALGORITHM_VERSION

    return DatasetReport(outcomes=outcomes, algorithm_version=ALGORITHM_VERSION), skipped
