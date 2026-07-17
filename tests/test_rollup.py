"""Rollup builder and retention pruner, including the midnight boundary."""

from solarmon.rollup import build_rollups, prune_if_new_day, prune_samples


def insert_sample(conn, ts, load=500, batt_w=480.0, soc=90):
    conn.execute(
        "INSERT INTO samples (ts, soc, batt_v, batt_a, batt_w, pv1_w, pv2_w, grid_v_l1,"
        " grid_v_l2, load_w_l1, load_w_l2, load_w_total, load_pct_l1, load_pct_l2,"
        " machine_state, fault_active)"
        " VALUES (?, ?, 52.8, 9.0, ?, 0, 0, 0, 0, ?, 0, ?, 10, 0, 5, 0)",
        (ts, soc, batt_w, load, load),
    )


def test_rollup_aggregates_completed_minutes(conn):
    base = 1_784_700_000 - 1_784_700_000 % 60  # minute-aligned
    for i, load in enumerate([400, 500, 600]):  # one minute, 3 samples
        insert_sample(conn, base + i * 20, load=load)
    insert_sample(conn, base + 60, load=999)  # next minute (current: not rolled)
    n = build_rollups(conn, now_ts=base + 90)
    assert n == 1
    row = conn.execute("SELECT * FROM rollup_1m").fetchone()
    assert row["minute_ts"] == base
    assert row["load_w_avg"] == 500
    assert row["load_w_min"] == 400
    assert row["load_w_max"] == 600
    assert row["sample_count"] == 3


def test_rollup_skips_empty_minutes_and_is_incremental(conn):
    base = 1_784_700_000 - 1_784_700_000 % 60
    insert_sample(conn, base)
    insert_sample(conn, base + 180)  # 2-minute gap in between
    assert build_rollups(conn, now_ts=base + 240) == 2
    minutes = [r["minute_ts"] for r in conn.execute("SELECT minute_ts FROM rollup_1m")]
    assert minutes == [base, base + 180]  # no rows for the empty minutes
    assert build_rollups(conn, now_ts=base + 240) == 0  # nothing new


def test_pruner_deletes_only_old(conn):
    now = 1_784_700_000
    old = now - 31 * 86400
    fresh = now - 5 * 86400
    insert_sample(conn, old)
    insert_sample(conn, fresh)
    assert prune_samples(conn, now, retention_days=30) == 1
    remaining = [r["ts"] for r in conn.execute("SELECT ts FROM samples")]
    assert remaining == [fresh]


def test_daily_prune_fires_on_date_change(conn):
    tz = "America/Toronto"
    # 1_784_692_740 = 2026-07-21 23:59:00 Toronto (EDT)
    before_midnight = 1_784_692_740
    after_midnight = before_midnight + 120
    insert_sample(conn, before_midnight - 31 * 86400)
    assert prune_if_new_day(conn, before_midnight, 30, tz) is not None  # first ever run
    insert_sample(conn, before_midnight - 31 * 86400 + 60)
    assert prune_if_new_day(conn, before_midnight + 30, 30, tz) is None  # same day
    assert prune_if_new_day(conn, after_midnight, 30, tz) == 1  # new local day
