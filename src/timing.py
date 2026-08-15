"""Timing helpers.

All movement timing uses a monotonic clock (Document 03 §24). Wall-clock time
is reserved for record provenance.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Optional


class FpsMeter:
    """Rolling frame-rate estimate over a fixed window of recent frames.

    A rolling window is used rather than a cumulative average so the displayed
    rate reflects current conditions, which is what a developer watching for a
    slowdown needs.
    """

    def __init__(self, window: int = 30) -> None:
        if window < 2:
            raise ValueError("FpsMeter window must be at least 2 frames.")
        self._window = window
        self._times: Deque[float] = deque(maxlen=window)

    def tick(self) -> None:
        """Record that a frame has just been processed."""
        self._times.append(time.perf_counter())

    def reset(self) -> None:
        self._times.clear()

    @property
    def fps(self) -> Optional[float]:
        """Frames per second, or None until enough frames have been seen."""
        if len(self._times) < 2:
            return None
        elapsed = self._times[-1] - self._times[0]
        if elapsed <= 0:
            return None
        return (len(self._times) - 1) / elapsed


class RollingMean:
    """Rolling mean of a scalar, for latency display."""

    def __init__(self, window: int = 30) -> None:
        self._values: Deque[float] = deque(maxlen=window)

    def add(self, value: Optional[float]) -> None:
        if value is not None:
            self._values.append(float(value))

    def reset(self) -> None:
        self._values.clear()

    @property
    def mean(self) -> Optional[float]:
        if not self._values:
            return None
        return sum(self._values) / len(self._values)
