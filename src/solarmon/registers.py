"""Register map and decoding. The ONE place scale factors and signedness live.

Map source: PROVEN.md (verified against the live inverter 2026-07-17).
Everything raw stays in this module; everything outside it works in display
units (V, A, W, %).
"""

from __future__ import annotations

from dataclasses import dataclass

# Block groups, read separately: spanning the unmapped gaps between them
# fails wholesale with IllegalDataAddress (PROVEN.md).
#   0x0100 x18: battery + PV        0x0200 x8: fault bits + codes
#   0x0210 x16: state, grid L1, load L1        0x022A x13: grid L2, load L2
BLOCKS: list[tuple[int, int]] = [(0x0100, 18), (0x0200, 8), (0x0210, 16), (0x022A, 13)]

REG_SOC = 0x0100
REG_BATT_V = 0x0101
REG_BATT_A = 0x0102
REG_PV1_V = 0x0107
REG_PV1_A = 0x0108
REG_PV1_W = 0x0109
REG_PV2_W = 0x0111
FAULT_BIT_REGS = (0x0200, 0x0201, 0x0202, 0x0203)
FAULT_CODE_REGS = (0x0204, 0x0205, 0x0206, 0x0207)
REG_MACHINE_STATE = 0x0210
REG_GRID_V_L1 = 0x0213
REG_LOAD_W_L1 = 0x021B
REG_LOAD_PCT_L1 = 0x021F
REG_GRID_V_L2 = 0x022A
REG_LOAD_W_L2 = 0x0232
REG_LOAD_PCT_L2 = 0x0236

# Every register a valid sample requires. A cycle missing any of these fails
# whole: we never write a half-decoded sample.
REQUIRED_REGS: tuple[int, ...] = (
    REG_SOC,
    REG_BATT_V,
    REG_BATT_A,
    REG_PV1_W,
    REG_PV2_W,
    *FAULT_BIT_REGS,
    *FAULT_CODE_REGS,
    REG_MACHINE_STATE,
    REG_GRID_V_L1,
    REG_LOAD_W_L1,
    REG_LOAD_PCT_L1,
    REG_GRID_V_L2,
    REG_LOAD_W_L2,
    REG_LOAD_PCT_L2,
)

# SRNE doc names. Live observation 2026-07-17 (see PROVEN.md): this unit
# appears to report the enum shifted -2, so 2 and 3 carry dual labels.
MACHINE_STATES = {
    0: "Power-up delay",
    1: "Waiting",
    2: "Initialization (Mains powered on this unit)",
    3: "Soft start (Inverter powered on this unit)",
    4: "Mains powered",
    5: "Inverter powered",
    6: "Inverter to Mains",
    7: "Mains to Inverter",
    8: "Battery activate",
    9: "Shutdown by user",
    10: "Fault",
}

# Plain-language names for fault codes we know. Fault 13 per SPEC section 4.
FAULT_NAMES = {13: "bypass overload"}


def fault_name(code: int) -> str:
    return FAULT_NAMES.get(code, f"fault {code}")


def s16(v: int) -> int:
    """Two's-complement 16-bit to signed int."""
    return v - 0x10000 if v >= 0x8000 else v


@dataclass(frozen=True)
class Sample:
    """One decoded poll, display units. ts is UTC epoch seconds."""

    ts: int
    soc: int  # %
    batt_v: float  # V
    batt_a: float  # A, signed as read (positive = discharge, provisional)
    batt_w: float  # W = batt_v * batt_a, carries batt_a's sign
    pv1_w: int
    pv2_w: int
    grid_v_l1: float
    grid_v_l2: float
    load_w_l1: int
    load_w_l2: int
    load_w_total: int
    load_pct_l1: int
    load_pct_l2: int
    machine_state: int
    fault_active: bool
    fault_codes: tuple[int, ...]  # active codes, not stored in samples table

    @property
    def machine_state_name(self) -> str:
        return MACHINE_STATES.get(self.machine_state, f"unknown ({self.machine_state})")

    @property
    def pv_w_total(self) -> int:
        return self.pv1_w + self.pv2_w

    def snapshot(self) -> dict:
        """Compact dict for event `detail` JSON: what was happening this poll."""
        return {
            "soc": self.soc,
            "batt_v": self.batt_v,
            "batt_w": self.batt_w,
            "pv_w_total": self.pv_w_total,
            "grid_v_l1": self.grid_v_l1,
            "grid_v_l2": self.grid_v_l2,
            "load_w_total": self.load_w_total,
            "load_pct_l1": self.load_pct_l1,
            "load_pct_l2": self.load_pct_l2,
            "machine_state": self.machine_state,
            "machine_state_name": self.machine_state_name,
            "fault_codes": list(self.fault_codes),
        }


class IncompleteReadError(ValueError):
    """A cycle came back missing required registers."""


def decode(regs: dict[int, int], ts: int) -> Sample:
    """Decode a raw register dict into a Sample. Raises IncompleteReadError
    if any required register is missing: half a sample is worse than none."""
    missing = [r for r in REQUIRED_REGS if r not in regs]
    if missing:
        raise IncompleteReadError("missing registers: " + ", ".join(f"0x{r:04x}" for r in missing))

    batt_v = regs[REG_BATT_V] * 0.1
    batt_a = s16(regs[REG_BATT_A]) * 0.1
    fault_bits = [regs[r] for r in FAULT_BIT_REGS]
    fault_codes = tuple(regs[r] for r in FAULT_CODE_REGS if regs[r] != 0)
    return Sample(
        ts=ts,
        soc=regs[REG_SOC],
        batt_v=round(batt_v, 1),
        batt_a=round(batt_a, 1),
        batt_w=round(batt_v * batt_a, 1),
        pv1_w=regs[REG_PV1_W],
        pv2_w=regs[REG_PV2_W],
        grid_v_l1=round(regs[REG_GRID_V_L1] * 0.1, 1),
        grid_v_l2=round(regs[REG_GRID_V_L2] * 0.1, 1),
        load_w_l1=regs[REG_LOAD_W_L1],
        load_w_l2=regs[REG_LOAD_W_L2],
        load_w_total=regs[REG_LOAD_W_L1] + regs[REG_LOAD_W_L2],
        load_pct_l1=regs[REG_LOAD_PCT_L1],
        load_pct_l2=regs[REG_LOAD_PCT_L2],
        machine_state=regs[REG_MACHINE_STATE],
        fault_active=any(fault_bits) or bool(fault_codes),
        fault_codes=fault_codes,
    )
