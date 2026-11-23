"""Incremental per-gauge rainfall history at the native ten-minute cadence."""

from collections import deque
import numpy as np


class RainHistory:
    def __init__(self, count):
        self.window = deque()
        self.hour_mm = np.zeros(count)
        self.decay_mm = np.zeros(count)
        self.previous_mm = np.zeros(count)

    def add(self, amount_mm):
        if len(self.window) == 6:
            self.hour_mm -= self.window.popleft()
        self.window.append(amount_mm)
        self.hour_mm += amount_mm
        self.decay_mm = self.decay_mm * 0.8 + amount_mm
        increase = np.maximum(0, amount_mm - self.previous_mm)
        self.previous_mm = amount_mm
        # 5 mm in this observation interval is equivalent to 30 mm/h.
        return (amount_mm >= 5) * 100 + amount_mm + self.hour_mm / 6 + self.decay_mm / 5 + increase
