"""SQLite layer: connection setup, versioned migrations, single-writer discipline.

Only the collector process ever opens this database for writing. The future
web app opens it read-only (mode=ro). WAL mode makes that concurrent read
safe without blocking the writer.

Migrations are numbered .sql files in solarmon/migrations/ (001_*.sql, 002_*...).
Applied versions are recorded in schema_migrations; startup applies anything new.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_MIGRATION_NAME = re.compile(r"^(\d{3})_.+\.sql$")


def connect(db_path: str | Path, read_only: bool = False) -> sqlite3.Connection:
    """Open the database with the standing pragmas. Creates parent dirs for writers."""
    p = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _available_migrations() -> list[tuple[int, Path]]:
    out = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _MIGRATION_NAME.match(f.name)
        if not m:
            raise ValueError(f"Migration filename not in NNN_name.sql form: {f.name}")
        out.append((int(m.group(1)), f))
    return out


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply any unapplied migrations, in order. Returns the versions applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, applied_ts INTEGER NOT NULL)"
    )
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    ran = []
    for version, path in _available_migrations():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn:  # one transaction per migration: applies fully or not at all
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_ts) VALUES (?, ?)",
                (version, int(time.time())),
            )
        ran.append(version)
    return ran


def open_for_collector(
    db_path: str | Path, config_snapshot: dict | None = None
) -> sqlite3.Connection:
    """The collector's single writer connection: migrate, snapshot settings."""
    conn = connect(db_path, read_only=False)
    migrate(conn)
    if config_snapshot is not None:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('config_snapshot', ?)",
                (json.dumps(config_snapshot, default=str),),
            )
    return conn
