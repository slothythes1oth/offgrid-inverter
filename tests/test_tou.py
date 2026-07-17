"""TOU band function: weekday bands, weekends, holidays, seasonal swap edges."""

from datetime import datetime

from solarmon.tou import band, load_holidays


def dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm)


# 2026-01-14 is a Wednesday; 2026-07-15 is a Wednesday.


def test_winter_weekday_bands():
    assert band(dt(2026, 1, 14, 6, 59)) == "off_peak"
    assert band(dt(2026, 1, 14, 7)) == "on_peak"  # winter morning on-peak
    assert band(dt(2026, 1, 14, 10, 59)) == "on_peak"
    assert band(dt(2026, 1, 14, 11)) == "mid_peak"  # winter midday mid
    assert band(dt(2026, 1, 14, 16, 59)) == "mid_peak"
    assert band(dt(2026, 1, 14, 17)) == "on_peak"  # winter evening on-peak
    assert band(dt(2026, 1, 14, 18, 59)) == "on_peak"
    assert band(dt(2026, 1, 14, 19)) == "off_peak"


def test_summer_weekday_bands():
    assert band(dt(2026, 7, 15, 7)) == "mid_peak"  # summer morning mid
    assert band(dt(2026, 7, 15, 10, 59)) == "mid_peak"
    assert band(dt(2026, 7, 15, 11)) == "on_peak"  # summer midday on-peak
    assert band(dt(2026, 7, 15, 16, 59)) == "on_peak"
    assert band(dt(2026, 7, 15, 17)) == "mid_peak"
    assert band(dt(2026, 7, 15, 19)) == "off_peak"


def test_seasonal_swap_edges():
    # Thu 2026-04-30 (winter) vs Fri 2026-05-01 (summer), both weekdays, noon
    assert band(dt(2026, 4, 30, 12)) == "mid_peak"
    assert band(dt(2026, 5, 1, 12)) == "on_peak"
    # Fri 2026-10-30? use Fri Oct 30 (summer) vs Mon Nov 2 (winter) at 8:00
    assert band(dt(2026, 10, 30, 8)) == "mid_peak"
    assert band(dt(2026, 11, 2, 8)) == "on_peak"


def test_weekend_always_off_peak():
    assert band(dt(2026, 7, 18, 12)) == "off_peak"  # Saturday noon
    assert band(dt(2026, 7, 19, 8)) == "off_peak"  # Sunday morning


def test_holidays_off_peak():
    # Canada Day 2026 falls on a Wednesday
    assert band(dt(2026, 7, 1, 12)) == "off_peak"
    # Family Day 2026-02-16 (Monday), winter morning
    assert band(dt(2026, 2, 16, 8)) == "off_peak"
    # Good Friday 2026-04-03
    assert band(dt(2026, 4, 3, 18)) == "off_peak"


def test_holiday_file_covers_range():
    years = {h.year for h in load_holidays()}
    assert {2025, 2026, 2027} <= years
