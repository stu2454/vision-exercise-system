"""Gesture detection for participant-initiated control.

The problem this solves: calibration is participant-relative and only valid
while the participant stays at a fixed distance from the camera. Starting the
software and then walking into position guarantees that the walk itself is
part of the calibration data, which on a real recording moved hip height
further than a repetition does and made every repetition uncountable.

Letting the participant signal readiness inverts that. Nothing is observed
until they are standing where they intend to exercise.

Side labelling
--------------
Frames are mirrored before pose estimation by default, so MediaPipe sees a
mirrored person and its `right_*` landmarks correspond to the participant's
left arm. Rather than depend on which way round that is, either arm is
accepted. That is also the kinder instruction: a participant with a painful
or weak shoulder can use the other arm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.movement.geometry import angle_at, aspect_ratio, point_of
from src.pose.models import (
    LEFT_ELBOW,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_ELBOW,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    PoseFrame,
)

ARM_SIDES: tuple[tuple[str, str, str, str], ...] = (
    ("left", LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
    ("right", RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
)


@dataclass(frozen=True)
class ArmRaiseConfig:
    """What counts as a raised arm.

    Attributes:
        minimum_elbow_angle: Least elbow angle accepted, in degrees.
        maximum_elbow_angle: Greatest elbow angle accepted. Together these
            describe a bent arm: roughly a right angle, with enough latitude
            that nobody has to be precise about it. A straight arm overhead
            is excluded deliberately, because it is close to the arm
            positions that occur naturally while standing up.
        require_wrist_above_shoulder: The wrist must be higher than the
            shoulder. This is what separates a deliberate signal from an arm
            resting or swinging.
        minimum_confidence: Least landmark confidence for the arm to be
            judged at all.
        hold_ms: How long the position must be held. Guards against a
            transient pose being read as a signal.
    """

    minimum_elbow_angle: float = 50.0
    maximum_elbow_angle: float = 130.0
    require_wrist_above_shoulder: bool = True
    minimum_confidence: float = 0.60
    hold_ms: float = 800.0


@dataclass(frozen=True)
class ArmRaiseState:
    """What the detector currently sees.

    Attributes:
        raised: Whether an arm is in the signalling position this frame.
        side: Canonical side of the raised arm, if any. Subject to the
            mirroring caveat in the module docstring.
        held_ms: How long the position has been held.
        progress: Fraction of the required hold completed, 0.0 to 1.0.
        triggered: True on the frame the hold completes, and not again until
            the detector is reset.
    """

    raised: bool = False
    side: Optional[str] = None
    held_ms: float = 0.0
    progress: float = 0.0
    triggered: bool = False


def raised_arm_sides(pose: PoseFrame, config: ArmRaiseConfig) -> tuple[str, ...]:
    """Return the canonical sides of every raised, bent arm.

    Pure, so the geometry can be tested without any timing behaviour.
    """
    if not pose.has_person:
        return ()
    sides: list[str] = []
    aspect = aspect_ratio(pose)
    for side, shoulder_name, elbow_name, wrist_name in ARM_SIDES:
        landmarks = [pose.get(n) for n in (shoulder_name, elbow_name, wrist_name)]
        if any(landmark is None for landmark in landmarks):
            continue
        if min(landmark.confidence for landmark in landmarks) < config.minimum_confidence:
            continue

        shoulder = point_of(pose, shoulder_name, aspect)
        elbow = point_of(pose, elbow_name, aspect)
        wrist = point_of(pose, wrist_name, aspect)
        if shoulder is None or elbow is None or wrist is None:
            continue

        # y increases downwards, so "above" is a smaller y.
        if config.require_wrist_above_shoulder and wrist[1] >= shoulder[1]:
            continue
        angle = angle_at(shoulder, elbow, wrist)
        if angle is None:
            continue
        if config.minimum_elbow_angle <= angle <= config.maximum_elbow_angle:
            sides.append(side)
    return tuple(sides)


def arm_is_raised(pose: PoseFrame, config: ArmRaiseConfig) -> Optional[str]:
    """Return the side of one raised arm, or None."""
    sides = raised_arm_sides(pose, config)
    return sides[0] if sides else None


class ArmRaiseDetector:
    """Detects raised, bent arms held long enough to be deliberate.

    Timing comes from frame timestamps rather than a frame count, so the
    required hold is the same on a machine running at 15 fps as at 30.

    Args:
        config: What counts as a raised arm.
        required_arms: How many arms must be raised at once. One arm starts
            an exercise; two finish it. Using distinct gestures matters
            because the consequences differ — a start that fires by accident
            costs a moment, a stop that fires by accident ends the attempt —
            and both arms raised together is not a position that occurs
            while standing up from a chair.
    """

    def __init__(
        self, config: Optional[ArmRaiseConfig] = None, required_arms: int = 1
    ) -> None:
        if required_arms not in (1, 2):
            raise ValueError("required_arms must be 1 or 2.")
        self._config = config or ArmRaiseConfig()
        self._required_arms = required_arms
        self._since_ms: Optional[float] = None
        self._last_ms: Optional[float] = None
        self._fired = False

    @property
    def config(self) -> ArmRaiseConfig:
        return self._config

    def reset(self) -> None:
        """Forget progress, and allow the gesture to fire again."""
        self._since_ms = None
        self._last_ms = None
        self._fired = False

    def update(self, pose: PoseFrame) -> ArmRaiseState:
        """Advance the detector by one frame."""
        now = pose.timestamp_ms
        sides = raised_arm_sides(pose, self._config)

        if len(sides) < self._required_arms:
            self._since_ms = None
            self._last_ms = now
            return ArmRaiseState()
        side = "both" if len(sides) > 1 else sides[0]

        if self._since_ms is None:
            self._since_ms = now
        self._last_ms = now
        held_ms = now - self._since_ms
        progress = (
            1.0 if self._config.hold_ms <= 0 else min(1.0, held_ms / self._config.hold_ms)
        )

        triggered = False
        if held_ms >= self._config.hold_ms and not self._fired:
            triggered = True
            self._fired = True

        return ArmRaiseState(
            raised=True,
            side=side,
            held_ms=held_ms,
            progress=progress,
            triggered=triggered,
        )
