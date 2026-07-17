"""Decoding: scale factors, signs, fault extraction, PROVEN.md snapshot."""

import pytest

from solarmon import registers as R
from solarmon.fake_source import FakeSource


def test_decode_proven_snapshot():
    """FakeSource defaults mirror the PROVEN.md confirmed live snapshot."""
    s = R.decode(FakeSource().read_cycle(), ts=1_784_700_000)
    assert s.soc == 96
    assert s.batt_v == 52.8
    assert s.batt_a == 11.0
    assert s.batt_w == pytest.approx(580.8)
    assert s.load_w_total == 466
    assert s.grid_v_l1 == 0.0
    assert s.machine_state == 5
    assert s.machine_state_name == "Inverter powered"
    assert not s.fault_active


def test_signed_battery_current():
    src = FakeSource()
    src.set(R.REG_BATT_A, 0x10000 - 110)  # -11.0 A raw two's complement
    s = R.decode(src.read_cycle(), ts=0)
    assert s.batt_a == -11.0
    assert s.batt_w == pytest.approx(-580.8)


def test_fault_decode():
    src = FakeSource()
    src.raise_fault(13)
    s = R.decode(src.read_cycle(), ts=0)
    assert s.fault_active
    assert s.fault_codes == (13,)
    assert R.fault_name(13) == "bypass overload"
    assert s.machine_state_name == "Fault"


def test_missing_register_refused():
    regs = FakeSource().read_cycle()
    del regs[R.REG_SOC]
    with pytest.raises(R.IncompleteReadError):
        R.decode(regs, ts=0)


def test_blocks_cover_required_registers():
    covered = set()
    for base, qty in R.BLOCKS:
        covered.update(range(base, base + qty))
    assert set(R.REQUIRED_REGS) <= covered
