"""Shared fixtures: in-memory-ish DB, config, fake clock, collector factory."""

from pathlib import Path

import pytest

from solarmon.collector import Collector
from solarmon.config import load_config
from solarmon.db import open_for_collector
from solarmon.fake_source import FakeSource

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def cfg():
    return load_config(REPO_ROOT / "config.yaml")


@pytest.fixture
def conn(tmp_path):
    c = open_for_collector(tmp_path / "test.db")
    yield c
    c.close()


class FakeClock:
    """Deterministic clock stepping a fixed interval per poll."""

    def __init__(self, start=1_784_700_000.0, step=0.0):
        self.t = start
        self.step = step

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def make_collector(cfg, conn, clock):
    def _make(source=None, alerts=None):
        col = Collector(cfg, conn, source or FakeSource(), alert_mgr=alerts, now_fn=clock)
        col.startup()
        return col

    return _make


def run_polls(collector, clock, n, interval=5):
    """Drive n poll cycles, advancing the fake clock between them."""
    samples = []
    for _ in range(n):
        clock.advance(interval)
        samples.append(collector.run_cycle())
    return samples
