"""STS-001 Sit-to-Stand reference exercise (Build 5).

State model (CLAUDE.md §12):

    SEATED -> RISING -> STANDING -> DESCENDING -> SEATED

A repetition increments only after that whole sequence completes.
`FORWARD_PREPARATION` is deliberately not implemented: Document 03 §19 permits
omitting it, and it should only be added if it demonstrably improves
recognition.

The primary signal is hip height, with hip vertical velocity used to confirm
movement direction. Knee angle is deliberately *not* used for state
transitions. It corroborates hip height well from an oblique view but is badly
foreshortened from a frontal one — measured range 48 degrees frontal against
82 degrees oblique on the same participant — so depending on it would make
recognition worse at exactly the camera angle that scores best.

No threshold is hard-coded. Every value comes from configuration
(CLAUDE.md §13, §24), and the numbers there are engineering parameters
established by experiment, not clinical thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.exercises.base import ExerciseEngine, ExerciseResult
from src.exercises.events import Event, EventType
from src.movement.features import (
    HIP_HEIGHT,
    HIP_VERTICAL_VELOCITY,
    MEAN_KNEE_ANGLE,
    TRUNK_ANGLE,
    FeatureSet,
)
from src.pose.models import PoseFrame
from src.pose.quality import PoseQualityReport, PoseQualityStatus

EXERCISE_ID = "STS-001"
SPECIFICATION_VERSION = "0.1"
ALGORITHM_VERSION = "0.1.0"


class StsState(str, Enum):
    """States of the sit-to-stand recogniser."""

    NO_PERSON = "NO_PERSON"
    CALIBRATING = "CALIBRATING"
    SEATED = "SEATED"
    RISING = "RISING"
    STANDING = "STANDING"
    DESCENDING = "DESCENDING"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class StsCalibration:
    """Participant-relative reference heights (CLAUDE.md §14).

    Population thresholds are avoided: hip height in image units depends on
    how far the participant is standing from the camera, so a threshold that
    works at 2 m fails at 3 m. Calibrating against this participant in this
    session removes that dependence.

    Attributes:
        seated_hip_height: Hip height observed while seated.
        standing_hip_height: Hip height observed while standing.
        source: How it was obtained.
        samples: Frames the estimate was drawn from.
    """

    seated_hip_height: float
    standing_hip_height: float
    source: str = "movement_cycle"
    samples: int = 0

    @property
    def travel(self) -> float:
        """Hip excursion between sitting and standing."""
        return self.standing_hip_height - self.seated_hip_height

    def normalise(self, hip_height: float) -> Optional[float]:
        """Map a hip height to 0.0 seated, 1.0 standing.

        Values outside that range are returned rather than clamped, so an
        unusually high or low posture stays visible to the caller.
        """
        if self.travel <= 1e-6:
            return None
        return (hip_height - self.seated_hip_height) / self.travel

    def to_dict(self) -> dict[str, Any]:
        return {
            "seated_hip_height": round(self.seated_hip_height, 4),
            "standing_hip_height": round(self.standing_hip_height, 4),
            "travel": round(self.travel, 4),
            "source": self.source,
            "samples": self.samples,
        }


@dataclass(frozen=True)
class StsConfig:
    """Engineering parameters for sit-to-stand recognition.

    Threshold pairs are deliberately asymmetric so a posture held near a
    boundary cannot oscillate between states (Document 03 §20).

    Attributes:
        target_repetitions: Prescribed count, or None for open-ended.
        rising_enter: Normalised height above which rising has begun.
        standing_enter: Normalised height counting as standing.
        standing_exit: Normalised height below which standing has ended.
            Must be below `standing_enter` to give hysteresis.
        seated_enter: Normalised height counting as seated again.
        minimum_dwell_ms: How long a condition must hold before the state
            changes. Prevents a single noisy frame causing a transition.
        minimum_rise_velocity: Upward hip speed required to confirm rising,
            in image heights per second. Guards against drift across the
            threshold while stationary.
        minimum_rep_seconds: Repetitions faster than this are implausible for
            a human and are rejected as detection artefacts.
        maximum_rep_seconds: Beyond this the movement is treated as abandoned
            rather than a very slow repetition.
        rapid_descent_seconds: Descent quicker than this raises a quality
            flag. A cue about control, not a safety judgement.
        calibration_minimum_travel: Hip excursion that must be observed before
            calibration is accepted.
        calibration_method: "cluster" splits observed heights into seated and
            standing clusters and takes each median; "percentile" uses the
            percentiles below. Cluster is the default because percentiles
            cannot separate repetitions from walking about, and a
            participant who walked to and from the camera inflated the
            percentile spread to 0.247 against a true travel of 0.137,
            causing every repetition to be missed.
        calibration_cluster_minimum_samples: Frames needed before clustering
            is used; below this the percentile estimate is used instead.
        calibration_low_percentile: Percentile of observed hip height taken as
            seated, when the percentile method is in use.
        calibration_high_percentile: Percentile taken as standing.
        calibration_window: Frames retained for calibration, oldest first
            discarded. A trailing window rather than the whole session: a
            participant who spends the first fifteen seconds elsewhere in
            the room would otherwise have that position treated as their
            seated reference for the rest of the attempt, which is exactly
            what happened on a real recording and left every repetition
            uncounted. Ten seconds at 30 fps spans about three repetitions,
            enough to see both postures while letting stale data age out.
        calibration_refine_interval_frames: How often calibration may be
            recomputed while no repetition is in progress. Refining only on
            return to sitting is not enough: a badly calibrated engine never
            reaches sitting, so it could never correct itself.
        calibration_reset_after_suspension_ms: Tracking loss longer than this
            discards the heights gathered so far. Hip height in image units
            says nothing about position in the room, so once the participant
            has been out of view long enough to have moved, earlier
            observations are not comparable with later ones. On a real
            recording a 1.6 second loss separated two phases whose hip
            heights differed by 0.19 -- more than a whole repetition's
            travel -- and mixing them made every repetition uncountable.
        calibration_requires_good_quality: Draw calibration only from frames
            at GOOD pose quality. Calibration sets the scale every later
            decision is measured against, so it must not be built from
            frames the quality layer already distrusts. Observed on a real
            recording: sampling DEGRADED frames while the participant walked
            into shot produced a travel of 0.042 against a true 0.133, and
            every subsequent repetition was missed.
        calibration_refine: Recompute calibration each time the participant
            returns to sitting. The initial estimate is necessarily taken
            part-way through the first rise, the moment enough travel has
            been seen, so it understates the true range: measured 0.042
            against a true 0.133 on a real recording, which compressed the
            scale threefold and made rise and descent times meaningless even
            though the count was right. Refining only at SEATED means the
            scale never changes during a repetition.
        quality_recovery_frames: Consecutive scorable frames before scoring
            resumes after a pose-quality interruption.
    """

    target_repetitions: Optional[int] = None

    rising_enter: float = 0.25
    standing_enter: float = 0.80
    standing_exit: float = 0.65
    seated_enter: float = 0.20

    minimum_dwell_ms: float = 100.0
    minimum_rise_velocity: float = 0.02

    minimum_rep_seconds: float = 0.8
    maximum_rep_seconds: float = 20.0
    rapid_descent_seconds: float = 0.5

    calibration_minimum_travel: float = 0.04
    calibration_low_percentile: float = 0.05
    calibration_high_percentile: float = 0.95
    calibration_window: int = 300
    calibration_requires_good_quality: bool = True
    calibration_refine: bool = True
    calibration_refine_interval_frames: int = 15
    calibration_reset_after_suspension_ms: float = 1000.0
    calibration_report_change: float = 0.05
    calibration_method: str = "cluster"
    calibration_cluster_minimum_samples: int = 30

    quality_recovery_frames: int = 5

    def validate(self) -> None:
        """Check the threshold ordering that hysteresis depends on."""
        if not self.seated_enter < self.rising_enter:
            raise ValueError("seated_enter must be below rising_enter.")
        if not self.standing_exit < self.standing_enter:
            raise ValueError(
                "standing_exit must be below standing_enter to give hysteresis."
            )
        if not self.rising_enter < self.standing_exit:
            raise ValueError("rising_enter must be below standing_exit.")
        if self.minimum_rep_seconds >= self.maximum_rep_seconds:
            raise ValueError("minimum_rep_seconds must be below maximum_rep_seconds.")


@dataclass
class _Repetition:
    """A repetition being assembled."""

    sequence: int
    started_ms: float
    stood_ms: Optional[float] = None
    descent_started_ms: Optional[float] = None
    completed_ms: Optional[float] = None
    peak_normalised: float = 0.0
    minimum_knee_angle: Optional[float] = None
    maximum_trunk_angle: Optional[float] = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sequence": self.sequence,
            "started_at_ms": round(self.started_ms, 1),
            "peak_normalised_height": round(self.peak_normalised, 3),
        }
        if self.completed_ms is not None:
            data["completed_at_ms"] = round(self.completed_ms, 1)
            data["duration_seconds"] = round(
                (self.completed_ms - self.started_ms) / 1000.0, 3
            )
        if self.stood_ms is not None:
            data["rise_time_seconds"] = round(
                (self.stood_ms - self.started_ms) / 1000.0, 3
            )
            if self.descent_started_ms is not None:
                # Time held upright, separate from the descent itself.
                data["standing_time_seconds"] = round(
                    (self.descent_started_ms - self.stood_ms) / 1000.0, 3
                )
        if self.completed_ms is not None and self.descent_started_ms is not None:
            data["descent_time_seconds"] = round(
                (self.completed_ms - self.descent_started_ms) / 1000.0, 3
            )
        if self.minimum_knee_angle is not None:
            data["minimum_knee_angle_degrees"] = round(self.minimum_knee_angle, 1)
        if self.maximum_trunk_angle is not None:
            data["maximum_trunk_angle_degrees"] = round(self.maximum_trunk_angle, 1)
        if self.flags:
            data["quality_flags"] = list(self.flags)
        return data


class SitToStandEngine(ExerciseEngine):
    """Deterministic sit-to-stand recogniser.

    Calibration is drawn from the participant's own movement. Scoring
    therefore begins only once a full excursion has been observed, which means
    the cycle used to calibrate is not counted. That is a deliberate trade:
    the alternative is scoring the first repetition against thresholds that
    are still guesses.
    """

    def __init__(self, config: Optional[StsConfig] = None) -> None:
        self._config = config or StsConfig()
        self._config.validate()
        self._state = StsState.NO_PERSON
        self._calibration: Optional[StsCalibration] = None
        self._calibration_is_explicit = False
        self._heights: list[float] = []
        self._candidate: Optional[StsState] = None
        self._candidate_since_ms: Optional[float] = None
        self._current: Optional[_Repetition] = None
        self._completed: list[_Repetition] = []
        self._attempted = 0
        self._partial = 0
        self._first_ms: Optional[float] = None
        self._last_ms: Optional[float] = None
        self._quality_status: Optional[PoseQualityStatus] = None
        self._recovery_frames = 0
        self._frames_since_refine = 0
        self._suspended_reason: Optional[str] = None
        self._suspended_at_ms: Optional[float] = None
        self._worst_quality = PoseQualityStatus.GOOD
        self._stopped = False

    # ---------------------------------------------------------------- state

    @property
    def state(self) -> StsState:
        return self._state

    @property
    def calibration(self) -> Optional[StsCalibration]:
        return self._calibration

    @property
    def valid_repetitions(self) -> int:
        return len(self._completed)

    # ------------------------------------------------------------ lifecycle

    def initialise(self, calibration: Optional[StsCalibration] = None) -> list[Event]:
        self.__init__(self._config)  # type: ignore[misc]
        self._calibration = calibration
        self._calibration_is_explicit = calibration is not None
        events: list[Event] = []
        if calibration is not None:
            events.append(
                self._event(
                    EventType.CALIBRATED, 0.0, payload=calibration.to_dict()
                )
            )
        return events

    def pause(self, reason: str) -> list[Event]:
        if self._state is StsState.SUSPENDED:
            return []
        events = self._abandon_repetition(self._last_ms or 0.0, reason)
        self._suspended_reason = reason
        self._suspended_at_ms = self._last_ms
        self._state = StsState.SUSPENDED
        self._candidate = None
        events.append(
            self._event(
                EventType.EXERCISE_PAUSED, self._last_ms or 0.0,
                payload={"reason": reason},
            )
        )
        return events

    def resume(self) -> list[Event]:
        if self._state is not StsState.SUSPENDED:
            return []
        now = self._last_ms or 0.0
        away_ms = now - (self._suspended_at_ms or now)
        if (
            not self._calibration_is_explicit
            and away_ms >= self._config.calibration_reset_after_suspension_ms
        ):
            # Long enough to have moved. Heights gathered before the
            # interruption describe a position that may no longer apply.
            self._heights.clear()
        self._suspended_reason = None
        self._suspended_at_ms = None
        self._recovery_frames = 0
        self._state = StsState.NO_PERSON
        return [self._event(EventType.EXERCISE_RESUMED, now)]

    def stop(self) -> list[Event]:
        if self._stopped:
            return []
        self._stopped = True
        now = self._last_ms or 0.0
        events = self._abandon_repetition(now, "exercise_stopped")
        target = self._config.target_repetitions
        completed = target is not None and len(self._completed) >= target
        events.append(
            self._event(
                EventType.EXERCISE_COMPLETED if completed else EventType.EXERCISE_STOPPED,
                now,
                payload={"valid_repetitions": len(self._completed)},
            )
        )
        return events

    # --------------------------------------------------------------- update

    def update(
        self,
        pose: PoseFrame,
        features: FeatureSet,
        quality: PoseQualityReport,
    ) -> list[Event]:
        now = features.timestamp_ms
        if self._first_ms is None:
            self._first_ms = now
        self._last_ms = now

        events = self._track_quality(quality, now)
        if self._state is StsState.SUSPENDED or self._stopped:
            return events

        hip_height = features.value(HIP_HEIGHT)
        if hip_height is None:
            events.extend(self._handle_missing(now))
            return events

        if self._state is StsState.NO_PERSON:
            events.append(self._event(EventType.PARTICIPANT_DETECTED, now))
            self._state = StsState.CALIBRATING

        self._observe_height(hip_height, quality)
        if self._calibration is None:
            events.extend(self._calibrate(now))
            if self._calibration is None:
                return events

        events.extend(self._expire_stalled_repetition(now))
        events.extend(self._maybe_refine(now))

        normalised = self._calibration.normalise(hip_height)
        if normalised is None:
            return events

        if self._state is StsState.CALIBRATING:
            self._state = (
                StsState.STANDING
                if normalised >= self._config.standing_enter
                else StsState.SEATED
            )
            events.append(self._event(EventType.EXERCISE_READY, now))

        self._record_rep_detail(features, normalised)
        events.extend(self._advance(normalised, features, now))
        return events

    # ---------------------------------------------------------- transitions

    def _advance(
        self, normalised: float, features: FeatureSet, now: float
    ) -> list[Event]:
        config = self._config
        velocity = features.value(HIP_VERTICAL_VELOCITY) or 0.0
        target: Optional[StsState] = None

        if self._state is StsState.SEATED:
            if normalised > config.rising_enter and velocity > config.minimum_rise_velocity:
                target = StsState.RISING
        elif self._state is StsState.RISING:
            if normalised >= config.standing_enter:
                target = StsState.STANDING
            elif normalised <= config.seated_enter:
                target = StsState.SEATED
        elif self._state is StsState.STANDING:
            if normalised < config.standing_exit:
                target = StsState.DESCENDING
        elif self._state is StsState.DESCENDING:
            if normalised <= config.seated_enter:
                target = StsState.SEATED
            elif normalised >= config.standing_enter:
                target = StsState.STANDING

        if target is None:
            self._candidate = None
            self._candidate_since_ms = None
            return []

        if self._candidate is not target:
            self._candidate = target
            self._candidate_since_ms = now
            return []
        if self._candidate_since_ms is None:
            self._candidate_since_ms = now
            return []
        if now - self._candidate_since_ms < config.minimum_dwell_ms:
            return []

        self._candidate = None
        self._candidate_since_ms = None
        return self._enter(target, now)

    def _enter(self, state: StsState, now: float) -> list[Event]:
        previous, self._state = self._state, state
        events = [
            self._event(
                EventType.STATE_CHANGED,
                now,
                payload={"from": previous.value, "to": state.value},
            )
        ]

        if state is StsState.RISING and previous is StsState.SEATED:
            self._attempted += 1
            self._current = _Repetition(sequence=self._attempted, started_ms=now)
            events.append(self._event(EventType.REP_STARTED, now, self._attempted))

        elif state is StsState.STANDING and previous is StsState.RISING:
            if self._current is not None:
                self._current.stood_ms = now
            events.append(
                self._event(
                    EventType.TARGET_POSITION_REACHED, now,
                    self._current.sequence if self._current else None,
                )
            )

        elif state is StsState.DESCENDING and self._current is not None:
            # Recorded on every entry to DESCENDING, so a participant who
            # dips and stands again has the final descent timed, not the
            # first.
            self._current.descent_started_ms = now

        elif state is StsState.SEATED and previous is StsState.RISING:
            events.extend(self._partial_repetition(now))

        elif state is StsState.SEATED and previous is StsState.DESCENDING:
            events.extend(self._complete_repetition(now))

        if state is StsState.SEATED:
            events.extend(self._refine_calibration(now))

        return events

    # -------------------------------------------------------- repetitions

    def _complete_repetition(self, now: float) -> list[Event]:
        rep = self._current
        self._current = None
        if rep is None or rep.stood_ms is None:
            return []

        duration_s = (now - rep.started_ms) / 1000.0
        if duration_s < self._config.minimum_rep_seconds:
            # Faster than a person can sit and stand: a detection artefact,
            # not a repetition. Rejecting these keeps false positives low,
            # which matters more than raw count accuracy (Document 03 §49).
            self._attempted = max(0, self._attempted - 1)
            return [
                self._event(
                    EventType.INVALID_REP, now, rep.sequence,
                    payload={"reason": "implausibly_short", "duration_seconds": round(duration_s, 3)},
                )
            ]
        if duration_s > self._config.maximum_rep_seconds:
            self._partial += 1
            return [
                self._event(
                    EventType.INVALID_REP, now, rep.sequence,
                    payload={"reason": "implausibly_long", "duration_seconds": round(duration_s, 3)},
                )
            ]

        rep.completed_ms = now
        descent_from = rep.descent_started_ms if rep.descent_started_ms else rep.stood_ms
        descent_s = (now - descent_from) / 1000.0
        events: list[Event] = []
        if descent_s < self._config.rapid_descent_seconds:
            rep.flags.append("rapid_descent")
            events.append(
                self._event(
                    EventType.QUALITY_FLAG, now, rep.sequence,
                    payload={"flag": "rapid_descent", "descent_time_seconds": round(descent_s, 3)},
                )
            )

        self._completed.append(rep)
        events.append(
            self._event(EventType.REP_COMPLETED, now, rep.sequence, payload=rep.to_dict())
        )

        target = self._config.target_repetitions
        if target is not None and len(self._completed) == target:
            events.append(
                self._event(
                    EventType.EXERCISE_COMPLETED, now,
                    payload={"valid_repetitions": len(self._completed)},
                )
            )
        return events

    def _partial_repetition(self, now: float) -> list[Event]:
        rep = self._current
        self._current = None
        if rep is None:
            return []
        self._partial += 1
        return [
            self._event(
                EventType.PARTIAL_REP, now, rep.sequence,
                payload={
                    "peak_normalised_height": round(rep.peak_normalised, 3),
                    "reason": "standing_not_reached",
                },
            )
        ]

    def _abandon_repetition(self, now: float, reason: str) -> list[Event]:
        """Discard an in-flight repetition without penalising the participant.

        Required by CLAUDE.md §7: when pose quality becomes INSUFFICIENT the
        incomplete action must not count against the participant. It is not
        recorded as a partial repetition, because nothing is known about
        whether it was completed.
        """
        rep = self._current
        if rep is None:
            return []
        self._current = None
        self._attempted = max(0, self._attempted - 1)
        return [
            self._event(
                EventType.INVALID_REP, now, rep.sequence,
                payload={"reason": reason, "not_counted": True},
            )
        ]

    def _record_rep_detail(self, features: FeatureSet, normalised: float) -> None:
        rep = self._current
        if rep is None:
            return
        rep.peak_normalised = max(rep.peak_normalised, normalised)
        knee = features.value(MEAN_KNEE_ANGLE)
        if knee is not None:
            rep.minimum_knee_angle = (
                knee if rep.minimum_knee_angle is None else min(rep.minimum_knee_angle, knee)
            )
        trunk = features.value(TRUNK_ANGLE)
        if trunk is not None:
            rep.maximum_trunk_angle = (
                abs(trunk)
                if rep.maximum_trunk_angle is None
                else max(rep.maximum_trunk_angle, abs(trunk))
            )

    # -------------------------------------------------------- calibration

    def _observe_height(self, hip_height: float, quality: PoseQualityReport) -> None:
        """Retain a hip height for calibration, if it can be trusted."""
        if (
            self._config.calibration_requires_good_quality
            and quality.status is not PoseQualityStatus.GOOD
        ):
            return
        self._heights.append(hip_height)
        if len(self._heights) > self._config.calibration_window:
            self._heights.pop(0)

    def _estimate(self) -> Optional[StsCalibration]:
        """Estimate seated and standing heights from observed movement."""
        config = self._config
        if len(self._heights) < 10:
            return None

        if (
            config.calibration_method == "cluster"
            and len(self._heights) >= config.calibration_cluster_minimum_samples
        ):
            low, high = _cluster_reference(self._heights)
            source = "movement_cluster"
        else:
            ordered = sorted(self._heights)
            last = len(ordered) - 1
            low = ordered[min(int(config.calibration_low_percentile * len(ordered)), last)]
            high = ordered[min(int(config.calibration_high_percentile * len(ordered)), last)]
            source = "movement_percentile"

        if high - low < config.calibration_minimum_travel:
            return None
        return StsCalibration(
            seated_hip_height=low,
            standing_hip_height=high,
            source=source,
            samples=len(self._heights),
        )

    def _calibrate(self, now: float) -> list[Event]:
        estimate = self._estimate()
        if estimate is None:
            return []
        self._calibration = estimate
        return [self._event(EventType.CALIBRATED, now, payload=estimate.to_dict())]

    def _expire_stalled_repetition(self, now: float) -> list[Event]:
        """Abandon a repetition that has been in progress implausibly long.

        Without this a repetition can stay in flight indefinitely, and that
        is not merely untidy: an in-flight repetition blocks calibration
        refinement, and bad calibration is the very thing that prevents the
        repetition from ever completing. The two deadlock each other, and the
        engine counts nothing for the rest of the attempt.
        """
        rep = self._current
        if rep is None:
            return []
        if now - rep.started_ms <= self._config.maximum_rep_seconds * 1000.0:
            return []
        self._state = (
            StsState.SEATED if self._state is StsState.RISING else self._state
        )
        return self._abandon_repetition(now, "repetition_stalled")

    def _maybe_refine(self, now: float) -> list[Event]:
        """Recompute calibration periodically between repetitions.

        Never while a repetition is in progress, so the scale a repetition is
        measured against cannot change part-way through it.
        """
        if self._current is not None:
            self._frames_since_refine = 0
            return []
        self._frames_since_refine += 1
        if self._frames_since_refine < self._config.calibration_refine_interval_frames:
            return []
        self._frames_since_refine = 0
        return self._refine_calibration(now)

    def _refine_calibration(self, now: float) -> list[Event]:
        """Replace calibration with a better-informed estimate."""
        if not self._config.calibration_refine or self._calibration is None:
            return []
        if self._calibration_is_explicit:
            # Calibration the caller supplied is authoritative. Quietly
            # replacing it would make a prescribed or previously measured
            # reference silently ineffective.
            return []
        estimate = self._estimate()
        if estimate is None:
            return []
        previous = self._calibration
        if estimate.to_dict() == previous.to_dict():
            return []
        # Replaces in either direction. An earlier "only widen" rule was
        # needed while calibration came from percentiles, where a shallow
        # stand could shrink the range. Cluster medians are computed from
        # every frame observed so far and move little with one odd
        # repetition, so a later estimate is simply better informed --
        # including when it is narrower, which is exactly what corrects a
        # range inflated by walking about.
        self._calibration = estimate
        # Refinement runs several times a second, and almost every run shifts
        # the estimate a little. Announcing each one buried the event stream
        # in 68 calibration events for a single session, so only a material
        # change is reported. The calibration itself always updates.
        if previous.travel > 0:
            change = abs(estimate.travel - previous.travel) / previous.travel
            if change < self._config.calibration_report_change:
                return []
        return [self._event(EventType.CALIBRATED, now, payload=estimate.to_dict())]

    # ------------------------------------------------------------- quality

    def _track_quality(self, quality: PoseQualityReport, now: float) -> list[Event]:
        events: list[Event] = []
        if quality.status is not self._quality_status:
            if quality.status is PoseQualityStatus.INSUFFICIENT:
                events.append(self._event(EventType.POSE_QUALITY_INSUFFICIENT, now))
            elif quality.status is PoseQualityStatus.DEGRADED:
                events.append(self._event(EventType.POSE_QUALITY_DEGRADED, now))
            elif self._quality_status is not None:
                events.append(self._event(EventType.POSE_QUALITY_RESTORED, now))
            self._quality_status = quality.status

        if _severity(quality.status) > _severity(self._worst_quality):
            self._worst_quality = quality.status

        if quality.status is PoseQualityStatus.INSUFFICIENT:
            if self._state is not StsState.SUSPENDED:
                events.extend(self.pause("pose_quality_insufficient"))
            self._recovery_frames = 0
        elif self._state is StsState.SUSPENDED and self._suspended_reason == (
            "pose_quality_insufficient"
        ):
            self._recovery_frames += 1
            if self._recovery_frames >= self._config.quality_recovery_frames:
                events.extend(self.resume())
        return events

    def _handle_missing(self, now: float) -> list[Event]:
        if self._state in (StsState.NO_PERSON, StsState.SUSPENDED):
            return []
        events = self._abandon_repetition(now, "participant_lost")
        self._state = StsState.NO_PERSON
        self._candidate = None
        events.append(self._event(EventType.PARTICIPANT_LOST, now))
        return events

    # -------------------------------------------------------------- result

    def result(self) -> ExerciseResult:
        durations = [
            (r.completed_ms - r.started_ms) / 1000.0
            for r in self._completed
            if r.completed_ms is not None
        ]
        rises = [
            (r.stood_ms - r.started_ms) / 1000.0
            for r in self._completed
            if r.stood_ms is not None
        ]
        descents = [
            (r.completed_ms - r.descent_started_ms) / 1000.0
            for r in self._completed
            if r.completed_ms is not None and r.descent_started_ms is not None
        ]
        standing_times = [
            (r.descent_started_ms - r.stood_ms) / 1000.0
            for r in self._completed
            if r.descent_started_ms is not None and r.stood_ms is not None
        ]
        flags: dict[str, int] = {}
        for rep in self._completed:
            for flag in rep.flags:
                flags[flag] = flags.get(flag, 0) + 1

        metrics: dict[str, Any] = {}
        if durations:
            metrics["mean_rep_duration_seconds"] = round(sum(durations) / len(durations), 3)
            metrics["fastest_rep_seconds"] = round(min(durations), 3)
            metrics["slowest_rep_seconds"] = round(max(durations), 3)
        if rises:
            metrics["mean_rise_time_seconds"] = round(sum(rises) / len(rises), 3)
        if descents:
            metrics["mean_descent_time_seconds"] = round(sum(descents) / len(descents), 3)
        if standing_times:
            metrics["mean_standing_time_seconds"] = round(
                sum(standing_times) / len(standing_times), 3
            )
        if self._calibration is not None:
            metrics["calibration"] = self._calibration.to_dict()

        target = self._config.target_repetitions
        if self._stopped:
            outcome = (
                "completed"
                if target is not None and len(self._completed) >= target
                else "stopped"
            )
        else:
            outcome = "in_progress"

        duration_s = 0.0
        if self._first_ms is not None and self._last_ms is not None:
            duration_s = (self._last_ms - self._first_ms) / 1000.0

        return ExerciseResult(
            exercise_id=EXERCISE_ID,
            exercise_specification_version=SPECIFICATION_VERSION,
            exercise_algorithm_version=ALGORITHM_VERSION,
            attempted_repetitions=self._attempted,
            valid_repetitions=len(self._completed),
            partial_repetitions=self._partial,
            target_repetitions=target,
            duration_seconds=duration_s,
            metrics=metrics,
            quality_flags=flags,
            pose_quality=self._worst_quality.value.lower(),
            repetitions=[r.to_dict() for r in self._completed],
            outcome=outcome,
        )

    # -------------------------------------------------------------- helper

    def _event(
        self,
        event_type: EventType,
        timestamp_ms: float,
        sequence: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> Event:
        return Event(
            event=event_type,
            timestamp_ms=timestamp_ms,
            exercise_id=EXERCISE_ID,
            sequence=sequence,
            payload=payload or {},
        )


def _cluster_reference(heights: list[float]) -> tuple[float, float]:
    """Split hip heights into a seated and a standing cluster.

    Sit-to-stand spends most of its time either seated or standing, with
    quick transitions between, so the distribution is bimodal. Walking to and
    from the camera is not: it spreads continuously, and it moves hip height
    a long way, because apparent height depends on distance from the camera.

    Percentiles cannot tell those apart. On a real recording where the
    participant walked in and out, the 5th-to-95th percentile spread was
    0.247 against a true repetition travel of 0.137, so repetitions reached
    only 0.55 of the calibrated range and none of them were counted.

    The split point is chosen to maximise between-cluster variance (Otsu's
    method), and each reference is the *median* of its cluster, which a tail
    of walking frames barely moves.
    """
    ordered = sorted(heights)
    count = len(ordered)
    prefix = [0.0]
    for value in ordered:
        prefix.append(prefix[-1] + value)
    total = prefix[-1]

    margin = max(1, count // 20)
    best_index, best_variance = count // 2, -1.0
    for index in range(margin, count - margin):
        weight_low = index / count
        weight_high = 1.0 - weight_low
        mean_low = prefix[index] / index
        mean_high = (total - prefix[index]) / (count - index)
        variance = weight_low * weight_high * (mean_low - mean_high) ** 2
        if variance > best_variance:
            best_variance, best_index = variance, index

    lower, upper = ordered[:best_index], ordered[best_index:]
    return _median(lower), _median(upper)


def _median(values: list[float]) -> float:
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def _severity(status: PoseQualityStatus) -> int:
    return {
        PoseQualityStatus.GOOD: 0,
        PoseQualityStatus.DEGRADED: 1,
        PoseQualityStatus.INSUFFICIENT: 2,
    }[status]
