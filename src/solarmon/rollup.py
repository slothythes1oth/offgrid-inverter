"""1-minute rollups and raw-sample retention pruning.

Rollups are built continuously: every completed minute (strictly before the
current one) that has samples and no rollup row yet gets one. Minutes with no
samples get NO row: gaps stay gaps, charts must not interpolate.

Pruning deletes raw samples older than retention_days once per local day.
Rollups, events, and outages are kept forever.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("rollup")


def build_rollups(conn: sqlite3.Connection, now_ts: int) -> int:
    """Aggregate all complete, un-rolled minutes. Returns rows written."""
    current_minute = now_ts // 60 * 60
    last = conn.execute("SELECT COALESCE(MAX(minute_ts), 0) FROM rollup_1m").fetchone()[0]
    start = last + 60 if last else 0
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO rollup_1m
            (minute_ts, load_w_avg, load_w_min, load_w_max,
             batt_w_avg, batt_w_min, batt_w_max,
             soc_avg, soc_min, soc_max, sample_count)
        SELECT (ts / 60) * 60 AS m,
               AVG(load_w_total), MIN(load_w_total), MAX(load_w_total),
               AVG(batt_w), MIN(batt_w), MAX(batt_w),
               AVG(soc), MIN(soc), MAX(soc), COUNT(*)
        FROM samples
        WHERE ts >= ? AND ts < ?
        GROUP BY m
        """,
        (start, current_minute),
    )
    return cur.rowcount


def prune_samples(conn: sqlite3.Connection, now_ts: int, retention_days: int) -> int:
    """Delete raw samples older than the retention window. Returns rows deleted."""
    cutoff = now_ts - retention_days * 86400
    cur = conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
    if cur.rowcount:
        log.info("pruned %d raw samples older than %d days", cur.rowcount, retention_days)
    return cur.rowcount


def prune_if_new_day(
    conn: sqlite3.Connection, now_ts: int, retention_days: int, tz: str
) -> int | None:
    """Run the daily prune when the local date changes. Returns rows deleted,
    or None if it was not time yet. Tracks the last run in meta."""
    today = datetime.fromtimestamp(now_ts, ZoneInfo(tz)).date().isoformat()
    row = conn.execute("SELECT value FROM meta WHERE key='last_prune_date'").fetchone()
    if row and row["value"] == today:
        return None
    deleted = prune_samples(conn, now_ts, retention_days)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_prune_date', ?)", (today,))
    return deleted
