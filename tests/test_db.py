"""SQLite layer: migrations, WAL mode, read-only opens."""

import sqlite3

import pytest

from solarmon.db import connect, migrate, open_for_collector

EXPECTED_TABLES = {
    "samples",
    "rollup_1m",
    "events",
    "outages",
    "peaks",
    "meta",
    "schema_migrations",
}


def test_migrate_creates_schema(tmp_path):
    conn = connect(tmp_path / "t.db")
    ran = migrate(conn)
    assert ran == [1]
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_migrate_is_idempotent(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert migrate(conn) == [1]
    assert migrate(conn) == []  # second run applies nothing


def test_wal_mode_enabled(tmp_path):
    conn = connect(tmp_path / "t.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_read_only_connection_cannot_write(tmp_path):
    db = tmp_path / "t.db"
    open_for_collector(db).close()
    ro = connect(db, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO meta (key, value) VALUES ('x', 'y')")


def test_config_snapshot_written(tmp_path):
    conn = open_for_collector(tmp_path / "t.db", config_snapshot={"a": 1})
    row = conn.execute("SELECT value FROM meta WHERE key='config_snapshot'").fetchone()
    assert row is not None and '"a": 1' in row["value"]
