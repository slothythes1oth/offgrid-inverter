"""Offline sunrise/sunset math (SPEC 8B.3).

Standard NOAA-style sunrise equation, accurate to a couple of minutes, which
is plenty for "will the battery make it to morning". Pure functions, no
network, no dependencies; the configured lat/long never leaves this module.
"""

from __future__ import annotations

import math

_J2000 = 2451545.0
_UNIX_EPOCH_JD = 2440587.5
_OBLIQUITY_DEG = 23.4397
# Standard altitude for rise/set: refraction + solar disc radius.
_SUN_ALTITUDE_DEG = -0.833


def _ts_to_jd(ts: float) -> float:
    return ts / 86400.0 + _UNIX_EPOCH_JD


def _jd_to_ts(jd: float) -> float:
    return (jd - _UNIX_EPOCH_JD) * 86400.0


def sun_times(lat: float, lon: float, ts: float) -> tuple[float, float] | None:
    """Sunrise and sunset (unix timestamps, UTC) for the solar day nearest ts.

    Returns None in polar day/night conditions (sun never crosses the
    horizon), which cannot happen at Bracebridge but keeps the math honest.
    """
    n = round(_ts_to_jd(ts) - _J2000 + 0.0008)  # days since J2000, nearest transit
    mean_solar_noon = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * mean_solar_noon) % 360)  # mean anomaly
    center = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    ecl_lon = math.radians((math.degrees(m) + center + 180 + 102.9372) % 360)
    j_transit = _J2000 + mean_solar_noon + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * ecl_lon)
    sin_decl = math.sin(ecl_lon) * math.sin(math.radians(_OBLIQUITY_DEG))
    decl = math.asin(sin_decl)
    lat_r = math.radians(lat)
    cos_hour = (math.sin(math.radians(_SUN_ALTITUDE_DEG)) - math.sin(lat_r) * sin_decl) / (
        math.cos(lat_r) * math.cos(decl)
    )
    if cos_hour < -1 or cos_hour > 1:
        return None  # polar day / polar night
    hour_angle = math.degrees(math.acos(cos_hour))
    return (
        _jd_to_ts(j_transit - hour_angle / 360.0),
        _jd_to_ts(j_transit + hour_angle / 360.0),
    )


def next_sun_events(
    lat: float, lon: float, now_ts: float, horizon_s: float = 86400.0
) -> list[dict]:
    """Sunrise/sunset events after now_ts within horizon_s, soonest first.

    This is what the outage burn-down marks on its projection: is sunrise
    before or after projected-empty. Feeds the API payload directly.
    """
    events: list[dict] = []
    # Solar days step by ~24h; scanning yesterday..+2d covers any horizon <= 36h
    # regardless of timezone offset between ts and the solar day boundary.
    for day_offset in (-1, 0, 1, 2):
        times = sun_times(lat, lon, now_ts + day_offset * 86400.0)
        if times is None:
            continue
        for kind, t in zip(("sunrise", "sunset"), times, strict=True):
            if now_ts < t <= now_ts + horizon_s:
                events.append({"type": kind, "ts": round(t)})
    events.sort(key=lambda e: e["ts"])
    return events
