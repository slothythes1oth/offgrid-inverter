"""Derived state: grid presence, on-battery under both enum encodings, flow."""

from solarmon import registers as R
from solarmon.derived import flow, grid_present, on_battery
from solarmon.fake_source import FakeSource


def sample_with(**over):
    src = FakeSource()
    for addr, val in over.items():
        src.set(getattr(R, addr), val)
    return R.decode(src.read_cycle(), ts=0)


def test_on_battery_srne_encoding():
    s = sample_with(REG_GRID_V_L1=0, REG_MACHINE_STATE=5)
    assert on_battery(s)


def test_on_battery_shifted_encoding():
    """Live 2026-07-17: this unit reads state 3 while off-grid inverting."""
    s = sample_with(REG_GRID_V_L1=0, REG_MACHINE_STATE=3)
    assert on_battery(s)


def test_on_grid_charging_is_not_outage():
    """Live 2026-07-17: on grid, charging, state 2, legs ~120 V."""
    s = sample_with(REG_GRID_V_L1=1195, REG_MACHINE_STATE=2, REG_BATT_A=0x10000 - 147)
    assert grid_present(s)
    assert not on_battery(s)
    assert flow(s) == "grid_to_battery"  # -14.7 A * 54.1-ish V is way over noise


def test_flow_on_battery_and_idle():
    s = sample_with(REG_GRID_V_L1=0, REG_MACHINE_STATE=5)
    assert flow(s) == "battery_to_house"
    idle = sample_with(REG_GRID_V_L1=1200, REG_MACHINE_STATE=4, REG_BATT_A=0)
    assert flow(idle) == "grid_to_house"
