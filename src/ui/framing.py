"""Camera framing assessment for setup.

Pose quality says *that* a frame is unscorable. Framing says *what to do about
it*: the participant is too close, or cut off at the bottom, or out to one
side. Two development recordings were largely wasted because the lower body
was outside the frame and there was no way to tell until afterwards.

This is the developer-mode ancestor of the participant camera check in
Document 05 §7.2. It stays deliberately geometric and produces a message key
rather than a sentence, so participant wording can live in the feedback layer
later (Document 03 §45) rather than being baked in here.

Left and right are deliberately not used. Frames are mirrored by default, and
"step left" is ambiguous when someone is watching a mirror image of
themselves. An arrow pointing toward the centre of the frame is unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from src.pose.models import LEFT_ANKLE, NOSE, RIGHT_ANKLE, PoseFrame


class Framing(str, Enum):
    """What the participant should do to be seen properly."""

    GOOD = "GOOD"
    NO_PERSON = "NO_PERSON"
    MOVE_BACK = "MOVE_BACK"
    MOVE_CLOSER = "MOVE_CLOSER"
    MOVE_TO_CENTRE_LEFT = "MOVE_TO_CENTRE_LEFT"
    MOVE_TO_CENTRE_RIGHT = "MOVE_TO_CENTRE_RIGHT"


DISPLAY_TEXT: dict[Framing, str] = {
    Framing.GOOD: "GOOD POSITION",
    Framing.NO_PERSON: "STAND IN VIEW",
    Framing.MOVE_BACK: "MOVE BACK",
    Framing.MOVE_CLOSER: "MOVE CLOSER",
    Framing.MOVE_TO_CENTRE_LEFT: "<<  MOVE ACROSS",
    Framing.MOVE_TO_CENTRE_RIGHT: "MOVE ACROSS  >>",
}
"""Developer-mode wording. Participant wording belongs in the feedback layer."""

DEFAULT_MINIMUM_BODY_FILL = 0.45
"""Least of the image height the body should occupy.

Below this the participant is far enough away that landmark precision suffers
noticeably. It is a starting value to be checked against recordings, not a
validated threshold.
"""


@dataclass(frozen=True)
class FramingHint:
    """A framing verdict and the evidence behind it.

    Attributes:
        status: What to do.
        body_fill: Fraction of image height between the highest and lowest
            visible required landmark, or None if not measurable.
        cut_off_below: Required landmarks past the bottom edge.
        cut_off_above: Required landmarks past the top edge.
        outside_sides: Required landmarks past the left or right edge.
    """

    status: Framing
    body_fill: Optional[float] = None
    cut_off_below: list[str] = field(default_factory=list)
    cut_off_above: list[str] = field(default_factory=list)
    outside_sides: list[str] = field(default_factory=list)

    @property
    def is_good(self) -> bool:
        return self.status is Framing.GOOD

    @property
    def text(self) -> str:
        return DISPLAY_TEXT[self.status]


def assess_framing(
    pose: PoseFrame,
    required: Sequence[str],
    margin: float = 0.02,
    minimum_body_fill: float = DEFAULT_MINIMUM_BODY_FILL,
) -> FramingHint:
    """Decide what the participant should do to be framed properly.

    Args:
        pose: The canonical pose to judge.
        required: Landmarks that must be visible, from pose-quality config.
        margin: Normalised distance from an edge treated as cut off.
        minimum_body_fill: Least acceptable body height as a fraction of the
            image.

    Only landmarks the engine actually reported are considered. A pose engine
    that extrapolates off-screen positions at near-zero confidence — MediaPipe
    does — still yields coordinates, and those coordinates are precisely the
    evidence that someone is out of frame, so they are used rather than
    filtered out.
    """
    if not pose.has_person:
        return FramingHint(status=Framing.NO_PERSON)

    # The nose matters for framing even when it is not required for scoring:
    # a head out of shot means the camera is too close or too low.
    names = [name for name in list(required) + [NOSE] if name in pose.landmarks]
    if not names:
        return FramingHint(status=Framing.NO_PERSON)

    below = [n for n in names if pose.landmarks[n].y > 1.0 - margin]
    above = [n for n in names if pose.landmarks[n].y < margin]
    off_left = [n for n in names if pose.landmarks[n].x < margin]
    off_right = [n for n in names if pose.landmarks[n].x > 1.0 - margin]

    ys = [pose.landmarks[n].y for n in names]
    body_fill = max(ys) - min(ys)

    hint = dict(
        body_fill=body_fill,
        cut_off_below=below,
        cut_off_above=above,
        outside_sides=off_left + off_right,
    )

    # Vertical fit first: someone cut off at both ends cannot be fixed by
    # moving sideways, and legs matter more than sway for these exercises.
    if below or above:
        return FramingHint(status=Framing.MOVE_BACK, **hint)
    if off_left and not off_right:
        return FramingHint(status=Framing.MOVE_TO_CENTRE_RIGHT, **hint)
    if off_right and not off_left:
        return FramingHint(status=Framing.MOVE_TO_CENTRE_LEFT, **hint)
    if off_left and off_right:
        return FramingHint(status=Framing.MOVE_BACK, **hint)
    if body_fill < minimum_body_fill:
        return FramingHint(status=Framing.MOVE_CLOSER, **hint)
    return FramingHint(status=Framing.GOOD, **hint)


def ankles_visible(pose: PoseFrame, margin: float = 0.02) -> bool:
    """Whether both ankles are genuinely inside the frame.

    Reported separately because ankles were the first thing lost in both
    development recordings, and they are what stepping and stance-width
    features depend on.
    """
    for name in (LEFT_ANKLE, RIGHT_ANKLE):
        landmark = pose.get(name)
        if landmark is None or not margin <= landmark.y <= 1.0 - margin:
            return False
    return True
