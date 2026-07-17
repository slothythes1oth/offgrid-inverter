"""History API queries: source selection, gaps-as-gaps, TOU day math,
flight-recorder traces, outage stats. Seeded with synthetic multi-day data
including a deliberate gap, an outage, and a fault event."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from tests.conftest import REPO_ROOT

from solarapi import history
from solarmon.config import load_config
from solarmon.db import connect, open_for_collector

TZ = ZoneInfo("America/Toronto")
# Wednesday 2026-07-15 00:00 local (EDT) — a plain summer weekday.
DAY0 = int(datetime(2026, 7, 15, 0, 0, tzinfo=TZ).timestamp())
NOW = DAY0 + 3 * 86400  # three days of data


@pytest.fixture(scope="module")
def cfg():
    return load_config(REPO_ROOT / "config.yaml")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """3 days of per-minute rollups (500 W flat, 2 kW during on-peak hours),
    a 30-min gap on day 2, raw samples for the last hour, one closed outage,
    one fault event with snapshot."""
    path = tmp_path_factory.mktemp("hist") / "hist.db"
    conn = open_for_collector(path)

    gap_start = DAY0 + 86400 + 12 * 3600  # day 2, 12:00 local
    gap_end = gap_start + 1800
    rows = []
    for m in range(0, 3 * 1440):
        ts = DAY0 + m * 60
        if gap_start <= ts < gap_end:
            continue  # the gap: no rows at all
        hour = datetime.fromtimestamp(ts, TZ).hour
        load = 2000.0 if 11 <= hour < 17 else 500.0  # on-peak bump (summer)
        batt = 800.0 if 13 <= hour < 14 else -300.0  # 13:00 discharging, else charging
        soc = 90 - (m % 60) / 10
        rows.append(
            (ts, load, load - 50, load + 150, batt, batt, batt, soc, int(soc) - 1, int(soc) + 1, 12)
        )
    conn.executemany("INSERT INTO rollup_1m VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)

    # Raw samples: last hour before NOW at 5s, load 466 W.
    conn.executemany(
        "INSERT INTO samples (ts, soc, batt_v, batt_a, batt_w, pv1_w, pv2_w, grid_v_l1,"
        " grid_v_l2, load_w_l1, load_w_l2, load_w_total, load_pct_l1, load_pct_l2,"
        " machine_state, fault_active)"
        " VALUES (?,88,52.0,5.0,260.0,0,0,120.0,120.0,312,154,466,9,5,2,0)",
        [(t,) for t in range(NOW - 3600, NOW, 5)],
    )

    conn.execute(
        "INSERT INTO outages (started_ts, ended_ts, duration_s, soc_start, soc_end, kwh_used)"
        " VALUES (?, ?, 5400, 90, 78, 2.4)",
        (DAY0 + 86400 + 13 * 3600, DAY0 + 86400 + 13 * 3600 + 5400),
    )

    # Insert in time order: the collector always does, and events_page's
    # keyset pagination relies on id order == time order.
    conn.execute(
        "INSERT INTO events (ts, type, detail) VALUES (?, 'grid_lost', ?)",
        (DAY0 + 86400 + 13 * 3600, json.dumps({"soc": 90, "load_w_total": 2000})),
    )
    detail = {
        "fault_codes": [13],
        "soc": 62,
        "load_w_total": 5900,
        "snapshot": {
            "machine_state": 10,
            "soc": 62,
            "load_w_total": 5900,
            "load_w_l1": 4800,
            "load_w_l2": 1100,
            "batt_v": 50.1,
            "batt_w": 5700,
        },
    }
    conn.execute(
        "INSERT INTO events (ts, type, detail) VALUES (?, 'fault_raised', ?)",
        (NOW - 1800, json.dumps(detail)),
    )
    conn.commit()
    conn.close()
    ro = connect(path, read_only=True)
    yield ro
    ro.close()


def test_window_source_selection(db, cfg):
    assert history.load_series(db, cfg, window="1h", now=NOW)["source"] == "samples"
    for w, step in (("24h", 60), ("7d", 600), ("30d", 1800)):
        out = history.load_series(db, cfg, window=w, now=NOW)
        assert out["source"] == "rollup"
        assert out["step_s"] == step


def test_point_budget(db, cfg):
    for w in ("1h", "24h", "7d", "30d"):
        out = history.load_series(db, cfg, window=w, now=NOW)
        assert out["count"] <= 2200, f"{w} ships {out['count']} points"


def test_gap_renders_as_gap(db, cfg):
    out = history.load_series(db, cfg, window="7d", now=NOW)
    gap_start = DAY0 + 86400 + 12 * 3600
    # The 30-min hole must appear in gaps and as a null point, never bridged.
    assert any(g[0] <= gap_start + 600 <= g[1] for g in out["gaps"])
    null_ts = [p[0] for p in out["points"] if p[1] is None]
    assert any(gap_start <= t <= gap_start + 1800 for t in null_ts)


def test_custom_range_drilldown_uses_raw(db, cfg):
    out = history.load_series(db, cfg, t_from=NOW - 1200, t_to=NOW)
    assert out["source"] == "samples"
    assert out["step_s"] == 5


def test_thresholds_and_peaks_meta(db, cfg):
    out = history.load_series(db, cfg, window="24h", now=NOW)
    t = out["thresholds"]
    assert t["continuous_load_w"] == 6500
    assert t["bypass_w_per_leg"] == 4800
    assert t["bypass_w_total_balanced"] == 9600


def test_events_page_and_fault_name(db):
    out = history.events_page(db, limit=10)
    assert out["items"][0]["type"] == "fault_raised"  # newest first
    assert out["items"][0]["fault_codes"] == [{"code": 13, "name": "bypass overload"}]
    only_grid = history.events_page(db, types=["grid_lost"])
    assert {i["type"] for i in only_grid["items"]} == {"grid_lost"}


def test_event_trace_flight_recorder(db):
    ev = history.events_page(db, types=["fault_raised"])["items"][0]
    trace = history.event_trace(db, ev["id"])
    assert trace["trace"]["source"] == "samples"  # raw still covers it
    t0 = trace["trace"]["points"][0][0]
    t1 = trace["trace"]["points"][-1][0]
    assert t0 >= ev["ts"] - 600 and t1 <= ev["ts"] + 600
    f = trace["facts"]
    assert f["machine_state_name"] == "Fault"
    assert f["load_a_l1"] == pytest.approx(40.0, abs=0.1)  # 4800 W / 120 V
    assert history.event_trace(db, 99999) is None


def test_outage_stats(db):
    out = history.outages_page(db)
    assert out["stats"]["count"] == 1
    assert out["stats"]["avg_duration_s"] == 5400
    assert out["items"][0]["kwh_used"] == 2.4


def test_tou_daily_bands_and_costs(db, cfg):
    out = history.tou_daily(db, cfg, days=5, now=NOW)
    d = next(i for i in out["items"] if i["date"] == "2026-07-15")
    # Summer weekday: on-peak 11-17 at 2 kW = 12 kWh; off-peak 19-07 at 0.5 kW
    # = 6 kWh; mid-peak 07-11 + 17-19 at 0.5 kW = 3 kWh.
    assert d["kwh"]["on_peak"] == pytest.approx(12.0, abs=0.1)
    assert d["kwh"]["off_peak"] == pytest.approx(6.0, abs=0.1)
    assert d["kwh"]["mid_peak"] == pytest.approx(3.0, abs=0.1)
    assert d["cost_cents"]["on_peak"] == pytest.approx(12.0 * 20.3, rel=0.02)
    # 13:00-14:00 battery discharged ~800 W during on-peak -> savings accrue.
    assert d["battery_served_on_peak_kwh"] == pytest.approx(0.8, abs=0.1)
    assert d["savings_cents"] == pytest.approx(0.8 * (20.3 - 9.8), rel=0.05)
    day2 = next(i for i in out["items"] if i["date"] == "2026-07-16")
    assert day2["outage"] is True


def test_tou_daily_rate_override_and_all_in(db, cfg):
    base = history.tou_daily(db, cfg, days=5, now=NOW)
    doubled = history.tou_daily(db, cfg, days=5, now=NOW, on=40.6)
    d0 = next(i for i in base["items"] if i["date"] == "2026-07-15")
    d1 = next(i for i in doubled["items"] if i["date"] == "2026-07-15")
    assert d1["cost_cents"]["on_peak"] == pytest.approx(d0["cost_cents"]["on_peak"] * 2, rel=0.01)
    flat = history.tou_daily(db, cfg, days=5, now=NOW, all_in=10.0)
    df = next(i for i in flat["items"] if i["date"] == "2026-07-15")
    assert df["cost_cents"]["total"] == pytest.approx(df["total_kwh"] * 10.0, rel=0.01)


def test_tou_day_ring_hours(db, cfg):
    out = history.tou_day(db, cfg, "2026-07-15")
    assert len(out["hours"]) == 24
    bands = {h["local_hour"]: h["band"] for h in out["hours"]}
    assert bands[12] == "on_peak" and bands[8] == "mid_peak" and bands[22] == "off_peak"
    assert out["hours"][12]["kwh"] == pytest.approx(2.0, abs=0.05)


def test_tou_day_missing_hours_are_null(db, cfg):
    # Day 2 has the 12:00-12:30 gap: that hour's kWh is reduced, and a day
    # with no data at all returns all-null hours (fresh-install state).
    empty = history.tou_day(db, cfg, "2026-01-01")
    assert all(h["kwh"] is None for h in empty["hours"])


def test_battery_daily_band(db, cfg):
    out = history.battery_daily(db, cfg, days=5, now=NOW)
    assert out["summary"]["days_with_data"] >= 3
    d = out["items"][0]
    assert d["soc_min"] <= d["soc_avg"] <= d["soc_max"]
    assert d["dod"] == d["soc_max"] - d["soc_min"]
