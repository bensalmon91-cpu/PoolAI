"""
BAYROL PoolManager / Analyt - Modbus TCP (Read-only)

Implements:
- FC=04 Read Input Registers for:
  - Parameter values at 3001.. (setpoints, alarm thresholds, etc.)
  - Measurement readings at 4001.. (pH, free chlorine, redox, temps, etc.)
- FC=02 Read Discrete Inputs ("Input Status") for:
  - Alarm statuses at 2001.. (collective alarm, pH alarms, dosing alarms, etc.)

IMPORTANT (per spec):
- Device/Unit ID not relevant; use 1
- Reading multiple registers/inputs is NOT supported -> always read count=1

TODO: VERIFICATION NEEDED
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This implementation has been tested against a SIMULATOR only, not a real
BAYROL PoolManager device. Before production use, verify against:
1. Official BAYROL Modbus TCP specification PDF
2. Real BAYROL PoolManager hardware

Items to verify:
- Register addresses (3001-3084 params, 4001-4077 measurements, 2001-2039 alarms)
- Decimal scaling factors (e.g., pH decimals=2 means divide by 100)
- Function codes (FC02 for alarms, FC04 for registers)
- Single-read restriction (count=1 only)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Dict, Optional, Union

# pip install pymodbus
from pymodbus.client import ModbusTcpClient


def _get_unit_keyword() -> str:
    """Detect the correct keyword for unit/slave ID based on pymodbus version."""
    try:
        params = inspect.signature(ModbusTcpClient.read_input_registers).parameters
        if "device_id" in params:
            return "device_id"
        if "slave" in params:
            return "slave"
    except Exception:
        pass
    return "unit"


_UNIT_KW = _get_unit_keyword()


# ----------------------------
# Register definitions (from PDF)
# ----------------------------

@dataclass(frozen=True)
class RegisterDef:
    address: int
    name: str
    unit: str = ""
    decimals: int = 0
    min_raw: Optional[int] = None
    max_raw: Optional[int] = None

    def scale(self, raw: int) -> float:
        return raw / (10 ** self.decimals)


# Parameters (FC04) - page 3 table
PARAM_REGS: Dict[str, RegisterDef] = {
    "setpoint_ph": RegisterDef(3001, "Setpoint pH", "pH", 2, 600, 850),
    "low_alarm_ph": RegisterDef(3002, "Lower Alarm threshold pH", "pH", 2, 0, 850),
    "high_alarm_ph": RegisterDef(3003, "Upper Alarm threshold pH", "pH", 2, 600, 999),

    "setpoint_freecl_br": RegisterDef(3017, "Setpoint Chlorine/Bromine", "mg/l", 2, 0, 999),
    "low_alarm_freecl_br": RegisterDef(3018, "Lower Alarm threshold Chlorine/Bromine", "mg/l", 2, 0, 999),
    "high_alarm_freecl_br": RegisterDef(3019, "Upper Alarm threshold Chlorine/Bromine", "mg/l", 2, 0, 999),

    # Redox section appears duplicated in the PDF table (3049/3050, 3051/3052, 3053/3054).
    # We keep the addresses as listed.
    "setpoint_redox_1": RegisterDef(3049, "Setpoint Redox (mV)", "mV", 0, 0, 999),
    "setpoint_redox_2": RegisterDef(3050, "Setpoint Redox (mV)", "mV", 0, 0, 999),
    "low_alarm_redox_1": RegisterDef(3051, "Lower Alarm threshold Redox (mV)", "mV", 0, 0, 999),
    "low_alarm_redox_2": RegisterDef(3052, "Lower Alarm threshold Redox (mV)", "mV", 0, 0, 999),
    "high_alarm_redox_1": RegisterDef(3053, "Upper Alarm threshold Redox (mV)", "mV", 0, 0, 999),
    "high_alarm_redox_2": RegisterDef(3054, "Upper Alarm threshold Redox (mV)", "mV", 0, 0, 999),

    "low_alarm_t1": RegisterDef(3069, "Lower Alarm Threshold T1", "°C", 1, 0, 500),
    "high_alarm_t1": RegisterDef(3070, "Upper Alarm Threshold T1", "°C", 1, 0, 500),

    "low_alarm_t2": RegisterDef(3074, "Lower Alarm Threshold T2", "°C", 1, 0, 500),
    "high_alarm_t2": RegisterDef(3075, "Upper Alarm Threshold T2", "°C", 1, 0, 500),

    "low_alarm_t3": RegisterDef(3079, "Lower Alarm Threshold T3", "°C", 1, 0, 500),
    "high_alarm_t3": RegisterDef(3080, "Upper Alarm Threshold T3", "°C", 1, 0, 500),

    "basic_dose_o2": RegisterDef(3084, "Basic dosing amount O2 (BayroSoft)", "l", 1, 0, 999),
}

# Measurements (FC04) - page 4 table
MEAS_REGS: Dict[str, RegisterDef] = {
    "ph": RegisterDef(4001, "pH", "pH", 2, 0, 999),
    "freecl_br": RegisterDef(4008, "Cl (free chlorine) / Br (free bromine)", "mg/l", 2, 0, 999),
    "redox": RegisterDef(4022, "Redox", "mV", 0, 0, 999),

    "t1": RegisterDef(4033, "T1 (temperature 1)", "°C", 1, 100, 500),
    "battery_v": RegisterDef(4047, "Battery", "V", 2, 0, 500),
    "t2": RegisterDef(4069, "T2 (temperature 2)", "°C", 1, 100, 500),
    "t3": RegisterDef(4071, "T3 (temperature 3)", "°C", 1, 100, 500),

    "o2_dosed_amount": RegisterDef(4077, "O2 (dosed amount O2)", "l", 1, 0, 999),
}

# Alarms (FC02) - page 5 table
ALARM_INPUTS: Dict[str, int] = {
    "collective_alarm": 2001,
    "power_on_delay": 2002,
    "no_flow_input_flow": 2003,
    "no_flow_input_in1": 2004,
    "upper_alarm_ph": 2005,
    "lower_alarm_ph": 2006,
    "dosing_alarm_ph": 2009,
    "upper_alarm_chlor_br": 2010,
    "lower_alarm_chlor_br": 2011,
    "level_alarm_chlor": 2012,
    "level_warning_chlor": 2013,
    "dosing_alarm_chlor_br": 2014,
    "upper_alarm_redox": 2019,
    "lower_alarm_redox": 2020,
    "level_alarm_redox": 2021,
    "level_warning_redox": 2022,
    "dosing_alarm_redox": 2023,
    "level_alarm_o2": 2024,
    "level_warning_o2": 2025,
    "upper_alarm_t1": 2028,
    "lower_alarm_t1": 2029,
    "upper_alarm_t2": 2030,
    "lower_alarm_t2": 2031,
    "upper_alarm_t3": 2032,
    "lower_alarm_t3": 2033,
    "battery_alarm": 2034,
    "level_alarm_php": 2035,
    "level_warning_php": 2036,
    "level_alarm_phm": 2037,
    "level_warning_phm": 2038,
    "level_alarm_flockmatic": 2039,
}


# ----------------------------
# Reader
# ----------------------------

class BayrolPoolManagerModbus:
    """
    Read-only Modbus TCP client for BAYROL PoolManager/Analyt.

    Per spec:
    - Unit/Device ID not relevant; default 1
    - Always read count=1 (multi-read not supported)
    """

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout_s: float = 2.0):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.client = ModbusTcpClient(host=host, port=port, timeout=timeout_s)

    def connect(self) -> bool:
        return bool(self.client.connect())

    def close(self) -> None:
        self.client.close()

    # ---- FC04 registers ----

    def read_fc04_raw(self, address: int) -> int:
        """
        Read one input register (FC04) and return the raw integer.
        """
        kw = {_UNIT_KW: self.unit_id}
        rr = self.client.read_input_registers(address=address, count=1, **kw)
        if rr.isError():
            raise IOError(f"FC04 read failed at {address}: {rr}")
        return int(rr.registers[0])

    def read_register(self, reg: RegisterDef) -> float:
        raw = self.read_fc04_raw(reg.address)
        return reg.scale(raw)

    def read_param(self, key: str) -> float:
        if key not in PARAM_REGS:
            raise KeyError(f"Unknown param key '{key}'. Available: {list(PARAM_REGS.keys())}")
        return self.read_register(PARAM_REGS[key])

    def read_measurement(self, key: str) -> float:
        if key not in MEAS_REGS:
            raise KeyError(f"Unknown measurement key '{key}'. Available: {list(MEAS_REGS.keys())}")
        return self.read_register(MEAS_REGS[key])

    # ---- FC02 alarms ----

    def read_alarm(self, key: str) -> bool:
        """
        Read one discrete input (FC02). Returns True if alarm active.
        """
        if key not in ALARM_INPUTS:
            raise KeyError(f"Unknown alarm key '{key}'. Available: {list(ALARM_INPUTS.keys())}")
        address = ALARM_INPUTS[key]
        kw = {_UNIT_KW: self.unit_id}
        rr = self.client.read_discrete_inputs(address=address, count=1, **kw)
        if rr.isError():
            raise IOError(f"FC02 read failed at {address}: {rr}")
        return bool(rr.bits[0])

    def read_many(self, *keys: str) -> Dict[str, Union[float, bool]]:
        """
        Convenience method: read a mix of keys.
        Rules:
          - if key in PARAM_REGS -> FC04 parameter
          - if key in MEAS_REGS  -> FC04 measurement
          - if key in ALARM_INPUTS -> FC02 alarm
        """
        out: Dict[str, Union[float, bool]] = {}
        for k in keys:
            if k in PARAM_REGS:
                out[k] = self.read_param(k)
            elif k in MEAS_REGS:
                out[k] = self.read_measurement(k)
            elif k in ALARM_INPUTS:
                out[k] = self.read_alarm(k)
            else:
                raise KeyError(f"Unknown key '{k}'")
        return out


# ----------------------------
# Example usage
# ----------------------------

if __name__ == "__main__":
    # Example usage - configure host/port as needed
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.100"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 502

    pm = BayrolPoolManagerModbus(host=host, port=port, unit_id=1)

    if not pm.connect():
        raise SystemExit(f"Could not connect to Modbus TCP server at {host}:{port}")

    try:
        # Examples based on the PDF tables:
        ph_now = pm.read_measurement("ph")          # address 4001, decimals=2
        ph_sp  = pm.read_param("setpoint_ph")       # address 3001, decimals=2
        alarm  = pm.read_alarm("collective_alarm")  # address 2001, FC02 boolean

        print(f"pH now: {ph_now:.2f}")
        print(f"pH setpoint: {ph_sp:.2f}")
        print(f"Collective alarm active: {alarm}")

        # Mixed read
        data = pm.read_many("ph", "freecl_br", "redox", "t1", "collective_alarm")
        print(data)

    finally:
        pm.close()
