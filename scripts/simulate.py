"""Checkpoint-d simulation: drive the FULL collector through an outage and a
fault using the fake register source. No hardware, no real DB: a throwaway
SQLite file in a temp dir. Alerts are dry-run (no ntfy topic configured).

Run: .venv/Scripts/python scripts/simulate.py

Scenario timeline (5s fake polls):
  t+0:00  on grid, charging, quiet
  t+0:30  GRID FAILS          -> outage declared after 3 polls (~15s debounce)
  t+2:00  SoC decays to 39%   -> low_soc event + alert (threshold 40)
  t+4:00  load spike trips fault 13 (bypass overload) -> fault event + alert
  t+4:30  fault cleared
  t+5:00  GRID RETURNS        -> outage closed after debounce, restore alert
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solarmon.collector import Collector  # noqa: E402
from solarmon.config import load_config  # noqa: E402
from solarmon.db import open_for_collector  # noqa: E402
from solarmon.fake_source import FakeSource  # noqa: E402
from solarmon.log import setup_logging  # noqa: E402


class FakeClock:
    def __init__(self, start=1_784_700_000.0):
        self.t = start

    def __call__(self):
        return self.t


def main() -> None:
    setup_logging("INFO", file=None)
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    tmp = Path(tempfile.mkdtemp(prefix="solarmon-sim-")) / "sim.db"
    conn = open_for_collector(tmp)
    clock = FakeClock()
    src = FakeSource()
    src.set_grid(True)
    col = Collector(cfg, conn, src, now_fn=clock)
    col.startup()

    soc = 96

    def polls(n, mutate=None):
        nonlocal soc
        for _ in range(n):
            clock.t += 5
            if mutate:
                mutate()
            col.run_cycle()

    print("\n=== phase 1: on grid, quiet (30s) ===")
    polls(6)

    print("\n=== phase 2: grid fails ===")
    src.set_grid(False)
    polls(18)  # 90s on battery

    print("\n=== phase 3: SoC decays below the 40% alert threshold ===")

    def decay():
        nonlocal soc
        soc = max(38, soc - 3)
        src.set_soc(soc)

    polls(24, mutate=decay)  # 2 min of decline to 38%

    print("\n=== phase 4: surge trips fault 13 (bypass overload) ===")
    src.set_load(4800, 1900)
    src.raise_fault(13)
    polls(3)
    print("\n=== phase 5: fault clears, load back to normal ===")
    src.clear_faults()
    src.set_grid(False)  # clear_faults reset state; still off-grid
    src.set_load(312, 154)
    polls(3)

    print("\n=== phase 6: grid returns ===")
    src.set_grid(True)
    polls(6)
    col.shutdown()

    print("\n=== RESULTS ===")
    print("\nevents:")
    for r in conn.execute("SELECT ts, type, detail FROM events ORDER BY ts, id"):
        detail = json.loads(r["detail"]) if r["detail"] else {}
        keys = {
            k: detail[k]
            for k in ("gap_s", "soc", "load_w_total", "fault_codes", "duration_s", "kwh_used")
            if k in detail
        }
        print(f"  {r['ts']}  {r['type']:<16} {keys}")
    print("\noutages:")
    for r in conn.execute("SELECT * FROM outages"):
        print(
            f"  id={r['id']} started={r['started_ts']} ended={r['ended_ts']}"
            f" duration_s={r['duration_s']} soc {r['soc_start']}->{r['soc_end']}"
            f" kwh_used={r['kwh_used']}"
        )
    n = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    print(f"\nsamples written: {n}   (db: {tmp})")


if __name__ == "__main__":
    main()
