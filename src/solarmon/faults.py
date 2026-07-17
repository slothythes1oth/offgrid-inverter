"""Fault capture: raise/clear events with the same-poll load snapshot.

The inverter latches faults in hardware; that latch is the authoritative
surge record. We capture which codes were active and what the load looked
like on the exact poll the fault appeared. Dedupe: an ongoing fault fires
exactly one raised event until it clears.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from solarmon.registers import Sample, fault_name

log = logging.getLogger("faults")


@dataclass
class FaultTransition:
    kind: str  # "fault_raised" | "fault_cleared"
    ts: int
    codes: tuple[int, ...]
    detail: dict


class FaultTracker:
    def __init__(self) -> None:
        self.active_codes: tuple[int, ...] = ()

    def resume(self, conn: sqlite3.Connection) -> None:
        """Seed from the event log so a collector restart during a latched
        fault does not re-fire the raised event."""
        row = conn.execute(
            "SELECT type, detail FROM events WHERE type IN ('fault_raised','fault_cleared')"
            " ORDER BY ts DESC, id DESC LIMIT 1"
        ).fetchone()
        if row and row["type"] == "fault_raised":
            try:
                self.active_codes = tuple(json.loads(row["detail"]).get("fault_codes", []))
            except (json.JSONDecodeError, TypeError):
                self.active_codes = ()
            if self.active_codes:
                log.info("resumed active fault codes=%s", list(self.active_codes))

    def update(self, sample: Sample) -> list[FaultTransition]:
        codes = sample.fault_codes if sample.fault_active else ()
        transitions: list[FaultTransition] = []
        if codes and codes != self.active_codes:
            detail = sample.snapshot()
            detail["fault_names"] = [fault_name(c) for c in codes]
            transitions.append(FaultTransition("fault_raised", sample.ts, codes, detail))
            log.info("fault raised codes=%s", list(codes))
        elif not codes and self.active_codes:
            detail = sample.snapshot()
            detail["cleared_codes"] = list(self.active_codes)
            transitions.append(
                FaultTransition("fault_cleared", sample.ts, self.active_codes, detail)
            )
            log.info("fault cleared codes=%s", list(self.active_codes))
        self.active_codes = codes
        return transitions
