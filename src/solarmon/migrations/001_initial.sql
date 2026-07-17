-- 001: initial schema (SPEC section 3).
-- All timestamps are UTC unix epoch seconds (INTEGER). Local-time concerns
-- (TOU bands, day boundaries) are handled in Python with America/Toronto.

-- One wide row per poll (~5s). Values are stored decoded, in display units
-- (V, A, W, %); decoding from raw registers happens once, in registers.py.
CREATE TABLE samples (
    ts            INTEGER PRIMARY KEY,   -- epoch seconds, UTC
    soc           INTEGER NOT NULL,      -- %
    batt_v        REAL    NOT NULL,      -- V
    batt_a        REAL    NOT NULL,      -- A, signed as read (sign provisional per PROVEN.md)
    batt_w        REAL    NOT NULL,      -- W = batt_v * batt_a, carries batt_a's sign
    pv1_w         INTEGER NOT NULL,      -- W
    pv2_w         INTEGER NOT NULL,      -- W
    grid_v_l1     REAL    NOT NULL,      -- V, ~0 = no grid
    grid_v_l2     REAL    NOT NULL,      -- V
    load_w_l1     INTEGER NOT NULL,      -- W
    load_w_l2     INTEGER NOT NULL,      -- W
    load_w_total  INTEGER NOT NULL,      -- W = l1 + l2
    load_pct_l1   INTEGER NOT NULL,      -- %
    load_pct_l2   INTEGER NOT NULL,      -- %
    machine_state INTEGER NOT NULL,      -- enum, 0..10 (PROVEN.md)
    fault_active  INTEGER NOT NULL DEFAULT 0   -- 0/1: any nonzero fault bit this poll
);

-- Per-minute rollup, built continuously by the collector. Kept forever;
-- this is what long history charts read after raw samples are pruned.
CREATE TABLE rollup_1m (
    minute_ts     INTEGER PRIMARY KEY,   -- epoch seconds truncated to the minute, UTC
    load_w_avg    REAL    NOT NULL,
    load_w_min    INTEGER NOT NULL,
    load_w_max    INTEGER NOT NULL,
    batt_w_avg    REAL    NOT NULL,
    batt_w_min    REAL    NOT NULL,
    batt_w_max    REAL    NOT NULL,
    soc_avg       REAL    NOT NULL,
    soc_min       INTEGER NOT NULL,
    soc_max       INTEGER NOT NULL,
    sample_count  INTEGER NOT NULL
);

-- Everything notable that happened, with the triggering poll snapshot in
-- detail (JSON) so the UI can show "what was running when it tripped".
CREATE TABLE events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     INTEGER NOT NULL,
    type   TEXT    NOT NULL,   -- fault_raised | fault_cleared | grid_lost | grid_restored
                               -- | pack_protection | low_soc | collector_start
                               -- | collector_stop | gap_detected
    detail TEXT                -- JSON: fault codes, same-poll snapshot, gap length, ...
);
CREATE INDEX idx_events_ts   ON events (ts);
CREATE INDEX idx_events_type ON events (type, ts);

-- One row per grid outage (after the 15s debounce). ended_ts NULL = ongoing.
CREATE TABLE outages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_ts INTEGER NOT NULL,
    ended_ts   INTEGER,
    duration_s INTEGER,
    soc_start  INTEGER,
    soc_end    INTEGER,
    kwh_used   REAL
);
CREATE INDEX idx_outages_started ON outages (started_ts);

-- Sampled peak load per period, always labeled "sampled peak" in the UI.
-- period: 'day' | 'week' | 'all'; period_key: '2026-07-17' | '2026-W29' | 'all'
CREATE TABLE peaks (
    period     TEXT    NOT NULL,
    period_key TEXT    NOT NULL,
    load_w     INTEGER NOT NULL,
    ts         INTEGER NOT NULL,   -- when the peak was sampled
    PRIMARY KEY (period, period_key)
);

-- Key/value: settings snapshot at startup, schema bookkeeping, markers.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
