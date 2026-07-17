"""Collector end-to-end against the fake source: samples, events, faults,
failures/staleness, gap on restart, peaks."""

import json

from tests.conftest import run_polls

from solarmon.fake_source import FakeSource


def events(conn, type_=None):
    q = "SELECT * FROM events" + (" WHERE type=?" if type_ else "") + " ORDER BY ts, id"
    return conn.execute(q, (type_,) if type_ else ()).fetchall()


def test_cycles_write_samples(make_collector, clock, conn):
    col = make_collector()
    run_polls(col, clock, 5)
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 5
    row = conn.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
    assert row["soc"] == 96
    assert row["load_w_total"] == 466
    assert row["fault_active"] == 0


def test_start_and_stop_events(make_collector, clock, conn):
    col = make_collector()
    run_polls(col, clock, 1)
    col.shutdown()
    types = [e["type"] for e in events(conn)]
    assert "collector_start" in types
    assert "collector_stop" in types


def test_fault_capture_with_same_poll_snapshot(make_collector, clock, conn):
    src = FakeSource()
    col = make_collector(src)
    run_polls(col, clock, 2)
    src.raise_fault(13)
    src.set_load(4800, 1200)  # the surge that tripped it
    run_polls(col, clock, 1)
    raised = events(conn, "fault_raised")
    assert len(raised) == 1
    detail = json.loads(raised[0]["detail"])
    assert detail["fault_codes"] == [13]
    assert detail["fault_names"] == ["bypass overload"]
    assert detail["load_w_total"] == 6000  # snapshot is from the SAME poll

    run_polls(col, clock, 3)  # ongoing fault: no repeat events
    assert len(events(conn, "fault_raised")) == 1

    src.clear_faults()
    src.set_load(312, 154)
    run_polls(col, clock, 1)
    assert len(events(conn, "fault_cleared")) == 1


def test_source_failure_writes_nothing_and_recovers(make_collector, clock, conn):
    src = FakeSource()
    col = make_collector(src)
    run_polls(col, clock, 3)
    src.fail_next_cycles = 8  # 40s of failures: crosses the 30s stale threshold
    out = run_polls(col, clock, 8)
    assert out == [None] * 8
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 3
    recovered = run_polls(col, clock, 2)
    assert all(s is not None for s in recovered)
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 5


def test_gap_event_on_restart_after_kill(cfg, conn, clock):
    from solarmon.collector import Collector

    col = Collector(cfg, conn, FakeSource(), now_fn=clock)
    col.startup()
    run_polls(col, clock, 2)
    # hard kill: no shutdown() call, then 10 minutes pass
    clock.advance(600)
    col2 = Collector(cfg, conn, FakeSource(), now_fn=clock)
    col2.startup()
    gaps = events(conn, "gap_detected")
    assert len(gaps) == 1
    detail = json.loads(gaps[0]["detail"])
    assert 595 <= detail["gap_s"] <= 605


def test_no_gap_event_on_quick_restart(cfg, conn, clock):
    from solarmon.collector import Collector

    col = Collector(cfg, conn, FakeSource(), now_fn=clock)
    col.startup()
    run_polls(col, clock, 2)
    clock.advance(20)  # well under the 60s gap threshold
    col2 = Collector(cfg, conn, FakeSource(), now_fn=clock)
    col2.startup()
    assert events(conn, "gap_detected") == []


def test_peaks_tracked(make_collector, clock, conn):
    src = FakeSource()
    col = make_collector(src)
    run_polls(col, clock, 2)
    src.set_load(3000, 2000)
    run_polls(col, clock, 1)
    src.set_load(300, 100)
    run_polls(col, clock, 2)
    peaks = {r["period"]: r["load_w"] for r in conn.execute("SELECT * FROM peaks")}
    assert peaks["day"] == 5000
    assert peaks["week"] == 5000
    assert peaks["all"] == 5000


def test_rollups_built_during_run(make_collector, clock, conn):
    col = make_collector()
    run_polls(col, clock, 30)  # 150s: at least 2 full minutes
    assert conn.execute("SELECT COUNT(*) FROM rollup_1m").fetchone()[0] >= 2
