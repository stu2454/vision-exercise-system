"""Tests for the STS-001 sit-to-stand state machine.

Movement is synthesised so that the true repetition count is known exactly.
The properties under test are the ones the project cares about most: a
repetition counts only after the full sequence, noise never causes a
transition, and false positives are avoided in preference to raw count
accuracy (Document 03 §49).
"""

from __future__ import annotations

import pytest

from src.exercises.events import EventType
from src.exercises.sit_to_stand import (
    SitToStandEngine,
    StsCalibration,
    StsConfig,
    StsState,
)
from src.movement.features import (
    HIP_HEIGHT,
    HIP_VERTICAL_VELOCITY,
    FeatureSet,
    FeatureValue,
)
from src.pose.models import Landmark, PoseFrame
from src.pose.quality import PoseQualityReport, PoseQualityStatus

FPS = 30.0
STEP_MS = 1000.0 / FPS
SEATED_HEIGHT = 0.40
STANDING_HEIGHT = 0.55

CALIBRATION = StsCalibration(
    seated_hip_height=SEATED_HEIGHT,
    standing_hip_height=STANDING_HEIGHT,
    source="explicit",
)


def quality(status=PoseQualityStatus.GOOD) -> PoseQualityReport:
    return PoseQualityReport(status=status, instantaneous_status=status, confidence=0.9)


def features_at(height: float, timestamp_ms: float, velocity: float = 0.0) -> FeatureSet:
    return FeatureSet(
        timestamp_ms=timestamp_ms,
        features={
            HIP_HEIGHT: FeatureValue(HIP_HEIGHT, height, "image_heights", 0.9, True),
            HIP_VERTICAL_VELOCITY: FeatureValue(
                HIP_VERTICAL_VELOCITY, velocity, "image_heights_per_second", 0.9, True
            ),
        },
    )


POSE = PoseFrame(0.0, 0.9, {"hip_centre": Landmark(0.5, 0.5, 0.0, 0.9)}, "test")


class Session:
    """Feeds synthetic movement to an engine and collects events."""

    def __init__(self, engine: SitToStandEngine, start_ms: float = 0.0) -> None:
        self.engine = engine
        self.now = start_ms
        self.events = []
        self._previous_height = None

    def feed(self, height: float, frames: int = 1, status=PoseQualityStatus.GOOD):
        for _ in range(frames):
            velocity = 0.0
            if self._previous_height is not None:
                velocity = (height - self._previous_height) * 1000.0 / STEP_MS
            self.events += self.engine.update(
                POSE, features_at(height, self.now, velocity), quality(status)
            )
            self._previous_height = height
            self.now += STEP_MS
        return self

    def ramp(self, start: float, end: float, frames: int, status=PoseQualityStatus.GOOD):
        for i in range(frames):
            self.feed(start + (end - start) * (i + 1) / frames, status=status)
        return self

    def repetition(self, hold: int = 12, move: int = 24):
        """One complete sit-to-stand at a plausible human pace.

        Roughly 2.4 s at 30 fps. Frame counts matter: the engine rejects
        cycles shorter than `minimum_rep_seconds` as detection artefacts, so
        an unrealistically brisk fixture would be discarded exactly as a
        spurious detection should be.
        """
        self.ramp(SEATED_HEIGHT, STANDING_HEIGHT, move)
        self.feed(STANDING_HEIGHT, hold)
        self.ramp(STANDING_HEIGHT, SEATED_HEIGHT, move)
        self.feed(SEATED_HEIGHT, hold)
        return self

    def count(self, event_type: EventType) -> int:
        return sum(1 for e in self.events if e.event is event_type)


def calibrated_engine(config: StsConfig | None = None) -> SitToStandEngine:
    engine = SitToStandEngine(config or StsConfig())
    engine.initialise(CALIBRATION)
    return engine


class TestRepetitionCounting:
    def test_a_full_sequence_counts_one_repetition(self):
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 5).repetition()
        assert session.count(EventType.REP_COMPLETED) == 1
        assert session.engine.valid_repetitions == 1

    def test_ten_repetitions_count_ten(self):
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 5)
        for _ in range(10):
            session.repetition()
        assert session.engine.valid_repetitions == 10

    def test_sitting_still_counts_nothing(self):
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 300)
        assert session.engine.valid_repetitions == 0
        assert session.count(EventType.REP_STARTED) == 0

    def test_standing_still_counts_nothing(self):
        session = Session(calibrated_engine()).feed(STANDING_HEIGHT, 300)
        assert session.engine.valid_repetitions == 0

    def test_standing_up_alone_does_not_count(self):
        # The sequence is incomplete until the participant sits again.
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 5)
        session.ramp(SEATED_HEIGHT, STANDING_HEIGHT, 8).feed(STANDING_HEIGHT, 30)
        assert session.count(EventType.REP_STARTED) == 1
        assert session.count(EventType.REP_COMPLETED) == 0

    def test_events_arrive_in_the_expected_order(self):
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 5).repetition()
        order = [
            e.event
            for e in session.events
            if e.event
            in (
                EventType.REP_STARTED,
                EventType.TARGET_POSITION_REACHED,
                EventType.REP_COMPLETED,
            )
        ]
        assert order == [
            EventType.REP_STARTED,
            EventType.TARGET_POSITION_REACHED,
            EventType.REP_COMPLETED,
        ]

    def test_repetition_events_are_numbered(self):
        session = Session(calibrated_engine()).feed(SEATED_HEIGHT, 5)
        session.repetition().repetition().repetition()
        completed = [e for e in session.events if e.event is EventType.REP_COMPLETED]
        assert [e.sequence for e in completed] == [1, 2, 3]


class TestPartialRepetitions:
    @staticmethod
    def _rise_halfway_and_sit(engine) -> Session:
        # Continuous movement with no pause at the apex. Pausing there would
        # drop the upward velocity that confirms rising, so the engine would
        # never enter RISING at all -- a real limitation of requiring
        # velocity confirmation, worth knowing about.
        halfway = SEATED_HEIGHT + (STANDING_HEIGHT - SEATED_HEIGHT) * 0.5
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.ramp(SEATED_HEIGHT, halfway, 12)
        session.ramp(halfway, SEATED_HEIGHT, 12).feed(SEATED_HEIGHT, 8)
        return session

    def test_rising_partway_and_sitting_is_a_partial(self):
        session = self._rise_halfway_and_sit(calibrated_engine())
        assert session.count(EventType.PARTIAL_REP) == 1
        assert session.count(EventType.REP_COMPLETED) == 0

    def test_a_partial_does_not_increment_valid_repetitions(self):
        session = self._rise_halfway_and_sit(calibrated_engine())
        assert session.engine.valid_repetitions == 0
        assert session.engine.result().partial_repetitions == 1


class TestNoiseRejection:
    def test_jitter_at_a_threshold_produces_no_repetitions(self):
        # The failure hysteresis and dwell exist to prevent: a held posture
        # whose noise straddles a boundary.
        engine = calibrated_engine()
        session = Session(engine)
        boundary = SEATED_HEIGHT + (STANDING_HEIGHT - SEATED_HEIGHT) * 0.25
        for i in range(300):
            session.feed(boundary + (0.004 if i % 2 else -0.004))
        assert engine.valid_repetitions == 0

    def test_a_single_spurious_frame_does_not_change_state(self):
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 20)
        session.feed(STANDING_HEIGHT, 1)
        session.feed(SEATED_HEIGHT, 5)
        assert engine.state is StsState.SEATED
        assert engine.valid_repetitions == 0

    def test_dwell_time_is_required_for_a_transition(self):
        config = StsConfig(minimum_dwell_ms=200.0)
        engine = calibrated_engine(config)
        session = Session(engine).feed(SEATED_HEIGHT, 10)
        # Two frames at 30 fps is 67 ms, well under the required dwell.
        session.ramp(SEATED_HEIGHT, STANDING_HEIGHT, 2)
        assert engine.state is not StsState.STANDING


class TestImplausibleRepetitions:
    @staticmethod
    def _too_fast(engine) -> Session:
        """A complete cycle faster than a person can sit and stand."""
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.ramp(SEATED_HEIGHT, STANDING_HEIGHT, 4).feed(STANDING_HEIGHT, 3)
        session.ramp(STANDING_HEIGHT, SEATED_HEIGHT, 4).feed(SEATED_HEIGHT, 5)
        return session

    def test_an_impossibly_fast_cycle_is_rejected(self):
        # Prefer a missed repetition to a false one (Document 03 §49).
        engine = calibrated_engine(
            StsConfig(minimum_dwell_ms=0.0, minimum_rep_seconds=2.0)
        )
        session = self._too_fast(engine)
        assert engine.valid_repetitions == 0
        assert session.count(EventType.INVALID_REP) == 1
        invalid = next(e for e in session.events if e.event is EventType.INVALID_REP)
        assert invalid.payload["reason"] == "implausibly_short"

    def test_a_rejected_repetition_does_not_inflate_attempts(self):
        engine = calibrated_engine(
            StsConfig(minimum_dwell_ms=0.0, minimum_rep_seconds=2.0)
        )
        self._too_fast(engine)
        assert engine.result().attempted_repetitions == 0

    def test_the_same_cycle_counts_when_the_bound_permits_it(self):
        # Confirms the rejection is about the duration bound, not a
        # structural failure to recognise the movement.
        engine = calibrated_engine(
            StsConfig(minimum_dwell_ms=0.0, minimum_rep_seconds=0.1)
        )
        self._too_fast(engine)
        assert engine.valid_repetitions == 1


class TestPoseQuality:
    def test_insufficient_quality_suspends_scoring(self):
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.feed(SEATED_HEIGHT, 5, status=PoseQualityStatus.INSUFFICIENT)
        assert engine.state is StsState.SUSPENDED
        assert session.count(EventType.EXERCISE_PAUSED) == 1

    def test_a_repetition_interrupted_by_tracking_loss_is_not_penalised(self):
        # CLAUDE.md §7: the incomplete action must not count against the
        # participant, and is not recorded as a partial either, because
        # nothing is known about whether it was completed.
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.ramp(SEATED_HEIGHT, STANDING_HEIGHT, 8)
        session.feed(STANDING_HEIGHT, 5, status=PoseQualityStatus.INSUFFICIENT)
        result = engine.result()
        assert result.valid_repetitions == 0
        assert result.partial_repetitions == 0
        assert result.attempted_repetitions == 0

    def test_scoring_resumes_after_quality_recovers(self):
        engine = calibrated_engine(StsConfig(quality_recovery_frames=3))
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.feed(SEATED_HEIGHT, 5, status=PoseQualityStatus.INSUFFICIENT)
        session.feed(SEATED_HEIGHT, 10)
        assert engine.state is not StsState.SUSPENDED
        session.repetition()
        assert engine.valid_repetitions == 1

    def test_recovery_needs_sustained_good_frames(self):
        engine = calibrated_engine(StsConfig(quality_recovery_frames=10))
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.feed(SEATED_HEIGHT, 5, status=PoseQualityStatus.INSUFFICIENT)
        session.feed(SEATED_HEIGHT, 3)
        assert engine.state is StsState.SUSPENDED

    def test_degraded_quality_still_scores(self):
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5, status=PoseQualityStatus.DEGRADED)
        session.repetition()
        assert engine.valid_repetitions == 1

    def test_worst_quality_is_reported_in_the_result(self):
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.feed(SEATED_HEIGHT, 3, status=PoseQualityStatus.DEGRADED)
        assert engine.result().pose_quality == "degraded"


class TestCalibration:
    def test_scoring_waits_for_calibration(self):
        engine = SitToStandEngine()
        engine.initialise()
        session = Session(engine).feed(SEATED_HEIGHT, 30)
        assert engine.calibration is None
        assert session.count(EventType.REP_STARTED) == 0

    def test_a_movement_cycle_calibrates_the_participant(self):
        engine = SitToStandEngine()
        engine.initialise()
        session = Session(engine).feed(SEATED_HEIGHT, 15).repetition()
        assert engine.calibration is not None
        # At least one; refinement at each SEATED may emit more.
        assert session.count(EventType.CALIBRATED) >= 1
        assert engine.calibration.travel > 0

    def test_calibration_converges_on_the_true_range(self):
        # On real recordings the initial estimate is taken part-way through
        # the first rise and understates the range badly: 0.042 against a
        # true 0.133, which compressed the scale threefold. Refinement must
        # end up at the true excursion. A synthetic fixture reaches it sooner
        # than a real one, so this checks the destination, not the path.
        engine = SitToStandEngine()
        engine.initialise()
        session = Session(engine).feed(SEATED_HEIGHT, 15)
        for _ in range(5):
            session.repetition()
        assert engine.calibration.travel == pytest.approx(
            STANDING_HEIGHT - SEATED_HEIGHT, rel=0.15
        )

    def test_calibration_only_widens(self):
        # Narrowing would let one shallow stand shrink the reference range
        # and inflate every later measurement.
        engine = SitToStandEngine()
        engine.initialise()
        session = Session(engine).feed(SEATED_HEIGHT, 15)
        for _ in range(3):
            session.repetition()
        wide = engine.calibration.travel
        shallow = SEATED_HEIGHT + (STANDING_HEIGHT - SEATED_HEIGHT) * 0.4
        for _ in range(3):
            session.ramp(SEATED_HEIGHT, shallow, 12)
            session.ramp(shallow, SEATED_HEIGHT, 12).feed(SEATED_HEIGHT, 10)
        assert engine.calibration.travel >= wide

    def test_repetitions_after_calibration_are_counted(self):
        engine = SitToStandEngine()
        engine.initialise()
        session = Session(engine).feed(SEATED_HEIGHT, 15)
        for _ in range(5):
            session.repetition()
        # The calibrating cycle is not scored, which is a deliberate trade.
        assert engine.valid_repetitions >= 4

    def test_calibration_normalises_to_zero_and_one(self):
        assert CALIBRATION.normalise(SEATED_HEIGHT) == pytest.approx(0.0)
        assert CALIBRATION.normalise(STANDING_HEIGHT) == pytest.approx(1.0)

    def test_a_degenerate_calibration_normalises_to_nothing(self):
        flat = StsCalibration(seated_hip_height=0.5, standing_hip_height=0.5)
        assert flat.normalise(0.5) is None

    def test_supplied_calibration_emits_an_event(self):
        engine = SitToStandEngine()
        events = engine.initialise(CALIBRATION)
        assert [e.event for e in events] == [EventType.CALIBRATED]


class TestResultContract:
    def test_the_result_matches_the_documented_shape(self):
        engine = calibrated_engine(StsConfig(target_repetitions=3))
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        for _ in range(3):
            session.repetition()
        engine.stop()
        data = engine.result().to_dict()
        for key in (
            "exercise_id",
            "exercise_specification_version",
            "exercise_algorithm_version",
            "attempted_repetitions",
            "valid_repetitions",
            "partial_repetitions",
            "metrics",
            "quality_flags",
            "pose_quality",
        ):
            assert key in data
        assert data["exercise_id"] == "STS-001"
        assert data["valid_repetitions"] == 3
        assert data["outcome"] == "completed"

    def test_metrics_describe_repetition_timing(self):
        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        for _ in range(3):
            session.repetition()
        metrics = engine.result().metrics
        assert metrics["mean_rep_duration_seconds"] > 0
        assert metrics["mean_rise_time_seconds"] > 0
        assert metrics["mean_descent_time_seconds"] > 0

    def test_the_result_is_json_serialisable(self):
        import json

        engine = calibrated_engine()
        session = Session(engine).feed(SEATED_HEIGHT, 5).repetition()
        engine.stop()
        assert json.loads(json.dumps(engine.result().to_dict()))["valid_repetitions"] == 1

    def test_reaching_the_target_completes_the_exercise(self):
        engine = calibrated_engine(StsConfig(target_repetitions=2))
        session = Session(engine).feed(SEATED_HEIGHT, 5).repetition().repetition()
        assert session.count(EventType.EXERCISE_COMPLETED) == 1

    def test_rapid_descent_raises_a_quality_flag(self):
        engine = calibrated_engine(
            StsConfig(minimum_dwell_ms=0.0, rapid_descent_seconds=0.4, minimum_rep_seconds=0.3)
        )
        session = Session(engine).feed(SEATED_HEIGHT, 5)
        session.ramp(SEATED_HEIGHT, STANDING_HEIGHT, 10).feed(STANDING_HEIGHT, 2)
        session.ramp(STANDING_HEIGHT, SEATED_HEIGHT, 2).feed(SEATED_HEIGHT, 5)
        assert engine.result().quality_flags.get("rapid_descent") == 1


class TestConfigValidation:
    def test_inverted_hysteresis_is_rejected(self):
        with pytest.raises(ValueError, match="hysteresis"):
            StsConfig(standing_enter=0.6, standing_exit=0.8).validate()

    def test_seated_above_rising_is_rejected(self):
        with pytest.raises(ValueError, match="seated_enter"):
            StsConfig(seated_enter=0.5, rising_enter=0.3).validate()

    def test_reversed_duration_bounds_are_rejected(self):
        with pytest.raises(ValueError, match="minimum_rep_seconds"):
            StsConfig(minimum_rep_seconds=10.0, maximum_rep_seconds=5.0).validate()


class TestDeterminism:
    def test_the_same_input_gives_the_same_events(self):
        def run() -> list[dict]:
            engine = calibrated_engine()
            session = Session(engine).feed(SEATED_HEIGHT, 5)
            for _ in range(4):
                session.repetition()
            return [e.to_dict() for e in session.events]

        assert run() == run()

    def test_initialise_resets_everything(self):
        engine = calibrated_engine()
        Session(engine).feed(SEATED_HEIGHT, 5).repetition()
        assert engine.valid_repetitions == 1
        engine.initialise(CALIBRATION)
        assert engine.valid_repetitions == 0
        assert engine.state is StsState.NO_PERSON
