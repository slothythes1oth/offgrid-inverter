"""Offline sunrise/sunset math. Reference windows are generous (+/- 15 min)
so the test pins correctness of the algorithm, not minute-level precision the
feature does not need."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from solarmon.sun import next_sun_events, sun_times

LAT, LON = 45.04, -79.31  # Bracebridge, ON
TZ = ZoneInfo("America/Toronto")


def _local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=TZ)


def _noon_utc(year: int, month: int, day: int) -> float:
    return datetime(year, month, day, 17, 0, tzinfo=UTC).timestamp()


def test_july_bracebridge_window():
    # Mid-July: sunrise ~05:40 EDT, sunset ~20:55 EDT.
    rise, set_ = sun_times(LAT, LON, _noon_utc(2026, 7, 17))
    r, s = _local(rise), _local(set_)
    assert r.hour == 5 and 25 <= r.minute <= 55
    assert s.hour == 20 and 40 <= s.minute or s.hour == 21 and s.minute <= 10
    assert set_ - rise > 14.5 * 3600  # long summer day


def test_december_bracebridge_window():
    # Winter solstice: sunrise ~07:50 EST, sunset ~16:35 EST, short day.
    rise, set_ = sun_times(LAT, LON, _noon_utc(2026, 12, 21))
    r, s = _local(rise), _local(set_)
    assert r.hour == 7 and 35 <= r.minute or r.hour == 8 and r.minute <= 5
    assert s.hour == 16 and 20 <= s.minute <= 50
    assert set_ - rise < 9.5 * 3600


def test_polar_night_returns_none():
    # Svalbard in December: sun never rises.
    assert sun_times(78.22, 15.65, _noon_utc(2026, 12, 21)) is None


def test_next_events_ordering_and_horizon():
    # From local midnight the next 24h must contain exactly one sunrise then
    # one sunset, in that order, strictly in the future.
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC).timestamp()  # midnight EDT
    events = next_sun_events(LAT, LON, now)
    kinds = [e["type"] for e in events]
    assert kinds == ["sunrise", "sunset"]
    assert all(now < e["ts"] <= now + 86400 for e in events)
    assert events[0]["ts"] < events[1]["ts"]


def test_next_events_evening_start():
    # From 22:00 local the first event within 24h is tomorrow's sunrise.
    now = datetime(2026, 7, 18, 2, 0, tzinfo=UTC).timestamp()  # 22:00 EDT Jul 17
    events = next_sun_events(LAT, LON, now)
    assert events and events[0]["type"] == "sunrise"
    assert _local(events[0]["ts"]).hour == 5
