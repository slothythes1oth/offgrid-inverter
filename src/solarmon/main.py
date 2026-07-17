"""Collector entrypoint.

Checkpoint (a) state: loads config, sets up logging, opens the database and
applies migrations, then reports readiness. The poll loop arrives in
checkpoint (b).
"""

from __future__ import annotations

import argparse
import logging

from solarmon.config import load_config
from solarmon.db import open_for_collector
from solarmon.log import kv, setup_logging

log = logging.getLogger("main")


def main() -> None:
    parser = argparse.ArgumentParser(description="solarmon collector")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging.level, cfg.logging.file)

    conn = open_for_collector(cfg.database.path, config_snapshot=cfg.model_dump())
    n_tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    kv(
        log,
        logging.INFO,
        "scaffold ready (poller arrives in checkpoint b)",
        db=cfg.database.path,
        tables=n_tables,
        stick=f"{cfg.stick.ip}:{cfg.stick.port}",
        alerts="on" if cfg.alerts.enabled else "off",
    )
    conn.close()


if __name__ == "__main__":
    main()
