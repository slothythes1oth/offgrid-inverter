"""TOU cost and savings calculators. Pure functions over row iterables;
callers (future API / reports) do the SQL and pass rows in.

Costs are supply-only: delivery charges and the Ontario rebate change the
all-in number. An optional all-in cents/kWh override in config replaces the
per-band rates entirely when set.
"""

from __future__ import annotations

from collections.abc import Iterable

from solarmon.config import TouRates
from solarmon.derived import CHARGE_MIN_W, GRID_PRESENT_MIN_V
from solarmon.tou import Band, band_for_ts

Bands = ("off_peak", "mid_peak", "on_peak")


def kwh_by_band(
    rows: Iterable[tuple[int, float, float]], tz: str = "America/Toronto"
) -> dict[Band, float]:
    """Consumption kWh per TOU band.

    rows: (ts, load_w, dt_s) — one entry per sample (dt_s = poll interval) or
    per rollup minute (dt_s = 60, load_w = load_w_avg).
    """
    out: dict[Band, float] = {b: 0.0 for b in Bands}
    for ts, load_w, dt_s in rows:
        out[band_for_ts(ts, tz)] += load_w * dt_s / 3_600_000.0
    return out


def cost_cents(
    kwh: dict[Band, float], rates: TouRates, all_in_override: float | None = None
) -> dict:
    """Supply-only cost per band and total, in cents."""
    if all_in_override is not None:
        per_band = {b: kwh[b] * all_in_override for b in Bands}
    else:
        rate_map = {
            "off_peak": rates.off_peak,
            "mid_peak": rates.mid_peak,
            "on_peak": rates.on_peak,
        }
        per_band = {b: kwh[b] * rate_map[b] for b in Bands}
    return {**per_band, "total": sum(per_band.values())}


def grid_charge_kwh(
    rows: Iterable[tuple[int, float, float, float]], tz: str = "America/Toronto"
) -> dict[Band, float]:
    """Energy flowing into the battery from grid, kWh per band.

    rows: (ts, grid_v_l1, batt_w, dt_s). While grid is present, meaningful
    battery power is charge (this system never discharges into the grid);
    magnitude is used so the provisional current sign cannot flip the answer.
    """
    out: dict[Band, float] = {b: 0.0 for b in Bands}
    for ts, grid_v, batt_w, dt_s in rows:
        if grid_v >= GRID_PRESENT_MIN_V and abs(batt_w) >= CHARGE_MIN_W:
            out[band_for_ts(ts, tz)] += abs(batt_w) * dt_s / 3_600_000.0
    return out


def peak_avoidance_savings_cents(
    battery_served_rows: Iterable[tuple[int, float, float]],
    rates: TouRates,
    tz: str = "America/Toronto",
) -> float:
    """kWh served from battery during on-peak x (on-peak - off-peak rate).

    battery_served_rows: (ts, load_w, dt_s) for polls where the house ran on
    battery. Caller filters those (grid_v ~0 and machine_state 5).
    """
    on_peak_kwh = 0.0
    for ts, load_w, dt_s in battery_served_rows:
        if band_for_ts(ts, tz) == "on_peak":
            on_peak_kwh += load_w * dt_s / 3_600_000.0
    return on_peak_kwh * (rates.on_peak - rates.off_peak)
