"""Run the dashboard API: python -m solarapi [--host H --port P --config F].

Separate process from the collector. Reads the same config.yaml (for the DB
path, poll interval, thresholds); never opens the stick.
"""

from __future__ import annotations

import argparse

import uvicorn

from solarapi.app import create_app
from solarmon.log import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="solarmon dashboard API")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (0.0.0.0 = LAN)")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    setup_logging("INFO", file=None)
    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
