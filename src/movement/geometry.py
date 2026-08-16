"""Geometric primitives for movement features.

Coordinate basis
----------------
Canonical landmarks are image-normalised: x is divided by image width, y by
image height. Those are different divisors, so the space is anisotropic and
any angle or distance computed directly in it is wrong by the aspect ratio.
On a 1280x720 frame, horizontal distances are compressed by 0.5625.

This is not theoretical. Estimating camera view from raw normalised shoulder
width during development gave a shoulder-to-torso ratio of 0.47 and the
conclusion "every take is oblique". Corrected, the same takes gave 0.83-0.88,
which is anatomically ordinary, and only one take was actually oblique.

Everything here therefore works in **image heights**: both axes divided by the
image height, so x spans 0 to width/height and y spans 0 to 1. The space is
isotropic, angles are true, and distances are comparable between axes. Values
remain resolution-independent, so a 1280x720 and a 1920x1080 recording of the
same movement produce the same numbers.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from src.pose.models import Landmark, PoseFrame

Point = Tuple[float, float]

DEFAULT_ASPECT = 16.0 / 9.0
"""Aspect ratio assumed when a pose frame does not carry its image size.

Pose streams recorded before image size was retained fall back to this. It is
the shape of every recording this project has made.
"""


def aspect_ratio(pose: PoseFrame) -> float:
    """Width divided by height for the frame this pose came from."""
    if pose.image_width and pose.image_height:
        return pose.image_width / pose.image_height
    return DEFAULT_ASPECT


def to_point(landmark: Landmark, aspect: float) -> Point:
    """Convert a landmark to isotropic image-height units."""
    return (landmark.x * aspect, landmark.y)


def point_of(pose: PoseFrame, name: str, aspect: Optional[float] = None) -> Optional[Point]:
    """Isotropic position of a canonical landmark, or None if absent."""
    landmark = pose.get(name)
    if landmark is None:
        return None
    return to_point(landmark, aspect if aspect is not None else aspect_ratio(pose))


def distance(first: Point, second: Point) -> float:
    """Euclidean distance in image heights."""
    return math.hypot(second[0] - first[0], second[1] - first[1])


def midpoint(first: Point, second: Point) -> Point:
    return ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)


def angle_at(first: Point, vertex: Point, second: Point) -> Optional[float]:
    """Interior angle at `vertex` in degrees, or None if degenerate.

    Returned in the range 0 to 180. For a knee this is the hip-knee-ankle
    angle: roughly 180 degrees standing, smaller when flexed.

    This is a projected angle measured in the image plane, not the true
    three-dimensional joint angle. A frontal camera foreshortens knee flexion
    badly: a seated knee that is anatomically near 90 degrees reads closer to
    120-135 degrees. Useful for detecting change, not for reporting joint
    angles (Document 04 measurement levels).
    """
    ax, ay = first[0] - vertex[0], first[1] - vertex[1]
    bx, by = second[0] - vertex[0], second[1] - vertex[1]
    magnitude = math.hypot(ax, ay) * math.hypot(bx, by)
    if magnitude <= 1e-9:
        return None
    cosine = (ax * bx + ay * by) / magnitude
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def tilt_from_vertical(lower: Point, upper: Point) -> Optional[float]:
    """Tilt of the `lower`-to-`upper` vector away from vertical, in degrees.

    Zero is upright. Positive leans towards increasing x, which is to the
    right of the image as displayed.

    Only tilt within the image plane is observable. From a frontal camera this
    measures lateral lean and is blind to forward lean; from a lateral camera
    the reverse. Interpreting it therefore requires knowing the camera view,
    which is why view is recorded with every take (Document 03 §10).
    """
    dx = upper[0] - lower[0]
    dy = upper[1] - lower[1]
    # y increases downward, so an upright torso has a negative dy.
    if math.hypot(dx, dy) <= 1e-9:
        return None
    return math.degrees(math.atan2(dx, -dy))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
