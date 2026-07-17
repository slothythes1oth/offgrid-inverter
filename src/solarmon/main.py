"""Collector entrypoint: the 5s poll loop with drift-corrected scheduling.

Run:            python -m solarmon.main
One-shot check: python -m solarmon.main --once   (poll once, print, disconnect)

Ctrl+C stops cleanly (collector_stop event). A hard kill skips that event;
the next start writes gap_detected instead, which is the honest record.
"""

from __future__ import annotations

import argparse
import logging
import time

from solarmon.collector import Collector
from solarmon.config import load_config
from solarmon.connection import SolarmanSource, StickLockoutError
from solarmon.db import open_for_collector
from solarmon.log import kv, setup_logging
from solarmon.registers import MACHINE_STATES

log = logging.getLogger("main")


def _print_sample(sample) -> None:
    print(f"ts              {sample.ts}")
    print(f"SOC             {sample.soc} %")
    print(f"Battery         {sample.batt_v} V  {sample.batt_a} A  {sample.batt_w} W")
    print(f"PV              {sample.pv1_w} + {sample.pv2_w} = {sample.pv_w_total} W")
    print(f"Grid L1/L2      {sample.grid_v_l1} / {sample.grid_v_l2} V")
    print(
        f"Load L1+L2      {sample.load_w_l1} + {sample.load_w_l2}"
        f" = {sample.load_w_total} W ({sample.load_pct_l1}%/{sample.load_pct_l2}%)"
    )
    print(
        f"Machine state   {sample.machine_state}"
        f" [{MACHINE_STATES.get(sample.machine_state, '?')}]"
    )
    print(f"Fault active    {sample.fault_active}  codes={list(sample.fault_codes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="solarmon collector")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("--once", action="store_true", help="single poll, print, exit")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging.level, cfg.logging.file)

    source = SolarmanSource(cfg.stick, cfg.polling)

    if args.once:
        regs = source.read_cycle()
        source.disconnect()
        if regs is None:
            raise SystemExit("poll failed; see log")
        from solarmon.registers import decode

        _print_sample(decode(regs, int(time.time())))
        return

    conn = open_for_collector(cfg.database.path, config_snapshot=cfg.model_dump())
    collector = Collector(cfg, conn, source)
    collector.startup()
    kv(log, logging.INFO, "collector started", interval_s=cfg.polling.interval_s)

    interval = cfg.polling.interval_s
    next_poll = time.monotonic()
    try:
        while True:
            try:
                collector.run_cycle()
            except StickLockoutError as e:
                # PROVEN.md: waited out the lockout once already. Tell Nik,
                # then retry gently (one attempt per lockout window), never a storm.
                log.error(
                    "STICK LOCKED OUT: %s — will retry every %ss; if this persists, "
                    "power-cycle the stick",
                    e,
                    cfg.polling.lockout_wait_s,
                )
                time.sleep(cfg.polling.lockout_wait_s)
            # Drift-corrected 5s cadence: long cycles skip missed slots
            # instead of bursting reads to catch up.
            next_poll += interval
            now = time.monotonic()
            if next_poll < now:
                next_poll = now + interval
            time.sleep(max(0.0, next_poll - now))
    except KeyboardInterrupt:
        pass
    finally:
        collector.shutdown()
        conn.close()


if __name__ == "__main__":
    main()
