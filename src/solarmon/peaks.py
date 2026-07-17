"""Sampled-peak tracking: max load seen per local day / ISO week / all-time.

"Sampled" because 5s polling cannot capture sub-5s surges; the UI must always
label these values "sampled peak". Period keys use local (America/Toronto)
dates so "today's peak" matches the wall clock.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from solarmon.registers import Sample

_UPSERT = (
    "INSERT INTO peaks (period, period_key, load_w, ts) VALUES (?, ?, ?, ?)"
    " ON CONFLICT (period, period_key) DO UPDATE"
    " SET load_w = excluded.load_w, ts = excluded.ts"
    " WHERE excluded.load_w > peaks.load_w"
)


def update_peaks(conn: sqlite3.Connection, sample: Sample, tz: str) -> None:
    local = datetime.fromtimestamp(sample.ts, ZoneInfo(tz))
    iso = local.isocalendar()
    for period, key in (
        ("day", local.date().isoformat()),
        ("week", f"{iso.year}-W{iso.week:02d}"),
        ("all", "all"),
    ):
        conn.execute(_UPSERT, (period, key, sample.load_w_total, sample.ts))
