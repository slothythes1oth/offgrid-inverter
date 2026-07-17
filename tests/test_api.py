"""API backend: endpoints, payload shape, read-only guarantee, SSE framing.

Uses a temp DB seeded via the collector so payloads reflect real decoding.
"""

import json

import pytest
from fastapi.testclient import TestClient
from tests.conftest import REPO_ROOT, FakeClock, run_polls

from solarapi.app import create_app
from solarapi.queries import build_current
from solarmon.collector import Collector
from solarmon.config import load_config
from solarmon.db import connect, open_for_collector
from solarmon.fake_source import FakeSource


@pytest.fixture
def seeded_db(tmp_path):
    """A DB with a short on-grid run, returned as a path + config pointing at it."""
    db = tmp_path / "api.db"
    conn = open_for_collector(db)
    cfg = load_config(REPO_ROOT / "config.yaml")
    clock = FakeClock(start=1_784_700_000.0)
    src = FakeSource()
    src.set_grid(True)
    col = Collector(cfg, conn, src, now_fn=clock)
    col.startup()
    run_polls(col, clock, 5)
    conn.close()
    return db, clock.t


@pytest.fixture
def client(seeded_db, tmp_path, monkeypatch):
    db, _ = seeded_db
    # Point a config file at the temp DB
    cfg_text = (REPO_ROOT / "config.yaml").read_text(encoding="utf-8")
    cfg_text = cfg_text.replace("path: data/solarmon.db", f"path: {db.as_posix()}")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text, encoding="utf-8")
    app = create_app(str(cfg_path))
    return TestClient(app)


def test_current_shape(client):
    r = client.get("/api/current")
    assert r.status_code == 200
    body = r.json()
    assert body["soc"] == 96  # FakeSource default (PROVEN.md snapshot)
    assert body["on_battery"] is False
    assert body["flow"] == "grid_to_battery"
    assert body["machine_state_name"]
    assert body["outage"] is None
    assert body["headroom"]["available_w"] > 0
    # 8B retrofit fields: per-leg amps + bypass ceiling for the headroom lanes.
    assert body["headroom"]["bypass_a_per_leg"] == 40
    assert body["headroom"]["bypass_w_per_leg"] == 4800
    assert body["load_a_l1"] == pytest.approx(body["load_w_l1"] / 120, abs=0.1)
    assert body["load_a_l2"] == pytest.approx(body["load_w_l2"] / 120, abs=0.1)


def test_settings_has_no_credentials(client):
    body = client.get("/api/settings").json()
    assert "battery" in body and "thresholds" in body
    flat = json.dumps(body)
    assert "192.168" not in flat  # no stick IP
    assert "serial" not in flat


def test_settings_sun_events_but_no_coordinates(client):
    """Settings carries upcoming sun events for the burn-down demo, but the
    raw lat/long never leaves the machine via the API."""
    body = client.get("/api/settings").json()
    assert body["sun_events"], "expected at least one sun event in the next 24h"
    assert {e["type"] for e in body["sun_events"]} <= {"sunrise", "sunset"}
    flat = json.dumps(body)
    assert "45.04" not in flat and "-79.31" not in flat
    assert "lat" not in flat and "lon" not in flat


def test_recent_samples_capped_and_trimmed(client):
    body = client.get("/api/samples/recent?window_s=999999").json()
    assert body["window_s"] <= 6 * 3600  # capped
    if body["samples"]:
        assert set(body["samples"][0]) == {
            "ts",
            "soc",
            "batt_w",
            "load_w_total",
            "grid_v_l1",
            "pv_w_total",
        }


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["latest_sample_age_s"] is not None


def test_stale_flag_from_age(seeded_db, tmp_path):
    """Stale is pure data age: a far-future 'now' marks stale even though the
    sample was fine when written (drives the disconnected banner)."""
    db, last_ts = seeded_db
    cfg = load_config(REPO_ROOT / "config.yaml")
    conn = connect(db, read_only=True)
    try:
        fresh = build_current(conn, cfg, now=last_ts + 2)
        stale = build_current(conn, cfg, now=last_ts + 999)
    finally:
        conn.close()
    assert fresh["stale"] is False
    assert stale["stale"] is True


def test_outage_payload_when_on_battery(tmp_path):
    db = tmp_path / "outage.db"
    conn = open_for_collector(db)
    cfg = load_config(REPO_ROOT / "config.yaml")
    clock = FakeClock(start=1_784_700_000.0)
    src = FakeSource()
    src.set_grid(True)
    col = Collector(cfg, conn, src, now_fn=clock)
    col.startup()
    run_polls(col, clock, 3)
    src.set_grid(False)
    run_polls(col, clock, 10)  # outage declared + drain history
    conn.close()

    ro = connect(db, read_only=True)
    try:
        body = build_current(ro, cfg, now=clock.t)
    finally:
        ro.close()
    assert body["on_battery"] is True
    assert body["outage"]["active"] is True
    assert body["outage"]["elapsed_s"] > 0
    assert body["outage"]["runtime_remaining_h"] is not None
    # Burn-down markers: sun events present, in the future, sorted.
    suns = body["outage"]["sun_events"]
    assert suns and all(e["ts"] > clock.t for e in suns)
    assert suns == sorted(suns, key=lambda e: e["ts"])


def test_drain_rate_is_outage_wide_and_sane(tmp_path):
    """Drain rate is the whole-outage average, not a jumpy trailing window."""
    db = tmp_path / "drain.db"
    conn = open_for_collector(db)
    cfg = load_config(REPO_ROOT / "config.yaml")
    start = 1_784_700_000
    # Outage started 2h ago at 90%, now at 80% -> 5%/hr; on battery, 500 W load.
    conn.execute(
        "INSERT INTO outages (started_ts, soc_start, soc_end, kwh_used) VALUES (?,90,80,1.0)",
        (start,),
    )
    for i in range(0, 7200, 5):
        soc = 90 - (i / 7200) * 10
        conn.execute(
            "INSERT INTO samples (ts, soc, batt_v, batt_a, batt_w, pv1_w, pv2_w, grid_v_l1,"
            " grid_v_l2, load_w_l1, load_w_l2, load_w_total, load_pct_l1, load_pct_l2,"
            " machine_state, fault_active) VALUES (?,?,52.0,9.6,499.2,0,0,0,0,250,250,500,9,9,5,0)",
            (start + i, round(soc)),
        )
    conn.commit()
    conn.close()

    ro = connect(db, read_only=True)
    try:
        body = build_current(ro, cfg, now=start + 7200 + 3)
    finally:
        ro.close()
    o = body["outage"]
    assert o["active"] is True
    assert 4.0 <= o["drain_pct_per_hr"] <= 6.0  # ~5%/hr, not an absurd spike
    assert o["runtime_remaining_h"] is not None


def test_stream_emits_state_event(seeded_db, tmp_path):
    """Drive the SSE generator directly: it is an infinite stream, so pull the
    opening frames with a timeout rather than via TestClient (which buffers)."""
    import asyncio

    from solarapi.app import _event_stream

    db, _ = seeded_db
    cfg = load_config(REPO_ROOT / "config.yaml")
    cfg.database.path = str(db)

    async def first_frames(n):
        gen = _event_stream(cfg)
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(gen.__anext__(), timeout=5))
        await gen.aclose()
        return out

    frames = asyncio.run(first_frames(2))
    assert frames[0].startswith("retry:")  # reconnect hint first
    assert "event: state" in frames[1]
    data_line = next(ln for ln in frames[1].splitlines() if ln.startswith("data:"))
    payload = json.loads(data_line[len("data:") :].strip())
    assert payload["soc"] == 96
    assert payload["stale"] is False
