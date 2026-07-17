"""Connection manager: PROVEN.md rules — warm-up, retries, single reconnect,
lockout wait, and the read-only guarantee."""

import re
from pathlib import Path

import pytest

from solarmon.config import PollingConfig, StickConfig
from solarmon.connection import SolarmanSource, StickLockoutError
from solarmon.fake_source import _snapshot_regs

STICK = StickConfig(ip="127.0.0.1", serial=1, port=8899, slave_id=1, socket_timeout_s=1)
POLLING = PollingConfig(interval_s=5, read_retries=3, backoff_s=10, lockout_wait_s=240)


class FakeClient:
    """Stands in for PySolarmanV5: serves blocks from a register dict."""

    def __init__(self, regs=None, fail_reads=0):
        self.regs = regs or _snapshot_regs()
        # Blocks may span registers the snapshot doesn't name; default 0
        self.fail_reads = fail_reads  # fail this many read calls, then succeed
        self.reads = []
        self.disconnected = False

    def read_holding_registers(self, addr, qty):
        self.reads.append((addr, qty))
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise OSError("timeout")
        return [self.regs.get(addr + i, 0) for i in range(qty)]

    def disconnect(self):
        self.disconnected = True


def make_source(factory, sleeps=None):
    return SolarmanSource(
        STICK,
        POLLING,
        client_factory=factory,
        sleep_fn=(sleeps.append if sleeps is not None else lambda s: None),
    )


def test_connect_does_warmup_read():
    client = FakeClient()
    src = make_source(lambda cfg: client)
    src.connect()
    assert client.reads[0] == (0x0100, 1)  # throwaway warm-up


def test_read_cycle_returns_full_register_dict():
    client = FakeClient()
    src = make_source(lambda cfg: client)
    regs = src.read_cycle()
    assert regs is not None
    assert regs[0x0100] == 96


def test_per_read_retry_then_success():
    client = FakeClient(fail_reads=2)  # warm-up eats one failure, first read retried once
    src = make_source(lambda cfg: client)
    assert src.read_cycle() is not None


def test_persistent_connection_reused():
    clients = []

    def factory(cfg):
        c = FakeClient()
        clients.append(c)
        return c

    src = make_source(factory)
    for _ in range(5):
        assert src.read_cycle() is not None
    assert len(clients) == 1  # never reconnects per read


def test_backoff_and_single_reconnect_after_failed_cycles():
    clients = []

    def factory(cfg):
        # First client fails everything; the replacement works
        c = FakeClient(fail_reads=10_000 if not clients else 0)
        clients.append(c)
        return c

    sleeps = []
    src = make_source(factory, sleeps)
    assert src.read_cycle() is None  # streak 1: no reconnect yet
    assert len(clients) == 1
    assert src.read_cycle() is None  # streak 2: backoff + ONE reconnect at cycle end
    assert len(clients) == 2
    assert src.read_cycle() is not None  # fresh connection serves the next cycle
    assert POLLING.backoff_s in sleeps  # backed off before reconnecting
    assert clients[0].disconnected  # clean disconnect of the dead client
    assert src.reconnect_count == 1


def test_lockout_waits_once_then_raises():
    attempts = []

    def factory(cfg):
        attempts.append(1)
        raise ConnectionRefusedError("port 8899 refused")

    sleeps = []
    src = make_source(factory, sleeps)
    with pytest.raises(StickLockoutError):
        src.connect()
    assert len(attempts) == 2  # initial + exactly one post-wait retry, never a loop
    assert POLLING.lockout_wait_s in sleeps


def test_no_write_path_exists_in_codebase():
    """SPEC: no write method may exist anywhere. Function code 3 only."""
    src_dir = Path(__file__).parent.parent / "src" / "solarmon"
    forbidden = re.compile(r"write_(holding|multiple|single)|write_register", re.IGNORECASE)
    offenders = [
        p.name for p in src_dir.rglob("*.py") if forbidden.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
