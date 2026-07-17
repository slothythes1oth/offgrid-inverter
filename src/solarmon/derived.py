"""Derived state: grid presence, on-battery, power flow.

Flow is inferred from power balance (PV + grid presence vs load), never from
the battery current sign: PROVEN.md flags that sign as provisional.
"""

from __future__ import annotations

from solarmon.registers import Sample

GRID_PRESENT_MIN_V = 80.0  # anything below this on L1 is "no grid" (legs are ~120 V)
CHARGE_MIN_W = 100.0  # battery power magnitude below this is noise, not charging

# Live observations 2026-07-17: this unit reported state 3 while off-grid
# inverting and state 2 while on grid charging, i.e. the SRNE enum shifted
# by -2 (SRNE says inverter=5, mains=4). Accept both encodings; a wrong
# state list here would make outage detection blind.
INVERTING_STATES = frozenset({3, 5})
MAINS_STATES = frozenset({2, 4})


def grid_present(sample: Sample) -> bool:
    return sample.grid_v_l1 >= GRID_PRESENT_MIN_V


def on_battery(sample: Sample) -> bool:
    """SPEC intent: grid down AND the inverter is powering the load."""
    return not grid_present(sample) and sample.machine_state in INVERTING_STATES


def flow(sample: Sample) -> str:
    """One-word power flow for the UI mini diagram.

    grid_to_battery means the house is on grid AND the battery is charging
    (any meaningful battery power while grid feeds the load must be charge,
    since this backup system never discharges into the grid).
    """
    if on_battery(sample):
        return "battery_to_house"
    if grid_present(sample):
        if abs(sample.batt_w) >= CHARGE_MIN_W:
            return "grid_to_battery"
        return "grid_to_house"
    return "idle"
