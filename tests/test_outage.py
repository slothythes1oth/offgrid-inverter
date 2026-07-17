"""Outage debounce, ledger rows, kWh integration, restart resume."""

from tests.conftest import run_polls


def outage_rows(conn):
    return conn.execute("SELECT * FROM outages ORDER BY id").fetchall()


def events_of(conn, type_):
    return conn.execute("SELECT * FROM events WHERE type=? ORDER BY ts", (type_,)).fetchall()


def test_grid_flicker_does_not_declare(make_collector, clock, conn):
    src_state = _grid_up_source()
    col = make_collector(src_state)
    run_polls(col, clock, 3)
    src_state.set_grid(False)
    run_polls(col, clock, 2)  # only 2 polls on battery: below debounce of 3
    src_state.set_grid(True)
    run_polls(col, clock, 3)
    assert outage_rows(conn) == []
    assert events_of(conn, "grid_lost") == []


def test_outage_declared_after_debounce_and_ended(make_collector, clock, conn):
    src = _grid_up_source()
    col = make_collector(src)
    run_polls(col, clock, 3)
    src.set_grid(False)
    samples = run_polls(col, clock, 3)  # exactly the debounce count
    rows = outage_rows(conn)
    assert len(rows) == 1
    # started_ts is the FIRST poll of the streak, not the third
    assert rows[0]["started_ts"] == samples[0].ts
    assert rows[0]["ended_ts"] is None

    # 6 more polls on battery at 466 W, then restore
    run_polls(col, clock, 6)
    src.set_grid(True)
    restore = run_polls(col, clock, 3)
    rows = outage_rows(conn)
    assert rows[0]["ended_ts"] == restore[0].ts
    assert rows[0]["duration_s"] == rows[0]["ended_ts"] - rows[0]["started_ts"]
    # kWh: ~11 polls x 5s x 466 W ~ 0.007 kWh; just assert it integrated
    assert 0.004 < rows[0]["kwh_used"] < 0.012
    assert len(events_of(conn, "grid_lost")) == 1
    assert len(events_of(conn, "grid_restored")) == 1


def test_restart_resumes_open_outage(cfg, conn, clock):
    from solarmon.collector import Collector
    from solarmon.fake_source import FakeSource

    src = FakeSource()  # defaults: off-grid
    col = Collector(cfg, conn, src, now_fn=clock)
    col.startup()
    run_polls(col, clock, 4)  # outage declared
    assert len(outage_rows(conn)) == 1

    # "Restart": fresh collector on the same DB, still on battery
    clock.advance(120)
    col2 = Collector(cfg, conn, src, now_fn=clock)
    col2.startup()
    assert col2.outage.on_battery_state is True
    run_polls(col2, clock, 2)
    # No second outage row, no second grid_lost event
    assert len(outage_rows(conn)) == 1
    assert len(events_of(conn, "grid_lost")) == 1


def test_low_soc_fires_once_per_outage(make_collector, clock, conn):
    src = _grid_up_source()
    col = make_collector(src)
    run_polls(col, clock, 3)
    src.set_grid(False)
    run_polls(col, clock, 3)  # outage active
    src.set_soc(39)  # below default 40 threshold
    run_polls(col, clock, 3)
    src.set_soc(38)
    run_polls(col, clock, 3)
    assert len(events_of(conn, "low_soc")) == 1


def _grid_up_source():
    from solarmon.fake_source import FakeSource

    src = FakeSource()
    src.set_grid(True)
    return src
