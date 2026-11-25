"""Incremental per-gauge rainfall history at the native ten-minute cadence."""

from collections import deque
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class RiskThresholds:
    rain_mm: float = 5
    hour_mm: float = 15
    decay_mm: float = 8
    depth_m: float = 0.010
    decay_factor: float = 0.8
    window_intervals: int = 6


RISK = RiskThresholds()


class RainHistory:
    def __init__(self, count):
        self.window = deque()
        self.hour_mm = np.zeros(count)
        self.decay_mm = np.zeros(count)

    def add(self, amount_mm):
        if len(self.window) == RISK.window_intervals:
            self.hour_mm -= self.window.popleft()
        # Exact 60-minute totals are retained only for the dashboard. Own the
        # bounded display buffer so it cannot retain the input interval array.
        self.window.append(amount_mm.copy())
        self.hour_mm += amount_mm
        self.decay_mm *= RISK.decay_factor
        self.decay_mm += amount_mm
