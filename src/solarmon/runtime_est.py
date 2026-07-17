"""Runtime-remaining estimator: usable kWh remaining / EMA-smoothed draw.

The EMA (default ~10 min window) exists so the displayed estimate never jumps
with each poll. Draw is fed as load power (sign-free), not battery current:
the current sign is provisional per PROVEN.md.
"""

from __future__ import annotations

MIN_DRAW_W = 50.0  # below this, "runtime" is meaningless: show "> 24 hrs"
CAP_HOURS = 24.0


class RuntimeEstimator:
    def __init__(self, window_s: float = 600.0):
        self.window_s = window_s
        self.smoothed_w: float | None = None

    def update(self, draw_w: float, dt_s: float) -> float:
        """Feed one poll's draw. Returns the new smoothed draw."""
        if self.smoothed_w is None:
            self.smoothed_w = float(draw_w)
        else:
            alpha = min(1.0, dt_s / self.window_s)
            self.smoothed_w += alpha * (draw_w - self.smoothed_w)
        return self.smoothed_w

    def reset(self) -> None:
        self.smoothed_w = None

    def runtime_hours(
        self, soc_pct: float, nominal_kwh: float, usable_fraction: float
    ) -> tuple[float | None, bool]:
        """(hours, capped). capped=True means display '> 24 hrs'.
        hours is None until at least one update() and when draw is near zero."""
        if self.smoothed_w is None:
            return None, False
        if self.smoothed_w < MIN_DRAW_W:
            return None, True
        usable_kwh = nominal_kwh * usable_fraction * (soc_pct / 100.0)
        hours = usable_kwh * 1000.0 / self.smoothed_w
        if hours > CAP_HOURS:
            return CAP_HOURS, True
        return hours, False
