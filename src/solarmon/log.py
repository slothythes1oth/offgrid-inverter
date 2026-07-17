"""Structured logging: one readable line per record, key=value pairs.

Plain stdlib logging (no extra dependency). Console and a file get the same
lines. The poller logs exactly one summary line per poll cycle; events log
at INFO with their key numbers.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


class KeyValueFormatter(logging.Formatter):
    """`2026-07-17T20:15:03 INFO poller poll ok soc=96 load_w=466` style lines."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} "
            f"{record.levelname} {record.name} {record.getMessage()}"
        )
        fields = getattr(record, "fields", None)
        if fields:
            kv = " ".join(f"{k}={v}" for k, v in fields.items())
            base = f"{base} {kv}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(level: str = "INFO", file: str | None = "data/collector.log") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    formatter = KeyValueFormatter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if file:
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)


def kv(logger: logging.Logger, level: int, msg: str, **fields) -> None:
    """Log msg with structured key=value fields."""
    logger.log(level, msg, extra={"fields": fields})
