"""Connection manager for the Solarman stick, implementing PROVEN.md exactly.

Rules encoded here:
1. ONE persistent connection, reused for every poll. Never reconnect per read.
2. Throwaway warm-up read after every connect (first packet is often dropped).
3. Per-read retries (config, default 3) with a short pause.
4. On a failed cycle streak: back off seconds, then ONE clean reconnect.
5. Never a reconnect storm. If connecting itself fails (stick unplugged or
   port 8899 locked out), wait out lockout_wait_s (~4 min) ONCE and try one
   more time; if that also fails, raise StickLockoutError so the caller can
   report loudly instead of hammering.

Strictly read-only: Modbus function code 3 (read_holding_registers) is the
only method this module ever calls. No write path exists.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from pysolarmanv5 import PySolarmanV5

from solarmon.config import PollingConfig, StickConfig
from solarmon.registers import BLOCKS, REQUIRED_REGS

log = logging.getLogger("connection")

_READ_RETRY_PAUSE_S = 0.4
_WARMUP_REG = 0x0100
_FAILURES_BEFORE_RECONNECT = 2


class StickLockoutError(RuntimeError):
    """Connecting failed even after waiting out the lockout window once."""


def _default_client_factory(stick: StickConfig) -> PySolarmanV5:
    return PySolarmanV5(
        stick.ip,
        stick.serial,
        port=stick.port,
        mb_slave_id=stick.slave_id,
        socket_timeout=stick.socket_timeout_s,
    )


class SolarmanSource:
    """Owns the single stick connection. read_cycle() returns a full raw
    register dict, or None for a failed cycle (caller marks data stale)."""

    def __init__(
        self,
        stick: StickConfig,
        polling: PollingConfig,
        client_factory: Callable[[StickConfig], object] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._stick = stick
        self._polling = polling
        self._factory = client_factory or _default_client_factory
        self._sleep = sleep_fn
        self._client: object | None = None
        self._failed_cycles = 0
        self.reconnect_count = 0  # diagnostics

    # -- connection lifecycle ------------------------------------------------

    def connect(self) -> None:
        """Connect with warm-up. On failure: wait out the lockout once, retry
        once, then raise StickLockoutError. Never loops."""
        try:
            self._client = self._factory(self._stick)
        except Exception as first:
            log.warning(
                "connect failed (%s); waiting out %ss once per PROVEN.md",
                first,
                self._polling.lockout_wait_s,
            )
            self._sleep(self._polling.lockout_wait_s)
            try:
                self._client = self._factory(self._stick)
            except Exception as second:
                raise StickLockoutError(
                    f"stick not answering on {self._stick.ip}:{self._stick.port} "
                    f"even after waiting {self._polling.lockout_wait_s}s: {second}"
                ) from second
        # Warm-up: the first read right after connect is often dropped.
        try:
            self._client.read_holding_registers(_WARMUP_REG, 1)
        except Exception:
            pass  # expected sometimes; real reads have their own retries
        log.info("connected to stick at %s:%s", self._stick.ip, self._stick.port)

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _reconnect_once(self) -> None:
        """The single clean reconnect after a backoff. Never called in a loop."""
        log.warning(
            "cycle failures reached %d; backing off %ss then reconnecting once",
            self._failed_cycles,
            self._polling.backoff_s,
        )
        self.disconnect()
        self._sleep(self._polling.backoff_s)
        self.connect()
        self.reconnect_count += 1
        self._failed_cycles = 0

    # -- reading -------------------------------------------------------------

    def _read_block(self, addr: int, qty: int) -> list[int] | None:
        for attempt in range(1, self._polling.read_retries + 1):
            try:
                return self._client.read_holding_registers(addr, qty)
            except Exception as e:
                if attempt == self._polling.read_retries:
                    log.debug("block 0x%04x x%d failed after %d tries: %s", addr, qty, attempt, e)
                else:
                    self._sleep(_READ_RETRY_PAUSE_S)
        return None

    def read_cycle(self) -> dict[int, int] | None:
        """One poll: read all block groups. Full success -> raw register dict.
        Any required register unread -> None (no partial samples)."""
        if self._client is None:
            self.connect()

        regs: dict[int, int] = {}
        failed_blocks: list[tuple[int, int]] = []
        for base, qty in BLOCKS:
            vals = self._read_block(base, qty)
            if vals is not None:
                for i, v in enumerate(vals):
                    regs[base + i] = v
            else:
                failed_blocks.append((base, qty))

        # Fallback per read_live.py: if a whole block fails (one illegal
        # address kills the request), try just the required registers inside
        # it, one at a time.
        for base, qty in failed_blocks:
            for reg in REQUIRED_REGS:
                if base <= reg < base + qty and reg not in regs:
                    one = self._read_block(reg, 1)
                    if one is not None:
                        regs[reg] = one[0]

        if all(r in regs for r in REQUIRED_REGS):
            self._failed_cycles = 0
            return regs

        self._failed_cycles += 1
        log.warning("poll cycle failed (streak=%d)", self._failed_cycles)
        if self._failed_cycles >= _FAILURES_BEFORE_RECONNECT:
            self._reconnect_once()  # may raise StickLockoutError; caller handles
        return None
