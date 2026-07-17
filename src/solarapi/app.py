"""FastAPI app: read-only REST + SSE + static frontend serving.

Every DB connection here is opened read-only (mode=ro); the collector remains
the single writer. Connections are per-request (SQLite connections are not
thread-safe to share), which is cheap in WAL mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from solarapi import queries
from solarmon.config import Config, load_config
from solarmon.db import connect

log = logging.getLogger("solarapi")

# Where the built frontend lives (Vite build output). Optional: if absent,
# the API still serves; only the SPA routes 404.
FRONTEND_DIR = Path(__file__).parent.parent.parent / "web" / "dist"

_SSE_HEARTBEAT_S = 15


def _ro_conn(cfg: Config) -> sqlite3.Connection:
    return connect(cfg.database.path, read_only=True)


def create_app(config_path: str = "config.yaml") -> FastAPI:
    cfg = load_config(config_path)
    app = FastAPI(title="solarmon dashboard API", version="0.1.0")
    app.state.cfg = cfg

    @app.get("/api/current")
    def current() -> JSONResponse:
        conn = _ro_conn(cfg)
        try:
            return JSONResponse(queries.build_current(conn, cfg))
        finally:
            conn.close()

    @app.get("/api/samples/recent")
    def samples_recent(window_s: int = Query(default=900, ge=1)) -> JSONResponse:
        conn = _ro_conn(cfg)
        try:
            return JSONResponse(queries.recent_samples(conn, window_s))
        finally:
            conn.close()

    @app.get("/api/settings")
    def settings() -> JSONResponse:
        return JSONResponse(queries.settings_payload(cfg))

    @app.get("/api/health")
    def health() -> JSONResponse:
        try:
            conn = _ro_conn(cfg)
            try:
                row = queries.latest_sample(conn)
            finally:
                conn.close()
            import time

            age = None if row is None else round(time.time() - row["ts"], 1)
            return JSONResponse({"ok": True, "db": "reachable", "latest_sample_age_s": age})
        except Exception as e:  # DB missing / locked / corrupt: report, don't crash
            return JSONResponse({"ok": False, "error": str(e)}, status_code=503)

    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(
            _event_stream(cfg),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    _mount_frontend(app)
    return app


async def _event_stream(cfg: Config) -> AsyncIterator[str]:
    """Emit a `state` event when a new sample lands, and at least every poll
    interval so age_s keeps ticking (this is what makes the stale banner fire
    even against a dead collector). Heartbeat comment keeps proxies open."""
    interval = cfg.polling.interval_s
    last_ts = None
    last_emit = 0.0
    yield "retry: 5000\n\n"
    while True:
        import time

        now = time.time()
        conn = _ro_conn(cfg)
        try:
            payload = queries.build_current(conn, cfg, now=now)
        finally:
            conn.close()

        new_sample = payload.get("ts") != last_ts
        if new_sample or (now - last_emit) >= interval:
            yield f"event: state\ndata: {json.dumps(payload)}\n\n"
            last_ts = payload.get("ts")
            last_emit = now
        elif (now - last_emit) >= _SSE_HEARTBEAT_S:
            yield f": hb {int(now)}\n\n"

        await asyncio.sleep(1)


def _mount_frontend(app: FastAPI) -> None:
    if not FRONTEND_DIR.exists():
        log.warning("frontend build not found at %s; serving API only", FRONTEND_DIR)
        return
    # Assets under /assets (hashed, immutable); index.html for SPA routes.
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")  # SPA fallback
