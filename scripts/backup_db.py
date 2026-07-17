"""Safe online backup of the solarmon database (works while the collector
runs: SQLite's backup API takes a consistent snapshot through WAL). Keeps the
newest 14 backups in data/backups/.

Run:      .venv/Scripts/python scripts/backup_db.py
Restore:  stop the collector, copy the backup over data/solarmon.db, start.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solarmon.config import load_config  # noqa: E402

KEEP = 14


def main() -> None:
    root = Path(__file__).parent.parent
    cfg = load_config(root / "config.yaml")
    src_path = root / cfg.database.path
    dest_dir = src_path.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"solarmon-{time.strftime('%Y%m%d-%H%M%S')}.db"

    # Read-only source connection: single-writer discipline holds.
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    out = sqlite3.connect(dest)
    with out:
        src.backup(out)
    out.close()
    src.close()
    print(f"backup written: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")

    backups = sorted(dest_dir.glob("solarmon-*.db"))
    for old in backups[:-KEEP]:
        old.unlink()
        print(f"pruned old backup: {old.name}")


if __name__ == "__main__":
    main()
