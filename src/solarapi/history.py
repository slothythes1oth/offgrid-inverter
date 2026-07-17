"""History API queries (SPEC sections 4, 5, 8-History, 8A, 8B).

All read-only. Source selection is honest about resolution: short spans read
raw `samples`, long spans read `rollup_1m` (optionally re-bucketed) so a 30d
view never ships hundreds of thousands of points. Gaps are returned as
explicit spans AND as null points in the series so charts break the line
(connectNulls=false) instead of interpolating across collector downtime.

Energy math note (v1, no PV): the battery only ever charges from the grid,
so rollup batt_w sign is sufficient — negative avg = grid charging, positive
avg = battery serving the house. When PV arrives this needs a PV-aware split.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from solarmon.config import Config
from solarmon.registers import MACHINE_STATES, fault_name
from solarmon.tou import band

# Meaningful battery power threshold, mirrors derived.CHARGE_MIN_W.
_BATT_MIN_W = 100.0

# Preset windows: (span_s, source, bucket_s). bucket_s == 0 -> native rows.
WINDOWS = {
    "1h": (3600, "samples", 0),
    "24h": (86400, "rollup", 0),
    "7d": (7 * 86400, "rollup", 600),
    "30d": (30 * 86400, "rollup", 1800),
}


# Custom-span source selection (zoom drill-down): finest source that keeps
# the payload under ~2200 points.
def _pick_source(span_s: int) -> tuple[str, int, int]:
    """-> (source, bucket_s, expected_step_s)"""
    if span_s <= 3 * 3600:
        return "samples", 0, 5
    if span_s <= 48 * 3600:
        return "rollup", 0, 60
    if span_s <= 10 * 86400:
        return "rollup", 600, 600
    return "rollup", 1800, 1800


def _series_rows(conn: sqlite3.Connection, source: str, bucket_s: int, t0: int, t1: int) -> list:
    if source == "samples":
        return conn.execute(
            "SELECT ts AS t, load_w_total AS avg, load_w_total AS min,"
            " load_w_total AS max, soc FROM samples WHERE ts >= ? AND ts <= ? ORDER BY ts",
            (t0, t1),
        ).fetchall()
    if bucket_s:
        return conn.execute(
            "SELECT (minute_ts / ?) * ? AS t, AVG(load_w_avg) AS avg, MIN(load_w_min) AS min,"
            " MAX(load_w_max) AS max, AVG(soc_avg) AS soc FROM rollup_1m"
            " WHERE minute_ts >= ? AND minute_ts <= ? GROUP BY t ORDER BY t",
            (bucket_s, bucket_s, t0, t1),
        ).fetchall()
    return conn.execute(
        "SELECT minute_ts AS t, load_w_avg AS avg, load_w_min AS min, load_w_max AS max,"
        " soc_avg AS soc FROM rollup_1m WHERE minute_ts >= ? AND minute_ts <= ? ORDER BY minute_ts",
        (t0, t1),
    ).fetchall()


def load_series(
    conn: sqlite3.Connection,
    cfg: Config,
    window: str | None = None,
    t_from: int | None = None,
    t_to: int | None = None,
    now: int | None = None,
) -> dict:
    """Load-profile series with explicit gaps and chart metadata."""
    now = int(datetime.now().timestamp()) if now is None else int(now)
    if window is not None:
        if window not in WINDOWS:
            raise ValueError(f"unknown window {window!r}; use one of {sorted(WINDOWS)}")
        span, source, bucket_s = WINDOWS[window]
        t1, t0 = now, now - span
        step = bucket_s or (5 if source == "samples" else 60)
    else:
        if t_from is None or t_to is None or t_to <= t_from:
            raise ValueError("custom range needs from < to")
        t0, t1 = int(t_from), int(t_to)
        source, bucket_s, step = _pick_source(t1 - t0)

    rows = _series_rows(conn, source, bucket_s, t0, t1)

    # Gaps: consecutive points further apart than 2.5x the expected step.
    # Null points break the chart line; spans drive the "no data" shading.
    points: list[list] = []
    gaps: list[list[int]] = []
    prev_t = None
    for r in rows:
        if prev_t is not None and r["t"] - prev_t > step * 2.5:
            gaps.append([prev_t + step, r["t"]])
            points.append([prev_t + step, None, None, None, None])
        points.append(
            [r["t"], round(r["avg"]), round(r["min"]), round(r["max"]), round(r["soc"], 1)]
        )
        prev_t = r["t"]
    # Trailing gap up to "now" (collector down right now) for preset windows.
    if window is not None and prev_t is not None and now - prev_t > step * 2.5:
        gaps.append([prev_t + step, now])
        points.append([prev_t + step, None, None, None, None])

    peaks = [
        dict(r)
        for r in conn.execute(
            "SELECT period, period_key, load_w, ts FROM peaks"
            " WHERE period = 'all' OR (ts >= ? AND ts <= ?) ORDER BY ts",
            (t0, t1),
        )
    ]
    bypass_w_leg = round(cfg.thresholds.bypass_amps_per_leg * 120)
    return {
        "window": window,
        "from": t0,
        "to": t1,
        "source": source,
        "step_s": step,
        "count": len(points),
        # points: [ts, load_avg_w, load_min_w, load_max_w, soc]; nulls = gap
        "points": points,
        "gaps": gaps,
        "thresholds": {
            "continuous_load_w": cfg.thresholds.continuous_load_w,
            "bypass_a_per_leg": cfg.thresholds.bypass_amps_per_leg,
            "bypass_w_per_leg": bypass_w_leg,
            "bypass_w_total_balanced": bypass_w_leg * 2,
        },
        "sampled_peaks": peaks,  # always labeled "sampled" in the UI
    }


# ---------------------------------------------------------------- events ---

_EVENT_SUMMARY_KEYS = ("soc", "load_w_total", "gap_s", "duration_s", "kwh_used", "pack_count")


def _fault_codes_named(detail: dict) -> list[dict]:
    return [{"code": c, "name": fault_name(c)} for c in detail.get("fault_codes", [])]


def events_page(
    conn: sqlite3.Connection,
    limit: int = 50,
    before_id: int | None = None,
    types: list[str] | None = None,
) -> dict:
    """Reverse-chron page of events, keyset-paginated by id. The collector
    inserts events in time order, so id order == time order."""
    limit = max(1, min(limit, 200))
    clauses, params = [], []
    if before_id is not None:
        clauses.append("id < ?")
        params.append(before_id)
    if types:
        clauses.append(f"type IN ({','.join('?' * len(types))})")
        params.extend(types)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT id, ts, type, detail FROM events {where} ORDER BY id DESC LIMIT ?",  # noqa: S608
        (*params, limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    items = []
    for r in rows[:limit]:
        detail = json.loads(r["detail"]) if r["detail"] else {}
        items.append(
            {
                "id": r["id"],
                "ts": r["ts"],
                "type": r["type"],
                "fault_codes": _fault_codes_named(detail),
                **{k: detail[k] for k in _EVENT_SUMMARY_KEYS if k in detail},
            }
        )
    return {
        "items": items,
        "has_more": has_more,
        "next_before_id": items[-1]["id"] if items and has_more else None,
    }


def event_trace(conn: sqlite3.Connection, event_id: int, window_s: int = 600) -> dict | None:
    """Flight-recorder payload (SPEC 8B.6): +/- window_s trace around the
    event plus a plain-language facts panel from the captured snapshot."""
    row = conn.execute(
        "SELECT id, ts, type, detail FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return None
    detail = json.loads(row["detail"]) if row["detail"] else {}
    t0, t1 = row["ts"] - window_s, row["ts"] + window_s

    # Raw samples if they still cover the window (30d retention), else rollups.
    have_raw = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM samples WHERE ts >= ? AND ts <= ?)", (t0, t1)
    ).fetchone()[0]
    source = "samples" if have_raw else "rollup"
    rows = _series_rows(conn, source, 0, t0, t1)
    step = 5 if source == "samples" else 60
    points, prev_t = [], None
    for r in rows:
        if prev_t is not None and r["t"] - prev_t > step * 2.5:
            points.append([prev_t + step, None, None])
        points.append([r["t"], round(r["avg"]), round(r["soc"], 1)])
        prev_t = r["t"]

    snapshot = detail.get("snapshot", {})
    state = snapshot.get("machine_state")
    return {
        "id": row["id"],
        "ts": row["ts"],
        "type": row["type"],
        "trace": {"source": source, "step_s": step, "points": points},  # [ts, load_w, soc]
        "facts": {
            "fault_codes": _fault_codes_named(detail),
            "machine_state": state,
            "machine_state_name": (
                MACHINE_STATES.get(state, "unknown") if state is not None else None
            ),
            "soc": detail.get("soc", snapshot.get("soc")),
            "load_w_total": detail.get("load_w_total", snapshot.get("load_w_total")),
            "load_w_l1": snapshot.get("load_w_l1"),
            "load_w_l2": snapshot.get("load_w_l2"),
            "load_a_l1": round(snapshot["load_w_l1"] / 120, 1) if "load_w_l1" in snapshot else None,
            "load_a_l2": round(snapshot["load_w_l2"] / 120, 1) if "load_w_l2" in snapshot else None,
            "batt_v": snapshot.get("batt_v"),
            "batt_w": snapshot.get("batt_w"),
        },
        "detail": detail,
    }


# --------------------------------------------------------------- outages ---


def outages_page(conn: sqlite3.Connection, limit: int = 50) -> dict:
    limit = max(1, min(limit, 500))
    items = [
        dict(r)
        for r in conn.execute(
            "SELECT id, started_ts, ended_ts, duration_s, soc_start, soc_end, kwh_used"
            " FROM outages ORDER BY started_ts DESC LIMIT ?",
            (limit,),
        )
    ]
    stats = conn.execute(
        "SELECT COUNT(*) AS count, AVG(duration_s) AS avg_duration_s,"
        " MAX(duration_s) AS longest_s, SUM(kwh_used) AS total_kwh, AVG(kwh_used) AS avg_kwh"
        " FROM outages WHERE ended_ts IS NOT NULL"
    ).fetchone()
    return {
        "items": items,
        "stats": {
            "count": stats["count"],
            "avg_duration_s": round(stats["avg_duration_s"]) if stats["avg_duration_s"] else None,
            "longest_s": stats["longest_s"],
            "total_kwh": round(stats["total_kwh"], 2) if stats["total_kwh"] else 0,
            "avg_kwh": round(stats["avg_kwh"], 2) if stats["avg_kwh"] else None,
        },
    }


# ------------------------------------------------------------------- TOU ---


def _hourly_energy(conn: sqlite3.Connection, t0: int, t1: int) -> list:
    """Hourly kWh from rollups: consumption, grid-charge, battery-served.
    UTC-hour buckets align with Toronto local hours (whole-hour offset)."""
    return conn.execute(
        "SELECT (minute_ts / 3600) * 3600 AS h,"
        " SUM(load_w_avg) / 60000.0 AS kwh,"
        " SUM(CASE WHEN batt_w_avg < -? THEN -batt_w_avg ELSE 0 END) / 60000.0 AS charge_kwh,"
        " SUM(CASE WHEN batt_w_avg > ? THEN"
        "   MIN(CAST(batt_w_avg AS REAL), load_w_avg) ELSE 0 END) / 60000.0 AS served_kwh,"
        " MIN(soc_min) AS soc_min, MAX(soc_max) AS soc_max"
        " FROM rollup_1m WHERE minute_ts >= ? AND minute_ts < ? GROUP BY h ORDER BY h",
        (_BATT_MIN_W, _BATT_MIN_W, t0, t1),
    ).fetchall()


def _rates(cfg: Config, off=None, mid=None, on=None, all_in=None) -> dict:
    r = cfg.tou.rates_cents_per_kwh
    return {
        "off_peak": off if off is not None else r.off_peak,
        "mid_peak": mid if mid is not None else r.mid_peak,
        "on_peak": on if on is not None else r.on_peak,
        "all_in_override": all_in if all_in is not None else cfg.tou.all_in_override_cents_per_kwh,
    }


def _rate_for(rates: dict, b: str) -> float:
    return rates["all_in_override"] if rates["all_in_override"] is not None else rates[b]


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[int, int]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def tou_daily(
    conn: sqlite3.Connection,
    cfg: Config,
    days: int = 60,
    now: int | None = None,
    **rate_overrides,
) -> dict:
    """Per-local-day energy + supply-only cost by band, grid-charge cost,
    peak-avoidance savings, and an outage badge. Feeds the calendar heatmap
    (8B.5), the stacked bars (8A), and the savings view."""
    days = max(1, min(days, 400))
    tz = ZoneInfo(cfg.tou.timezone)
    now = int(datetime.now().timestamp()) if now is None else int(now)
    today = datetime.fromtimestamp(now, tz).date()
    t0, _ = _local_day_bounds(today - timedelta(days=days - 1), tz)
    _, t1 = _local_day_bounds(today, tz)
    rates = _rates(cfg, **rate_overrides)

    day_map: dict[str, dict] = {}
    for r in _hourly_energy(conn, t0, t1):
        local = datetime.fromtimestamp(r["h"], tz)
        key = local.date().isoformat()
        d = day_map.setdefault(
            key,
            {
                "date": key,
                "kwh": {"off_peak": 0.0, "mid_peak": 0.0, "on_peak": 0.0},
                "grid_charge_kwh": 0.0,
                "grid_charge_cost_cents": 0.0,
                "battery_served_on_peak_kwh": 0.0,
            },
        )
        b = band(local)
        d["kwh"][b] += r["kwh"]
        d["grid_charge_kwh"] += r["charge_kwh"]
        d["grid_charge_cost_cents"] += r["charge_kwh"] * _rate_for(rates, b)
        if b == "on_peak":
            d["battery_served_on_peak_kwh"] += r["served_kwh"]

    outage_days = set()
    for r in conn.execute(
        "SELECT started_ts, COALESCE(ended_ts, started_ts) AS e FROM outages"
        " WHERE COALESCE(ended_ts, started_ts) >= ? AND started_ts < ?",
        (t0, t1),
    ):
        d = datetime.fromtimestamp(r["started_ts"], tz).date()
        end = datetime.fromtimestamp(r["e"], tz).date()
        while d <= end:
            outage_days.add(d.isoformat())
            d += timedelta(days=1)

    items = []
    for key in sorted(day_map):
        d = day_map[key]
        cost = {b: round(d["kwh"][b] * _rate_for(rates, b), 1) for b in d["kwh"]}
        items.append(
            {
                "date": key,
                "kwh": {b: round(v, 2) for b, v in d["kwh"].items()},
                "total_kwh": round(sum(d["kwh"].values()), 2),
                "cost_cents": {**cost, "total": round(sum(cost.values()), 1)},
                "grid_charge_kwh": round(d["grid_charge_kwh"], 2),
                "grid_charge_cost_cents": round(d["grid_charge_cost_cents"], 1),
                "battery_served_on_peak_kwh": round(d["battery_served_on_peak_kwh"], 2),
                "savings_cents": round(
                    d["battery_served_on_peak_kwh"] * (rates["on_peak"] - rates["off_peak"]), 1
                ),
                "outage": key in outage_days,
            }
        )
    return {"days": days, "rates": rates, "items": items}


def tou_day(conn: sqlite3.Connection, cfg: Config, date_str: str, **rate_overrides) -> dict:
    """One local day, hour by hour, for the TOU day-ring (8B.4): each hour's
    band (from the TOU engine, so seasonal windows are always right), kWh,
    and cost. DST days have 23/25 UTC hours; the ring maps by local hour."""
    tz = ZoneInfo(cfg.tou.timezone)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    t0, t1 = _local_day_bounds(day, tz)
    rates = _rates(cfg, **rate_overrides)
    by_hour = {r["h"]: r for r in _hourly_energy(conn, t0, t1)}

    hours = []
    t = t0
    while t < t1:
        local = datetime.fromtimestamp(t, tz)
        b = band(local)
        r = by_hour.get(t)
        kwh = round(r["kwh"], 3) if r else None  # None = no data that hour
        hours.append(
            {
                "ts": t,
                "local_hour": local.hour,
                "band": b,
                "kwh": kwh,
                "cost_cents": round(kwh * _rate_for(rates, b), 2) if kwh is not None else None,
            }
        )
        t += 3600
    total_kwh = sum(h["kwh"] for h in hours if h["kwh"] is not None)
    total_cost = sum(h["cost_cents"] for h in hours if h["cost_cents"] is not None)
    return {
        "date": date_str,
        "rates": rates,
        "hours": hours,
        "total_kwh": round(total_kwh, 2),
        "total_cost_cents": round(total_cost, 1),
    }


# --------------------------------------------------------------- battery ---


def battery_daily(
    conn: sqlite3.Connection, cfg: Config, days: int = 90, now: int | None = None
) -> dict:
    """Daily SoC min/max band + mean and DoD summary (History #5)."""
    days = max(1, min(days, 400))
    tz = ZoneInfo(cfg.tou.timezone)
    now = int(datetime.now().timestamp()) if now is None else int(now)
    today = datetime.fromtimestamp(now, tz).date()
    t0, _ = _local_day_bounds(today - timedelta(days=days - 1), tz)
    _, t1 = _local_day_bounds(today, tz)

    day_map: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT (minute_ts / 3600) * 3600 AS h, MIN(soc_min) AS mn, MAX(soc_max) AS mx,"
        " AVG(soc_avg) AS avg FROM rollup_1m WHERE minute_ts >= ? AND minute_ts < ?"
        " GROUP BY h ORDER BY h",
        (t0, t1),
    ):
        key = datetime.fromtimestamp(r["h"], tz).date().isoformat()
        d = day_map.setdefault(
            key, {"date": key, "soc_min": 100, "soc_max": 0, "_sum": 0.0, "_n": 0}
        )
        d["soc_min"] = min(d["soc_min"], r["mn"])
        d["soc_max"] = max(d["soc_max"], r["mx"])
        d["_sum"] += r["avg"]
        d["_n"] += 1

    items = []
    for key in sorted(day_map):
        d = day_map[key]
        items.append(
            {
                "date": key,
                "soc_min": d["soc_min"],
                "soc_max": d["soc_max"],
                "soc_avg": round(d["_sum"] / d["_n"], 1),
                "dod": d["soc_max"] - d["soc_min"],
            }
        )
    dods = [i["dod"] for i in items]
    return {
        "days": days,
        "items": items,
        "summary": {
            "avg_dod": round(sum(dods) / len(dods), 1) if dods else None,
            "max_dod": max(dods) if dods else None,
            "days_with_data": len(items),
        },
    }
