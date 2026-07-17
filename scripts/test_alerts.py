"""Alert drill (phase 3 checkpoint e): send one test message of EACH alert
type through the real AlertManager, then run the dedupe drill — a simulated
ongoing outage must produce exactly ONE on-battery alert and ONE restore.

With alerts.ntfy_topic set in config.yaml (or --topic), messages really send;
otherwise everything logs as [dry-run]. Never touches the stick or the DB.

Run: .venv/Scripts/python scripts/test_alerts.py [--topic solarmon-xxxxxxxx]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solarmon.alerts import PRIORITY_CRITICAL, PRIORITY_DEFAULT, AlertManager  # noqa: E402
from solarmon.config import load_config  # noqa: E402
from solarmon.log import setup_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="solarmon alert drill")
    parser.add_argument("--topic", help="override alerts.ntfy_topic for this drill")
    args = parser.parse_args()

    setup_logging("INFO", file=None)
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    if args.topic:
        cfg.alerts.ntfy_topic = args.topic

    mgr = AlertManager(cfg.alerts)
    mode = "LIVE -> " + cfg.alerts.ntfy_topic if cfg.alerts.enabled else "DRY-RUN (no topic set)"
    print(f"\n=== alert drill: {mode} ===\n")

    print("-- one of each alert type (as the collector would send them) --")
    mgr.alert_once(
        "test_outage",
        "TEST: Grid lost — on battery",
        "SoC 96% · load 466 W. (test message)",
        PRIORITY_CRITICAL,
    )
    mgr.alert_edge(
        "TEST: Grid restored",
        "Outage lasted 42m · SoC 96% -> 81% · 1.9 kWh used. (test message)",
        PRIORITY_DEFAULT,
    )
    mgr.alert_once(
        "test_fault",
        "TEST: Inverter fault: Fault 13 - bypass overload",
        "Load at trip 5.9 kW (L1 4.8 kW / L2 1.1 kW) · SoC 62%. (test message)",
        PRIORITY_CRITICAL,
    )
    mgr.alert_edge("TEST: Inverter fault cleared", "All fault codes clear. (test message)")
    mgr.alert_once(
        "test_low_soc",
        "TEST: Battery low during outage: 39%",
        "Below 40% threshold. (test message)",
        PRIORITY_CRITICAL,
    )
    mgr.alert_once(
        "test_pack",
        "TEST: Battery pack protection",
        "Pack count dropped below 3. (test message)",
        PRIORITY_CRITICAL,
    )

    print("\n-- dedupe drill: an ongoing outage alerts exactly once --")
    drill = AlertManager(cfg.alerts)
    on_batt = "TEST-DEDUPE: Grid lost — on battery"
    sends = [
        drill.alert_once("outage", on_batt, "poll 1", PRIORITY_CRITICAL),
        drill.alert_once("outage", "SHOULD NOT SEND", "poll 2 (ongoing)", PRIORITY_CRITICAL),
        drill.alert_once("outage", "SHOULD NOT SEND", "poll 3 (ongoing)", PRIORITY_CRITICAL),
    ]
    drill.mark_active("outage")  # collector restart mid-outage: still no re-alert
    sends.append(drill.alert_once("outage", "SHOULD NOT SEND", "after restart", PRIORITY_CRITICAL))
    drill.clear("outage")
    drill.alert_edge("TEST-DEDUPE: Grid restored", "outage over", PRIORITY_DEFAULT)

    assert sends == [True, False, False, False], f"dedupe broken: {sends}"
    print("\ndedupe OK: 1 on-battery alert + 1 restore for a whole outage")
    if cfg.alerts.enabled:
        print(f"total live messages sent: {mgr.sent_count + drill.sent_count} (expect 8)")
        print("check your phone: 6 typed tests + 1 dedupe pair (2 messages)")
    else:
        print("set alerts.ntfy_topic in config.yaml (or pass --topic) to send for real")


if __name__ == "__main__":
    main()
