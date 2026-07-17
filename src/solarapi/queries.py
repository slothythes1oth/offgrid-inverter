"""Read-only queries + derived-state builders that produce the API payloads.

All timing/derivation the UI needs but the DB does not store (data age, drain
rate, runtime remaining) is computed here from stored samples. The collector's
own EMA is for its alerts; the API recomputes a display-friendly equivalent
from recent samples so the two processes stay fully decoupled.
"""

from __future__ import annotations

import sqlite3
import time

from solarmon.config import Config
from solarmon.derived import flow, on_battery
from solarmon.registers import MACHINE_STATES, Sample
from solarmon.runtime_est import CAP_HOURS, MIN_DRAW_W
from solarmon.sun import next_sun_events

# Trailing window for "current" drain rate and smoothed draw (seconds).
_DRAIN_WINDOW_S = 600

# Per-leg amps are derived at nominal leg voltage: the output-voltage register
# is not in the proven map, and the headroom lanes measure proximity to a
# 40 A relay limit, where a few percent of voltage sag is immaterial.
NOMINAL_LEG_V = 120.0


def _row_to_sample(row: sqlite3.Row) -> Sample:
    """Rebuild a Sample from a stored row. fault_codes are not persisted
    (only the bool), which is fine: derived flow/on_battery never read them."""
    return Sample(
        ts=row["ts"],
        soc=row["soc"],
        batt_v=row["batt_v"],
        batt_a=row["batt_a"],
        batt_w=row["batt_w"],
        pv1_w=row["pv1_w"],
        pv2_w=row["pv2_w"],
        grid_v_l1=row["grid_v_l1"],
        grid_v_l2=row["grid_v_l2"],
        load_w_l1=row["load_w_l1"],
        load_w_l2=row["load_w_l2"],
        load_w_total=row["load_w_total"],
        load_pct_l1=row["load_pct_l1"],
        load_pct_l2=row["load_pct_l2"],
        machine_state=row["machine_state"],
        fault_active=bool(row["fault_active"]),
        fault_codes=(),
    )


def latest_sample(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1").fetchone()


def active_outage(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM outages WHERE ended_ts IS NULL ORDER BY started_ts DESC LIMIT 1"
    ).fetchone()


def _drain_and_runtime(
    conn: sqlite3.Connection, cfg: Config, latest: sqlite3.Row, outage: sqlite3.Row
) -> dict:
    """Drain rate and runtime remaining for the active outage.

    Drain rate is the outage-wide average (soc_start - soc_now)/elapsed: SoC
    is a coarse integer, so a short trailing window is either jumpy or absurd;
    the whole-outage slope is stable and answers "how fast is it going down".
    Runtime uses a recent-window mean load so it tracks the current draw."""
    elapsed_h = (latest["ts"] - outage["started_ts"]) / 3600.0
    drain_pct_per_hr = None
    if elapsed_h > 0 and outage["soc_start"] is not None:
        drop = outage["soc_start"] - latest["soc"]  # positive while discharging
        if drop > 0:
            drain_pct_per_hr = round(drop / elapsed_h, 1)

    window_start = max(latest["ts"] - _DRAIN_WINDOW_S, outage["started_ts"])
    rows = conn.execute(
        "SELECT load_w_total FROM samples WHERE ts >= ? ORDER BY ts",
        (window_start,),
    ).fetchall()
    smoothed_draw_w = (
        sum(r["load_w_total"] for r in rows) / len(rows) if rows else latest["load_w_total"]
    )
    usable_kwh = cfg.battery.nominal_kwh * cfg.battery.usable_fraction * (latest["soc"] / 100.0)
    runtime_h: float | None
    capped = False
    if smoothed_draw_w < MIN_DRAW_W:
        runtime_h, capped = None, True  # near-zero draw -> "> 24 hrs"
    else:
        runtime_h = usable_kwh * 1000.0 / smoothed_draw_w
        if runtime_h > CAP_HOURS:
            runtime_h, capped = CAP_HOURS, True
        else:
            runtime_h = round(runtime_h, 1)
    return {
        "drain_pct_per_hr": drain_pct_per_hr,
        "smoothed_draw_w": round(smoothed_draw_w),
        "runtime_remaining_h": runtime_h,
        "runtime_capped": capped,
    }


def build_current(conn: sqlite3.Connection, cfg: Config, now: float | None = None) -> dict:
    """The /api/current payload (also pushed over SSE)."""
    now = time.time() if now is None else now
    latest = latest_sample(conn)
    if latest is None:
        return {"ts": None, "age_s": None, "stale": True, "no_data": True}

    sample = _row_to_sample(latest)
    age_s = round(now - latest["ts"], 1)
    outage_row = active_outage(conn)

    payload: dict = {
        "ts": latest["ts"],
        "age_s": age_s,
        "stale": age_s > cfg.polling.stale_after_s,
        "no_data": False,
        "soc": sample.soc,
        "batt_v": sample.batt_v,
        "batt_a": sample.batt_a,
        "batt_w": sample.batt_w,
        "pv1_w": sample.pv1_w,
        "pv2_w": sample.pv2_w,
        "pv_w_total": sample.pv_w_total,
        "grid_v_l1": sample.grid_v_l1,
        "grid_v_l2": sample.grid_v_l2,
        "load_w_l1": sample.load_w_l1,
        "load_w_l2": sample.load_w_l2,
        "load_w_total": sample.load_w_total,
        "load_pct_l1": sample.load_pct_l1,
        "load_pct_l2": sample.load_pct_l2,
        "machine_state": sample.machine_state,
        "machine_state_name": MACHINE_STATES.get(sample.machine_state, "unknown"),
        "fault_active": sample.fault_active,
        "on_battery": on_battery(sample),
        "flow": flow(sample),
        "load_a_l1": round(sample.load_w_l1 / NOMINAL_LEG_V, 1),
        "load_a_l2": round(sample.load_w_l2 / NOMINAL_LEG_V, 1),
        "headroom": {
            "continuous_load_w": cfg.thresholds.continuous_load_w,
            "available_w": max(0, cfg.thresholds.continuous_load_w - sample.load_w_total),
            "bypass_a_per_leg": cfg.thresholds.bypass_amps_per_leg,
            "bypass_w_per_leg": round(cfg.thresholds.bypass_amps_per_leg * NOMINAL_LEG_V),
        },
    }

    if outage_row is not None:
        elapsed = int(latest["ts"] - outage_row["started_ts"])
        payload["outage"] = {
            "active": True,
            "started_ts": outage_row["started_ts"],
            "elapsed_s": elapsed,
            "soc_start": outage_row["soc_start"],
            "low_soc_pct": cfg.thresholds.low_soc_alert_pct,
            "sun_events": next_sun_events(cfg.location.lat, cfg.location.lon, now),
            **_drain_and_runtime(conn, cfg, latest, outage_row),
        }
    else:
        payload["outage"] = None
    return payload


def recent_samples(conn: sqlite3.Connection, window_s: int) -> dict:
    """Trimmed recent samples for drain context / future sparklines."""
    window_s = max(1, min(window_s, 6 * 3600))  # cap at 6h to keep payloads light
    cutoff = int(time.time()) - window_s
    rows = conn.execute(
        "SELECT ts, soc, batt_w, load_w_total, grid_v_l1,"
        " (pv1_w + pv2_w) AS pv_w_total FROM samples WHERE ts >= ? ORDER BY ts",
        (cutoff,),
    ).fetchall()
    return {
        "window_s": window_s,
        "count": len(rows),
        "samples": [dict(r) for r in rows],
    }


def settings_payload(cfg: Config) -> dict:
    """Safe config subset for the UI. No stick credentials."""
    return {
        "poll_interval_s": cfg.polling.interval_s,
        "stale_after_s": cfg.polling.stale_after_s,
        "battery": {
            "nominal_kwh": cfg.battery.nominal_kwh,
            "usable_fraction": cfg.battery.usable_fraction,
        },
        "thresholds": {
            "continuous_load_w": cfg.thresholds.continuous_load_w,
            "low_soc_alert_pct": cfg.thresholds.low_soc_alert_pct,
            "bypass_a_per_leg": cfg.thresholds.bypass_amps_per_leg,
            "bypass_w_per_leg": round(cfg.thresholds.bypass_amps_per_leg * NOMINAL_LEG_V),
        },
        "timezone": cfg.tou.timezone,
        # Real sun events here too, so the demo/simulated outage review can
        # show tonight's actual sunrise without a live outage in the DB.
        "sun_events": next_sun_events(cfg.location.lat, cfg.location.lon, time.time()),
    }
