"""The collector: 5s poll loop wiring source -> decode -> DB -> engines -> alerts.

Testable headless: source, clock and sleep are injected, so tests drive
run_cycle() directly against a FakeSource with a synthetic clock. The real
main loop in main.py only adds scheduling and signal handling around this.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable

from solarmon.alerts import PRIORITY_CRITICAL, PRIORITY_DEFAULT, AlertManager, fmt_duration
from solarmon.config import Config
from solarmon.faults import FaultTracker
from solarmon.log import kv
from solarmon.outage import OutageTracker
from solarmon.peaks import update_peaks
from solarmon.registers import Sample, decode, fault_name
from solarmon.rollup import build_rollups, prune_if_new_day
from solarmon.runtime_est import RuntimeEstimator

log = logging.getLogger("collector")

GAP_THRESHOLD_S = 60  # a restart within this of the last sample is not a gap

_INSERT_SAMPLE = (
    "INSERT OR REPLACE INTO samples (ts, soc, batt_v, batt_a, batt_w, pv1_w, pv2_w,"
    " grid_v_l1, grid_v_l2, load_w_l1, load_w_l2, load_w_total, load_pct_l1,"
    " load_pct_l2, machine_state, fault_active)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class Collector:
    def __init__(
        self,
        cfg: Config,
        conn: sqlite3.Connection,
        source,
        alert_mgr: AlertManager | None = None,
        now_fn: Callable[[], float] = time.time,
    ):
        self.cfg = cfg
        self.conn = conn
        self.source = source
        self.alerts = alert_mgr or AlertManager(cfg.alerts)
        self.now = now_fn
        self.outage = OutageTracker(cfg.outage.debounce_polls, cfg.thresholds.low_soc_alert_pct)
        self.faults = FaultTracker()
        self.estimator = RuntimeEstimator(cfg.runtime_estimator.ema_window_min * 60)
        self._last_sample_ts: float | None = None
        self._stale_logged = False
        self.cycles_ok = 0
        self.cycles_failed = 0

    # -- lifecycle -------------------------------------------------------

    def startup(self) -> None:
        now = int(self.now())
        self._check_gap(now)
        self._write_event(now, "collector_start", {"pid_note": "collector starting"})
        self.outage.resume(self.conn)
        self.faults.resume(self.conn)
        if self.outage.on_battery_state:
            self.alerts.mark_active("outage")  # do not re-alert an ongoing outage
        if self.faults.active_codes:
            self.alerts.mark_active("fault")
        self.conn.commit()

    def shutdown(self) -> None:
        now = int(self.now())
        self._write_event(now, "collector_stop", {"cycles_ok": self.cycles_ok})
        self.conn.commit()
        self.source.disconnect()
        kv(log, logging.INFO, "collector stopped", cycles_ok=self.cycles_ok)

    def _check_gap(self, now: int) -> None:
        row = self.conn.execute("SELECT MAX(ts) AS t FROM samples").fetchone()
        if row["t"] is not None and now - row["t"] > GAP_THRESHOLD_S:
            gap_s = now - row["t"]
            self._write_event(now, "gap_detected", {"last_sample_ts": row["t"], "gap_s": gap_s})
            kv(log, logging.INFO, "gap detected", gap_s=gap_s)

    # -- one poll cycle ----------------------------------------------------

    def run_cycle(self) -> Sample | None:
        """One poll: read, decode, persist, run engines. Returns the sample
        or None on a failed cycle."""
        t0 = self.now()
        regs = self.source.read_cycle()
        now = int(self.now())
        if regs is None:
            self.cycles_failed += 1
            self._note_staleness(now)
            kv(log, logging.WARNING, "poll failed", failed=self.cycles_failed)
            return None

        sample = decode(regs, now)
        dt_s = (
            min(
                float(now - self._last_sample_ts) if self._last_sample_ts else 0.0,
                self.cfg.polling.interval_s * 3,  # a gap must not dump energy into integrals
            )
            or self.cfg.polling.interval_s
        )

        with self.conn:  # everything for this poll commits atomically
            self.conn.execute(_INSERT_SAMPLE, self._sample_row(sample))
            self._run_engines(sample, dt_s)
            build_rollups(self.conn, now)
            prune_if_new_day(
                self.conn, now, self.cfg.database.retention_days_raw, self.cfg.tou.timezone
            )

        if self._stale_logged:
            kv(log, logging.INFO, "data fresh again", stale_for_s=now - int(self._last_sample_ts))
            self._stale_logged = False
        self._last_sample_ts = now
        self.cycles_ok += 1
        kv(
            log,
            logging.INFO,
            "poll ok",
            soc=sample.soc,
            load_w=sample.load_w_total,
            batt_v=sample.batt_v,
            batt_w=sample.batt_w,
            grid_v=sample.grid_v_l1,
            state=sample.machine_state,
            fault=int(sample.fault_active),
            ms=int((self.now() - t0) * 1000),
        )
        return sample

    def _run_engines(self, sample: Sample, dt_s: float) -> None:
        # Outage detection + ledger
        for tr in self.outage.update(self.conn, sample, dt_s):
            self._write_event(tr.ts, tr.kind, tr.detail)
            if tr.kind == "grid_lost":
                self.estimator.reset()
                self.alerts.alert_once(
                    "outage",
                    "Grid lost — on battery",
                    f"SoC {sample.soc}%, load {sample.load_w_total} W.",
                    PRIORITY_CRITICAL,
                )
            else:
                self.alerts.clear("outage")
                dur = fmt_duration(tr.detail.get("duration_s", 0))
                kwh = tr.detail.get("kwh_used", 0)
                self.alerts.alert_edge(
                    "Grid restored",
                    f"Outage lasted {dur}, used {kwh} kWh. SoC {sample.soc}%.",
                    PRIORITY_DEFAULT,
                )

        # Runtime estimator: feed load as draw while on battery
        if self.outage.on_battery_state:
            self.estimator.update(sample.load_w_total, dt_s)

        # Low SoC during an outage, once per outage
        if self.outage.low_soc_crossed(sample):
            self._write_event(sample.ts, "low_soc", sample.snapshot())
            hours, capped = self.estimator.runtime_hours(
                sample.soc, self.cfg.battery.nominal_kwh, self.cfg.battery.usable_fraction
            )
            left = "> 24 hrs" if capped else (f"~{hours:.1f} h" if hours else "unknown")
            self.alerts.alert_once(
                "low_soc",
                f"Battery at {sample.soc}% during outage",
                f"Below {self.cfg.thresholds.low_soc_alert_pct}% threshold."
                f" Load {sample.load_w_total} W, {left} left.",
                PRIORITY_CRITICAL,
            )
        if not self.outage.on_battery_state:
            self.alerts.clear("low_soc")

        # Faults, with same-poll snapshot
        for tr in self.faults.update(sample):
            self._write_event(tr.ts, tr.kind, tr.detail)
            if tr.kind == "fault_raised":
                names = ", ".join(f"{c} ({fault_name(c)})" for c in tr.codes)
                self.alerts.alert_once(
                    "fault",
                    f"Inverter fault: {names}",
                    f"Load {sample.load_w_total} W, SoC {sample.soc}%."
                    " Fault is latched by the inverter.",
                    PRIORITY_CRITICAL,
                )
            else:
                self.alerts.clear("fault")
                self.alerts.alert_edge("Inverter fault cleared", "All fault codes clear.")

        update_peaks(self.conn, sample, self.cfg.tou.timezone)

    # -- helpers ---------------------------------------------------------

    def _note_staleness(self, now: int) -> None:
        if self._last_sample_ts is None:
            return
        age = now - self._last_sample_ts
        if age > self.cfg.polling.stale_after_s and not self._stale_logged:
            kv(log, logging.WARNING, "data now stale", age_s=int(age))
            self._stale_logged = True

    def _write_event(self, ts: int, type_: str, detail: dict) -> None:
        self.conn.execute(
            "INSERT INTO events (ts, type, detail) VALUES (?, ?, ?)",
            (ts, type_, json.dumps(detail, separators=(",", ":"))),
        )

    @staticmethod
    def _sample_row(s: Sample) -> tuple:
        return (
            s.ts,
            s.soc,
            s.batt_v,
            s.batt_a,
            s.batt_w,
            s.pv1_w,
            s.pv2_w,
            s.grid_v_l1,
            s.grid_v_l2,
            s.load_w_l1,
            s.load_w_l2,
            s.load_w_total,
            s.load_pct_l1,
            s.load_pct_l2,
            s.machine_state,
            int(s.fault_active),
        )
