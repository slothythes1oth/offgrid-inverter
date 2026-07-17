"""Outage detection with debounce, plus the outages ledger.

The raw condition (grid_v_l1 ~0 AND machine_state=5) must persist for
`debounce_polls` consecutive polls (~15s at 3x5s) before an outage is declared
or ended; brief flickers never register. kWh used is integrated from load
power (battery serves the whole load during an outage; sign-free, so immune
to the provisional battery-current sign).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from solarmon.derived import on_battery
from solarmon.registers import Sample

log = logging.getLogger("outage")


@dataclass
class OutageTransition:
    kind: str  # "grid_lost" | "grid_restored"
    ts: int
    outage_id: int
    detail: dict


class OutageTracker:
    def __init__(self, debounce_polls: int, low_soc_pct: int):
        self.debounce_polls = debounce_polls
        self.low_soc_pct = low_soc_pct
        self.on_battery_state = False  # debounced state
        self._streak = 0
        self._streak_first: Sample | None = None
        self.outage_id: int | None = None
        self._kwh_acc = 0.0
        self._soc_start: int | None = None
        self._started_ts: int | None = None
        self.low_soc_fired = False

    def resume(self, conn: sqlite3.Connection) -> None:
        """On collector start, pick up an outage the previous run left open,
        so a restart mid-outage neither loses it nor re-alerts it."""
        row = conn.execute(
            "SELECT id, started_ts, soc_start, kwh_used FROM outages"
            " WHERE ended_ts IS NULL ORDER BY started_ts DESC LIMIT 1"
        ).fetchone()
        if row:
            self.on_battery_state = True
            self.outage_id = row["id"]
            self._started_ts = row["started_ts"]
            self._soc_start = row["soc_start"]
            self._kwh_acc = row["kwh_used"] or 0.0
            log.info("resumed open outage id=%d started_ts=%d", row["id"], row["started_ts"])

    def update(
        self, conn: sqlite3.Connection, sample: Sample, dt_s: float
    ) -> list[OutageTransition]:
        """Feed one sample. Returns transitions (0 or 1) that just happened."""
        raw = on_battery(sample)
        transitions: list[OutageTransition] = []

        if raw != self.on_battery_state:
            if self._streak == 0:
                self._streak_first = sample
            self._streak += 1
            if self._streak >= self.debounce_polls:
                first = self._streak_first or sample
                if raw:
                    transitions.append(self._declare_outage(conn, first, sample))
                else:
                    transitions.append(self._end_outage(conn, first, sample))
                self.on_battery_state = raw
                self._streak = 0
                self._streak_first = None
        else:
            self._streak = 0
            self._streak_first = None

        # Integrate energy while on battery (including debounce lag polls).
        if self.on_battery_state or raw:
            self._kwh_acc += sample.load_w_total * dt_s / 3_600_000.0
            if self.outage_id is not None:
                conn.execute(
                    "UPDATE outages SET kwh_used = ?, soc_end = ? WHERE id = ?",
                    (round(self._kwh_acc, 3), sample.soc, self.outage_id),
                )
        return transitions

    def low_soc_crossed(self, sample: Sample) -> bool:
        """True exactly once per outage, when SoC first drops below threshold."""
        if self.on_battery_state and not self.low_soc_fired and sample.soc < self.low_soc_pct:
            self.low_soc_fired = True
            return True
        return False

    def _declare_outage(
        self, conn: sqlite3.Connection, first: Sample, sample: Sample
    ) -> OutageTransition:
        self._started_ts = first.ts
        self._soc_start = first.soc
        self._kwh_acc = 0.0
        self.low_soc_fired = False
        cur = conn.execute(
            "INSERT INTO outages (started_ts, soc_start, soc_end, kwh_used)" " VALUES (?, ?, ?, 0)",
            (first.ts, first.soc, sample.soc),
        )
        self.outage_id = cur.lastrowid
        log.info("outage declared id=%d started_ts=%d soc=%d", self.outage_id, first.ts, first.soc)
        return OutageTransition("grid_lost", sample.ts, self.outage_id, sample.snapshot())

    def _end_outage(
        self, conn: sqlite3.Connection, first: Sample, sample: Sample
    ) -> OutageTransition:
        ended_ts = first.ts  # grid actually came back at the start of the streak
        detail = sample.snapshot()
        outage_id = self.outage_id
        if outage_id is not None:
            duration = ended_ts - (self._started_ts or ended_ts)
            conn.execute(
                "UPDATE outages SET ended_ts=?, duration_s=?, soc_end=?, kwh_used=?" " WHERE id=?",
                (ended_ts, duration, sample.soc, round(self._kwh_acc, 3), outage_id),
            )
            detail.update(
                {
                    "duration_s": duration,
                    "soc_start": self._soc_start,
                    "kwh_used": round(self._kwh_acc, 3),
                }
            )
            log.info("outage ended id=%d duration_s=%d", outage_id, duration)
        else:
            # Collector started already on battery with no open outage row:
            # we saw the restore edge but not the loss. Record honestly.
            log.warning("grid restored but no open outage row; edge-only event")
            outage_id = -1
        self.outage_id = None
        self._kwh_acc = 0.0
        return OutageTransition("grid_restored", sample.ts, outage_id, detail)


def event_detail_json(detail: dict) -> str:
    return json.dumps(detail, separators=(",", ":"))
