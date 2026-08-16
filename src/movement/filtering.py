"""Temporal filtering of pose data.

Raw frame-by-frame landmarks must not drive exercise decisions (CLAUDE.md §8).
They jitter enough to cross any threshold repeatedly within a single held
posture.

Every filter here is **timestamp-aware** rather than frame-counting. Measured
capture rates in this project have ranged from 27.9 to 29.9 fps within single
sessions, and a filter tuned in frames silently changes strength when the rate
drifts. Expressing smoothing as a time constant keeps behaviour identical
across machines and across a Raspberry Pi running slower than a laptop.

Filtering is configurable and bypassable: `PassThroughFilter` is a real
option, so developer mode can see unfiltered data (CLAUDE.md §8).

Filters never invent data. When a landmark disappears for longer than
`max_gap_ms`, its filter state is discarded rather than blended across the
gap, because averaging across a tracking loss fabricates movement that did
not happen.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from src.pose.models import Landmark, PoseFrame


class ScalarFilter(ABC):
    """Smooths a single scalar signal sampled at irregular intervals."""

    @abstractmethod
    def update(self, value: float, timestamp_ms: float) -> float:
        """Add a sample and return the filtered value."""

    @abstractmethod
    def reset(self) -> None:
        """Discard all history."""

    @abstractmethod
    def copy(self) -> "ScalarFilter":
        """A new filter with the same settings and no history."""


class PassThroughFilter(ScalarFilter):
    """No smoothing. The bypass required for developer inspection."""

    def update(self, value: float, timestamp_ms: float) -> float:
        return value

    def reset(self) -> None:
        return None

    def copy(self) -> "PassThroughFilter":
        return PassThroughFilter()


class ExponentialMovingAverageFilter(ScalarFilter):
    """Time-constant exponential smoothing.

    The weight given to each new sample is derived from the elapsed time,
    `alpha = 1 - exp(-dt / tau)`, so a dropped frame does not change how much
    smoothing is applied per unit time.

    `time_constant_ms` is the lag: larger is smoother and slower to respond.
    This is the default because it is the simplest thing that removes
    meaningful jitter, which is what the project asks for before anything
    more elaborate.
    """

    def __init__(self, time_constant_ms: float = 80.0) -> None:
        if time_constant_ms <= 0:
            raise ValueError("time_constant_ms must be positive.")
        self._tau_ms = time_constant_ms
        self._value: Optional[float] = None
        self._last_ms: Optional[float] = None

    def update(self, value: float, timestamp_ms: float) -> float:
        if self._value is None or self._last_ms is None:
            self._value, self._last_ms = value, timestamp_ms
            return value
        elapsed = timestamp_ms - self._last_ms
        self._last_ms = timestamp_ms
        if elapsed <= 0:
            return self._value
        alpha = 1.0 - math.exp(-elapsed / self._tau_ms)
        self._value += alpha * (value - self._value)
        return self._value

    def reset(self) -> None:
        self._value = None
        self._last_ms = None

    def copy(self) -> "ExponentialMovingAverageFilter":
        return ExponentialMovingAverageFilter(self._tau_ms)


class MovingMedianFilter(ScalarFilter):
    """Median of the most recent samples.

    Rejects isolated outliers outright rather than averaging them in, which
    suits landmark data where a single frame occasionally jumps far from the
    body. Costs more lag than the moving average for the same window, and its
    window is in frames rather than time.
    """

    def __init__(self, window: int = 5) -> None:
        if window < 1:
            raise ValueError("window must be at least 1.")
        self._window = window
        self._values: Deque[float] = deque(maxlen=window)

    def update(self, value: float, timestamp_ms: float) -> float:
        self._values.append(value)
        ordered = sorted(self._values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2.0

    def reset(self) -> None:
        self._values.clear()

    def copy(self) -> "MovingMedianFilter":
        return MovingMedianFilter(self._window)


class OneEuroFilter(ScalarFilter):
    """Adaptive filter that smooths less as the signal moves faster.

    Smoothing that is acceptable while a posture is held introduces lag that
    matters during a fast transition. The One Euro filter varies its cutoff
    with the estimated speed of the signal, so it is steady when still and
    responsive when moving.

    Kept available rather than default: it has three parameters to tune, and
    the simpler filter should be shown inadequate first.
    """

    def __init__(
        self,
        min_cutoff_hz: float = 1.0,
        beta: float = 0.007,
        derivative_cutoff_hz: float = 1.0,
    ) -> None:
        self._min_cutoff = min_cutoff_hz
        self._beta = beta
        self._d_cutoff = derivative_cutoff_hz
        self._value: Optional[float] = None
        self._derivative = 0.0
        self._last_ms: Optional[float] = None

    @staticmethod
    def _alpha(cutoff_hz: float, elapsed_s: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff_hz)
        return 1.0 / (1.0 + tau / elapsed_s)

    def update(self, value: float, timestamp_ms: float) -> float:
        if self._value is None or self._last_ms is None:
            self._value, self._last_ms = value, timestamp_ms
            self._derivative = 0.0
            return value
        elapsed_s = (timestamp_ms - self._last_ms) / 1000.0
        self._last_ms = timestamp_ms
        if elapsed_s <= 0:
            return self._value

        raw_derivative = (value - self._value) / elapsed_s
        d_alpha = self._alpha(self._d_cutoff, elapsed_s)
        self._derivative += d_alpha * (raw_derivative - self._derivative)

        cutoff = self._min_cutoff + self._beta * abs(self._derivative)
        alpha = self._alpha(cutoff, elapsed_s)
        self._value += alpha * (value - self._value)
        return self._value

    def reset(self) -> None:
        self._value = None
        self._derivative = 0.0
        self._last_ms = None

    def copy(self) -> "OneEuroFilter":
        return OneEuroFilter(self._min_cutoff, self._beta, self._d_cutoff)


FILTERS: dict[str, type[ScalarFilter]] = {
    "none": PassThroughFilter,
    "exponential_moving_average": ExponentialMovingAverageFilter,
    "moving_median": MovingMedianFilter,
    "one_euro": OneEuroFilter,
}


def make_filter(kind: str, **settings: float) -> ScalarFilter:
    """Build a filter by configuration name."""
    if kind not in FILTERS:
        raise ValueError(
            f"Unknown filter '{kind}'. Available: {', '.join(sorted(FILTERS))}."
        )
    if kind == "none":
        return PassThroughFilter()
    return FILTERS[kind](**settings)  # type: ignore[arg-type]


@dataclass(frozen=True)
class FilterSettings:
    """How landmark smoothing is configured."""

    kind: str = "exponential_moving_average"
    time_constant_ms: float = 80.0
    window: int = 5
    min_cutoff_hz: float = 1.0
    beta: float = 0.007
    derivative_cutoff_hz: float = 1.0
    max_gap_ms: float = 250.0

    def build(self) -> ScalarFilter:
        """Create one filter instance from these settings."""
        if self.kind == "exponential_moving_average":
            return ExponentialMovingAverageFilter(self.time_constant_ms)
        if self.kind == "moving_median":
            return MovingMedianFilter(self.window)
        if self.kind == "one_euro":
            return OneEuroFilter(self.min_cutoff_hz, self.beta, self.derivative_cutoff_hz)
        if self.kind == "none":
            return PassThroughFilter()
        raise ValueError(
            f"Unknown filter '{self.kind}'. Available: {', '.join(sorted(FILTERS))}."
        )


class PoseFilter:
    """Applies temporal smoothing to every landmark of a pose stream.

    Confidence is deliberately left unsmoothed. It is evidence about the
    current frame, and blurring it across time would make the pose-quality
    layer slower to notice that tracking has degraded.
    """

    def __init__(self, settings: Optional[FilterSettings] = None) -> None:
        self._settings = settings or FilterSettings()
        self._filters: dict[tuple[str, str], ScalarFilter] = {}
        self._last_seen_ms: dict[str, float] = {}

    @property
    def settings(self) -> FilterSettings:
        return self._settings

    def reset(self) -> None:
        """Discard all history. Required between replays for determinism."""
        self._filters.clear()
        self._last_seen_ms.clear()

    def apply(self, pose: PoseFrame) -> PoseFrame:
        """Return `pose` with smoothed landmark positions."""
        if not pose.has_person:
            # Nothing to smooth, and the gap logic below will discard stale
            # state once the person returns.
            return pose

        smoothed: dict[str, Landmark] = {}
        for name, landmark in pose.landmarks.items():
            self._discard_if_stale(name, pose.timestamp_ms)
            smoothed[name] = Landmark(
                x=self._filtered(name, "x", landmark.x, pose.timestamp_ms),
                y=self._filtered(name, "y", landmark.y, pose.timestamp_ms),
                z=(
                    None
                    if landmark.z is None
                    else self._filtered(name, "z", landmark.z, pose.timestamp_ms)
                ),
                confidence=landmark.confidence,
            )
            self._last_seen_ms[name] = pose.timestamp_ms

        return PoseFrame(
            timestamp_ms=pose.timestamp_ms,
            person_confidence=pose.person_confidence,
            landmarks=smoothed,
            source=pose.source,
            frame_index=pose.frame_index,
            image_width=pose.image_width,
            image_height=pose.image_height,
        )

    def _discard_if_stale(self, name: str, timestamp_ms: float) -> None:
        last = self._last_seen_ms.get(name)
        if last is None:
            return
        if timestamp_ms - last > self._settings.max_gap_ms:
            for axis in ("x", "y", "z"):
                self._filters.pop((name, axis), None)

    def _filtered(self, name: str, axis: str, value: float, timestamp_ms: float) -> float:
        key = (name, axis)
        if key not in self._filters:
            self._filters[key] = self._settings.build()
        return self._filters[key].update(value, timestamp_ms)
