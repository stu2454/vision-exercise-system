"""Structured exercise events (Document 03 §22, ADR-009).

Exercise engines emit events. The UI, feedback engine and storage subscribe to
them and never inspect state-machine internals. This is what keeps movement
interpretation separate from product behaviour: changing how a repetition is
detected must not require touching anything that consumes `rep_completed`.

Events carry a monotonic timestamp, not wall-clock time (Document 03 §24).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """The event vocabulary from Document 03 §22 and CLAUDE.md §15."""

    PARTICIPANT_DETECTED = "participant_detected"
    PARTICIPANT_LOST = "participant_lost"

    POSE_QUALITY_DEGRADED = "pose_quality_degraded"
    POSE_QUALITY_INSUFFICIENT = "pose_quality_insufficient"
    POSE_QUALITY_RESTORED = "pose_quality_restored"

    EXERCISE_READY = "exercise_ready"
    EXERCISE_STARTED = "exercise_started"
    EXERCISE_PAUSED = "exercise_paused"
    EXERCISE_RESUMED = "exercise_resumed"

    CALIBRATED = "calibrated"
    STATE_CHANGED = "state_changed"

    REP_STARTED = "rep_started"
    TARGET_POSITION_REACHED = "target_position_reached"
    REP_COMPLETED = "rep_completed"
    PARTIAL_REP = "partial_rep"
    INVALID_REP = "invalid_rep"

    SUPPORT_USED = "support_used"
    QUALITY_FLAG = "quality_flag"
    SAFETY_FLAG = "safety_flag"

    EXERCISE_COMPLETED = "exercise_completed"
    EXERCISE_STOPPED = "exercise_stopped"


@dataclass(frozen=True)
class Event:
    """One thing that happened during an exercise.

    Attributes:
        event: What happened.
        timestamp_ms: Monotonic time from the frame source.
        exercise_id: Which exercise emitted it, e.g. "STS-001".
        sequence: Repetition number where the event concerns one.
        payload: Event-specific detail. Plain JSON-compatible values only,
            so events remain language-neutral (Document 03 §6).
    """

    event: EventType
    timestamp_ms: float
    exercise_id: str
    sequence: Optional[int] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": self.event.value,
            "timestamp_ms": self.timestamp_ms,
            "exercise_id": self.exercise_id,
        }
        if self.sequence is not None:
            data["sequence"] = self.sequence
        if self.payload:
            data["payload"] = dict(self.payload)
        return data
