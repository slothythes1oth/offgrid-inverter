"""Fake register source: same read_cycle() contract as SolarmanSource.

Used by unit tests and the outage/fault simulation (checkpoint d). Defaults
to the PROVEN.md confirmed live snapshot (2026-07-17, off-grid).
No hardware, no network.
"""

from __future__ import annotations

from solarmon import registers as R


def _snapshot_regs() -> dict[int, int]:
    """PROVEN.md live snapshot: SOC 96, 52.8V, ~11A discharge, off-grid,
    load 312+154 W. Grid variant fields set by helpers below."""
    regs = dict.fromkeys(R.REQUIRED_REGS, 0)
    regs.update(
        {
            R.REG_SOC: 96,
            R.REG_BATT_V: 528,  # 52.8 V
            R.REG_BATT_A: 110,  # 11.0 A (positive = discharge, provisional)
            R.REG_PV1_W: 0,
            R.REG_PV2_W: 0,
            R.REG_MACHINE_STATE: 5,  # Inverter powered
            R.REG_GRID_V_L1: 0,
            R.REG_GRID_V_L2: 0,
            R.REG_LOAD_W_L1: 312,
            R.REG_LOAD_W_L2: 154,
            R.REG_LOAD_PCT_L1: 12,
            R.REG_LOAD_PCT_L2: 6,
        }
    )
    return regs


class FakeSource:
    """Mutable register bank with failure injection."""

    def __init__(self, regs: dict[int, int] | None = None):
        self.regs = regs if regs is not None else _snapshot_regs()
        self.fail_next_cycles = 0
        self.cycles_served = 0

    # -- scenario helpers ------------------------------------------------

    def set(self, addr: int, value: int) -> None:
        self.regs[addr] = value

    def set_grid(self, present: bool, volts: float = 242.0) -> None:
        raw = int(volts * 10) if present else 0
        self.regs[R.REG_GRID_V_L1] = raw
        self.regs[R.REG_GRID_V_L2] = raw
        self.regs[R.REG_MACHINE_STATE] = 4 if present else 5

    def set_load(self, l1_w: int, l2_w: int) -> None:
        self.regs[R.REG_LOAD_W_L1] = l1_w
        self.regs[R.REG_LOAD_W_L2] = l2_w

    def set_soc(self, pct: int) -> None:
        self.regs[R.REG_SOC] = pct

    def raise_fault(self, code: int) -> None:
        self.regs[R.FAULT_BIT_REGS[0]] = 1
        self.regs[R.FAULT_CODE_REGS[0]] = code
        self.regs[R.REG_MACHINE_STATE] = 10  # Fault

    def clear_faults(self) -> None:
        for reg in (*R.FAULT_BIT_REGS, *R.FAULT_CODE_REGS):
            self.regs[reg] = 0
        self.regs[R.REG_MACHINE_STATE] = 4 if self.regs[R.REG_GRID_V_L1] >= 800 else 5

    # -- Source contract ---------------------------------------------------

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def read_cycle(self) -> dict[int, int] | None:
        if self.fail_next_cycles > 0:
            self.fail_next_cycles -= 1
            return None
        self.cycles_served += 1
        return dict(self.regs)
