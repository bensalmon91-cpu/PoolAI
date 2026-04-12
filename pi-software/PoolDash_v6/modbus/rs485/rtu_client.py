# modbus/rs485/rtu_client.py
# Modbus RTU serial client wrapper for RS485 devices
#
# This module provides a wrapper around pymodbus.ModbusSerialClient for
# RS485 communication. It handles connection management, error handling,
# and provides consistent interface with the existing TCP-based logger.

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusException
except ImportError:
    # Fallback for older pymodbus versions
    from pymodbus.client.sync import ModbusSerialClient
    from pymodbus.exceptions import ModbusException


class RS485ConnectionError(Exception):
    """Raised when RS485 serial connection fails."""
    pass


@dataclass
class RS485Health:
    """Tracks connection health metrics for an RS485 device."""
    port: str
    name: str
    total_successes: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_success_ts: Optional[str] = None
    last_failure_ts: Optional[str] = None
    last_failure_reason: str = ""
    current_backoff_seconds: float = 0.0
    next_attempt_after: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.total_successes + self.total_failures
        if total == 0:
            return 0.0
        return self.total_successes / total

    @property
    def is_degraded(self) -> bool:
        """Device is degraded if success rate < 50%."""
        return self.success_rate < 0.5 and (self.total_successes + self.total_failures) >= 5

    @property
    def is_offline(self) -> bool:
        """Device appears offline if 10+ consecutive failures."""
        return self.consecutive_failures >= 10

    def record_success(self, ts: str) -> None:
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success_ts = ts
        self.current_backoff_seconds = 0.0
        self.next_attempt_after = 0.0

    def record_failure(self, ts: str, reason: str) -> None:
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_ts = ts
        self.last_failure_reason = reason
        # Exponential backoff: 2, 4, 8, 16, 32, max 60 seconds
        if self.consecutive_failures > 1:
            self.current_backoff_seconds = min(60.0, 2 ** (self.consecutive_failures - 1))
            self.next_attempt_after = time.time() + self.current_backoff_seconds

    def should_skip_this_cycle(self) -> bool:
        """Check if we should skip due to backoff."""
        if self.next_attempt_after <= 0:
            return False
        return time.time() < self.next_attempt_after

    def status_summary(self) -> str:
        """Human-readable status summary."""
        if self.is_offline:
            return f"OFFLINE (failed {self.consecutive_failures}x, last: {self.last_failure_reason})"
        if self.is_degraded:
            return f"DEGRADED ({self.success_rate*100:.0f}% success rate)"
        if self.consecutive_failures > 0:
            return f"RECOVERING (failed {self.consecutive_failures}x)"
        return "OK"


class RS485Client:
    """
    Wrapper around pymodbus ModbusSerialClient for RS485 RTU communication.

    Provides:
    - Connection management with retry logic
    - Health tracking
    - Consistent interface with TCP logger
    - Register reading with type decoding
    """

    # Default serial settings for common water testing devices
    DEFAULT_BAUDRATE = 9600
    DEFAULT_PARITY = "N"       # None
    DEFAULT_STOPBITS = 1
    DEFAULT_BYTESIZE = 8
    DEFAULT_TIMEOUT = 1.0      # seconds
    DEFAULT_UNIT_ID = 1

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        parity: str = DEFAULT_PARITY,
        stopbits: int = DEFAULT_STOPBITS,
        bytesize: int = DEFAULT_BYTESIZE,
        timeout: float = DEFAULT_TIMEOUT,
        unit_id: int = DEFAULT_UNIT_ID,
        name: str = "RS485 Device",
    ):
        """
        Initialize RS485 client.

        Args:
            port: Serial port path (e.g., "/dev/ttyUSB0" or "COM3")
            baudrate: Baud rate (default: 9600)
            parity: Parity setting - "N", "E", "O" (default: "N")
            stopbits: Stop bits (default: 1)
            bytesize: Data bits (default: 8)
            timeout: Read timeout in seconds (default: 1.0)
            unit_id: Modbus unit/slave ID (default: 1)
            name: Human-readable device name
        """
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.timeout = timeout
        self.unit_id = unit_id
        self.name = name

        self._client: Optional[ModbusSerialClient] = None
        self.health = RS485Health(port=port, name=name)

        self._logger = logging.getLogger(f"rs485.{name}")

    def connect(self) -> bool:
        """
        Establish serial connection to the RS485 device.

        Returns:
            True if connection successful, False otherwise.
        """
        if self._client and self._client.connected:
            return True

        try:
            self._client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
                timeout=self.timeout,
            )

            if self._client.connect():
                self._logger.info("Connected to %s on %s @ %d baud",
                                  self.name, self.port, self.baudrate)
                return True
            else:
                self._logger.warning("Failed to connect to %s on %s",
                                     self.name, self.port)
                return False

        except Exception as e:
            self._logger.error("Connection error for %s: %s", self.name, e)
            return False

    def disconnect(self) -> None:
        """Close the serial connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    @property
    def connected(self) -> bool:
        """Check if currently connected."""
        return self._client is not None and self._client.connected

    def read_holding_registers(
        self,
        address: int,
        count: int,
        unit: Optional[int] = None
    ) -> Optional[List[int]]:
        """
        Read holding registers from the device.

        Args:
            address: Starting register address (0-based)
            count: Number of registers to read
            unit: Modbus unit ID (default: self.unit_id)

        Returns:
            List of register values, or None on error.
        """
        if not self.connected:
            if not self.connect():
                return None

        unit = unit or self.unit_id

        try:
            # Determine correct keyword for unit ID (pymodbus version compatibility)
            try:
                import inspect
                params = inspect.signature(self._client.read_holding_registers).parameters
                if "slave" in params:
                    kw = {"slave": unit}
                elif "device_id" in params:
                    kw = {"device_id": unit}
                else:
                    kw = {"unit": unit}
            except Exception:
                kw = {"unit": unit}

            result = self._client.read_holding_registers(address=address, count=count, **kw)

            if result is None:
                return None
            if hasattr(result, "isError") and result.isError():
                return None

            regs = getattr(result, "registers", None)
            if regs is None:
                return None

            return list(regs)

        except ModbusException as e:
            self._logger.warning("Modbus error reading %s addr=%d: %s",
                                 self.name, address, e)
            return None
        except Exception as e:
            self._logger.error("Error reading %s addr=%d: %s",
                               self.name, address, e)
            return None

    def read_input_registers(
        self,
        address: int,
        count: int,
        unit: Optional[int] = None
    ) -> Optional[List[int]]:
        """
        Read input registers from the device.

        Args:
            address: Starting register address (0-based)
            count: Number of registers to read
            unit: Modbus unit ID (default: self.unit_id)

        Returns:
            List of register values, or None on error.
        """
        if not self.connected:
            if not self.connect():
                return None

        unit = unit or self.unit_id

        try:
            try:
                import inspect
                params = inspect.signature(self._client.read_input_registers).parameters
                if "slave" in params:
                    kw = {"slave": unit}
                elif "device_id" in params:
                    kw = {"device_id": unit}
                else:
                    kw = {"unit": unit}
            except Exception:
                kw = {"unit": unit}

            result = self._client.read_input_registers(address=address, count=count, **kw)

            if result is None:
                return None
            if hasattr(result, "isError") and result.isError():
                return None

            regs = getattr(result, "registers", None)
            if regs is None:
                return None

            return list(regs)

        except ModbusException as e:
            self._logger.warning("Modbus error reading input %s addr=%d: %s",
                                 self.name, address, e)
            return None
        except Exception as e:
            self._logger.error("Error reading input %s addr=%d: %s",
                               self.name, address, e)
            return None

    def __enter__(self) -> "RS485Client":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


# -----------------------------
# Decoding Helpers (shared with TCP logger patterns)
# -----------------------------

def decode_u16(registers: List[int]) -> Optional[float]:
    """Decode a single 16-bit unsigned integer."""
    if not registers:
        return None
    return float(registers[0] & 0xFFFF)


def decode_u32(registers: List[int], word_order: str = "AB") -> Optional[float]:
    """Decode a 32-bit unsigned integer from 2 registers."""
    if len(registers) < 2:
        return None
    if word_order == "BA":
        w0, w1 = registers[1] & 0xFFFF, registers[0] & 0xFFFF
    else:
        w0, w1 = registers[0] & 0xFFFF, registers[1] & 0xFFFF
    v = ((w0 & 0xFFFF) << 16) | (w1 & 0xFFFF)
    return float(v)


def decode_f32(registers: List[int], word_order: str = "AB") -> Optional[float]:
    """Decode a 32-bit float from 2 registers."""
    if len(registers) < 2:
        return None
    if word_order == "BA":
        w0, w1 = registers[1] & 0xFFFF, registers[0] & 0xFFFF
    else:
        w0, w1 = registers[0] & 0xFFFF, registers[1] & 0xFFFF
    b = struct.pack(">HH", w0, w1)
    try:
        import math
        v = struct.unpack(">f", b)[0]
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def decode_str(registers: List[int], reg_count: int, byte_order: str = "AB") -> str:
    """Decode ASCII string from registers."""
    raw = bytearray()
    for r in registers[:reg_count]:
        hi = (r >> 8) & 0xFF
        lo = r & 0xFF
        if byte_order == "BA":
            raw.append(lo)
            raw.append(hi)
        else:
            raw.append(hi)
            raw.append(lo)
    return raw.decode("ascii", errors="ignore").rstrip("\x00").rstrip()


def apply_scale(value: Optional[float], scale: Optional[float]) -> Optional[float]:
    """Apply scaling factor to a value."""
    if value is None:
        return None
    if scale is None:
        return value
    try:
        return value * float(scale)
    except Exception:
        return value
