"""Cost/savings calculators over synthetic rows."""

from datetime import datetime
from zoneinfo import ZoneInfo

from pytest import approx

from solarmon.config import TouRates
from solarmon.costs import cost_cents, grid_charge_kwh, kwh_by_band, peak_avoidance_savings_cents

TZ = ZoneInfo("America/Toronto")
RATES = TouRates(off_peak=9.8, mid_peak=15.7, on_peak=20.3)


def ts_at(y, m, d, hh):
    return int(datetime(y, m, d, hh, tzinfo=TZ).timestamp())


def test_kwh_by_band_splits_correctly():
    # Wed 2026-07-15 (summer): noon = on-peak, 8:00 = mid-peak, 22:00 = off-peak
    rows = [
        (ts_at(2026, 7, 15, 12), 1000, 3600),  # 1 kWh on-peak
        (ts_at(2026, 7, 15, 8), 2000, 3600),  # 2 kWh mid-peak
        (ts_at(2026, 7, 15, 22), 500, 3600),  # 0.5 kWh off-peak
    ]
    kwh = kwh_by_band(rows)
    assert kwh["on_peak"] == approx(1.0)
    assert kwh["mid_peak"] == approx(2.0)
    assert kwh["off_peak"] == approx(0.5)


def test_cost_cents_and_override():
    kwh = {"off_peak": 10.0, "mid_peak": 2.0, "on_peak": 1.0}
    c = cost_cents(kwh, RATES)
    assert c["total"] == approx(10 * 9.8 + 2 * 15.7 + 1 * 20.3)
    c2 = cost_cents(kwh, RATES, all_in_override=15.0)
    assert c2["total"] == approx(13 * 15.0)


def test_grid_charge_kwh_needs_grid_and_power():
    noon = ts_at(2026, 7, 15, 12)
    rows = [
        (noon, 242.0, -1500.0, 3600),  # charging on grid: counts (sign ignored)
        (noon, 242.0, 20.0, 3600),  # noise-level battery power: no
        (noon, 0.0, 800.0, 3600),  # no grid: discharge, not charging
    ]
    kwh = grid_charge_kwh(rows)
    assert kwh["on_peak"] == approx(1.5)
    assert kwh["off_peak"] == 0
    assert kwh["mid_peak"] == 0


def test_peak_avoidance_savings():
    rows = [
        (ts_at(2026, 7, 15, 12), 2000, 3600),  # 2 kWh on battery during on-peak
        (ts_at(2026, 7, 15, 22), 2000, 3600),  # off-peak: no savings credit
    ]
    cents = peak_avoidance_savings_cents(rows, RATES)
    assert cents == approx(2 * (20.3 - 9.8))
