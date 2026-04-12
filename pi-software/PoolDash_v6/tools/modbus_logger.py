#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoolAIssistant — Modbus TCP Hybrid Logger (READINGS + EVENT CHANGES)

What it does:
1) Continuous readings every SAMPLE_SECONDS:
   - Reads *numeric* points from modbus_points.POINTS (f32/u16/u32)
   - Writes to SQLite table: readings (long format)
     columns: ts, pool, host, system_name, serial_number, point_label, value, raw_type

2) Alarm / status bits logged as events (ON->OFF/ OFF->ON):
   - Reads a configured set of "bitfield" labels (Status_* and *Error* etc.)
   - Bit OFF->ON : inserts into alarm_events (started_ts set, ended_ts NULL)
   - Bit ON->OFF : updates that row (ended_ts set)

DB path:
- Uses env var POOLDB if set
- Else defaults to: /opt/PoolAIssistant/data/pool_readings.sqlite3  (fallback: ./pool_readings.sqlite3)

Important:
- This script is read-only (no Modbus writes)
- modbus_points.py must be importable (in same folder or PYTHONPATH)
"""

from __future__ import annotations

import os
import sys

# Add parent directory to path for modbus_points imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import math
import json
import sqlite3
import struct
import logging
import importlib
import subprocess
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

from pymodbus.client import ModbusTcpClient
import inspect
from pymodbus.exceptions import ModbusException


# -----------------------------
# Connection Health Tracking
# -----------------------------

@dataclass
class ControllerHealth:
    """Tracks connection health metrics for a single controller."""
    host: str
    name: str
    # Rolling window of recent connection attempts (True=success, False=failure)
    recent_attempts: deque = field(default_factory=lambda: deque(maxlen=20))
    total_successes: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_success_ts: Optional[str] = None
    last_failure_ts: Optional[str] = None
    last_failure_reason: str = ""
    last_ping_ok: Optional[bool] = None
    last_ping_ms: Optional[float] = None
    current_backoff_seconds: float = 0.0
    next_attempt_after: float = 0.0  # time.time() value
    alert_sent: bool = False  # Track if failure alert has been sent

    @property
    def success_rate(self) -> float:
        """Recent success rate (0.0 to 1.0)."""
        if not self.recent_attempts:
            return 0.0
        return sum(1 for x in self.recent_attempts if x) / len(self.recent_attempts)

    @property
    def is_degraded(self) -> bool:
        """Controller is degraded if success rate < 50% over recent window."""
        return len(self.recent_attempts) >= 5 and self.success_rate < 0.5

    @property
    def is_offline(self) -> bool:
        """Controller appears offline if 10+ consecutive failures."""
        return self.consecutive_failures >= 10

    def record_success(self, ts: str) -> None:
        self.recent_attempts.append(True)
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success_ts = ts
        self.current_backoff_seconds = 0.0
        self.next_attempt_after = 0.0
        self.alert_sent = False  # Reset alert on successful connection

    def record_failure(self, ts: str, reason: str) -> None:
        self.recent_attempts.append(False)
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_ts = ts
        self.last_failure_reason = reason
        # Exponential backoff: 0, 2, 4, 8, 16, 32, max 60 seconds
        if self.consecutive_failures > 1:
            self.current_backoff_seconds = min(60.0, 2 ** (self.consecutive_failures - 1))
            self.next_attempt_after = time.time() + self.current_backoff_seconds

    def should_skip_this_cycle(self) -> bool:
        """Check if we should skip this controller due to backoff."""
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


# Global health tracker: host -> ControllerHealth
_controller_health: Dict[str, ControllerHealth] = {}


def get_controller_health(host: str, name: str) -> ControllerHealth:
    """Get or create health tracker for a controller."""
    if host not in _controller_health:
        _controller_health[host] = ControllerHealth(host=host, name=name)
    return _controller_health[host]


def log_health_summary() -> None:
    """Log health summary for all controllers."""
    if not _controller_health:
        return
    lines = ["Controller Health Summary:"]
    for host, health in _controller_health.items():
        ping_info = ""
        if health.last_ping_ok is not None:
            ping_info = f", ping={'OK' if health.last_ping_ok else 'FAIL'}"
            if health.last_ping_ms:
                ping_info = f", ping={health.last_ping_ms:.1f}ms"
        lines.append(
            f"  {health.name} ({host}): {health.status_summary()} "
            f"[{health.total_successes}/{health.total_successes + health.total_failures} polls{ping_info}]"
        )
    logging.info("\n".join(lines))


def check_health_alert(health: ControllerHealth) -> None:
    """Check if controller has exceeded failure threshold and log alert."""
    if health.consecutive_failures >= FAILURE_ALERT_THRESHOLD:
        if not health.alert_sent:
            logging.error(
                "[ALERT] Controller %s (%s) failed %d times consecutively! Last error: %s",
                health.name, health.host, health.consecutive_failures, health.last_failure_reason
            )
            health.alert_sent = True


# -----------------------------
# Network Diagnostics
# -----------------------------

def ping_host(host: str, timeout_sec: float = 1.0) -> Tuple[bool, Optional[float]]:
    """
    Ping a host to check network reachability.
    Returns (success, latency_ms).
    """
    try:
        # Use system ping command (works on both Linux and Windows)
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout_sec * 1000)), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout_sec)), host]

        start = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 1
        )
        latency_ms = (time.time() - start) * 1000

        return result.returncode == 0, latency_ms if result.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return False, None
    except Exception:
        return False, None


def check_tcp_port(host: str, port: int, timeout_sec: float = 2.0) -> Tuple[bool, Optional[str]]:
    """
    Check if a TCP port is reachable.
    Returns (success, error_message).
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            return True, None
        else:
            return False, f"connect_ex returned {result}"
    except socket.timeout:
        return False, "connection timed out"
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    except OSError as e:
        return False, f"OS error: {e}"
    except Exception as e:
        return False, str(e)

# -----------------------------
# Protocol Auto-Detection
# -----------------------------

# Signature registers for each protocol type
# Each entry: {"addr": register_address, "count": register_count, "check": validation_function}
PROTOCOL_SIGNATURES = {
    "ezetrol": {
        "addr": 0,
        "count": 10,
        "check": lambda r: r is not None and len(r) >= 10
    },
    "bayrol": {
        "addr": 8001,
        "count": 1,
        "check": lambda r: r is not None and len(r) >= 1
    },
    "dulcopool": {
        "addr": 0,
        "count": 2,
        "check": lambda r: r is not None and len(r) >= 2
    },
    "walchem": {
        "addr": 3000,
        "count": 2,
        "check": lambda r: r is not None and len(r) >= 2
    },
}


def detect_protocol(client: "ModbusTcpClient", unit: int) -> Optional[str]:
    """
    Probe controller to identify protocol by reading signature registers.

    Args:
        client: Connected ModbusTcpClient
        unit: Modbus unit/slave ID

    Returns:
        Protocol name if detected, None if unknown
    """
    for name, sig in PROTOCOL_SIGNATURES.items():
        try:
            kw = {_UNIT_KW: unit}
            result = client.read_holding_registers(address=sig["addr"], count=sig["count"], **kw)
            if result is None or (hasattr(result, "isError") and result.isError()):
                continue
            regs = getattr(result, "registers", None)
            if sig["check"](regs):
                logging.debug("[PROTOCOL] Detected protocol: %s (addr=%d responded)", name, sig["addr"])
                return name
        except Exception:
            continue
    return None


# BAYROL profile detection flags (set by _load_points)
IS_BAYROL_PROFILE = False
BAYROL_MODULE = None


def _load_points() -> tuple[list, dict]:
    global IS_BAYROL_PROFILE, BAYROL_MODULE

    profile = (os.getenv("MODBUS_PROFILE") or "").strip().lower()
    settings_path = os.getenv("POOLDASH_SETTINGS_PATH", "").strip()
    settings = {}
    if settings_path and os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            if isinstance(settings, dict):
                profile = (settings.get("modbus_profile") or profile).strip().lower()
        except Exception:
            pass

    if profile not in {"bayrol", "dulcopool", "ezetrol", "walchem"}:
        profile = "ezetrol"

    module_name = {
        "bayrol": "modbus.bayrol_modbus_points",
        "dulcopool": "modbus.dulcopool_modbus_points",
        "ezetrol": "modbus.ezetrol_modbus_points",
        "walchem": "modbus.walchem_modbus_points",
    }[profile]

    try:
        module = importlib.import_module(module_name)

        # BAYROL uses a different architecture (reader class + dictionaries)
        # instead of POINTS list - handle specially
        if profile == "bayrol":
            IS_BAYROL_PROFILE = True
            BAYROL_MODULE = module
            # Return empty POINTS - BAYROL main loop uses the reader class directly
            return [], {}

        points = getattr(module, "POINTS", [])
        if not points:
            raise ValueError(f"No POINTS defined in {module_name}")
        if profile == "ezetrol":
            # Ezetrol uses word-swapped ordering for 32-bit values (BA)
            # and byte-swapped ordering for strings (BA per 16-bit word).
            for p in points:
                if p.get("type") in ("f32", "u32") and "word_order" not in p:
                    p["word_order"] = "BA"
                if p.get("type") == "str" and "byte_order" not in p:
                    p["byte_order"] = "BA"
        aliases = _build_aliases(profile, settings if isinstance(settings, dict) else {})
        return points, aliases
    except Exception as e:
        print(f"FATAL: Cannot load Modbus points for profile '{profile}': {e}")
        raise


def _build_aliases(profile: str, settings: dict) -> dict:
    if profile == "dulcopool":
        mapping = settings.get("dulcopool_channel_map") or {}
        metric_map = {
            "ph": "pH",
            "chlorine": "Chlorine",
            "orp": "ORP",
            "temp": "Temp",
        }
        aliases = {}
        for key, label in metric_map.items():
            ch = (mapping.get(key) or "").strip().upper()
            if not ch or not ch.startswith("E"):
                continue
            idx = ch[1:]
            if not idx.isdigit():
                continue
            prefix = f"param_E{idx}_"
            aliases[f"{prefix}measure_value"] = f"{label}_MeasuredValue"
            aliases[f"{prefix}control_w"] = f"{label}_Setpoint"
            aliases[f"{prefix}alarm_high"] = f"{label}_AlarmHigh"
            aliases[f"{prefix}alarm_low"] = f"{label}_AlarmLow"
        return aliases

    if profile == "ezetrol":
        channel_map = settings.get("ezetrol_channel_map") or {}
        if isinstance(channel_map, dict) and channel_map:
            physical = {
                "ch1": "Chlorine",
                "ch2": "pH",
                "ch3": "ORP",
                "ch4": "Ch4",
            }
            aliases = {}
            for ch_key, src_prefix in physical.items():
                dst_prefix = (channel_map.get(ch_key) or "").strip()
                if not dst_prefix or dst_prefix == src_prefix:
                    continue
                for suffix in ["MeasuredValue", "Unit", "LowerRange", "UpperRange", "Setpoint", "Yout"]:
                    aliases[f"{src_prefix}_{suffix}"] = f"{dst_prefix}_{suffix}"
            return aliases

        layout = (settings.get("ezetrol_layout") or "ABCD").strip().upper()
        if layout == "ABCD":
            return {}
        physical = {
            "A": "Chlorine",
            "B": "pH",
            "C": "ORP",
            "D": "Ch4",
        }
        standard = ["Chlorine", "pH", "ORP", "Ch4"]
        aliases = {}
        for idx, letter in enumerate(layout):
            if letter not in physical:
                continue
            src_prefix = physical[letter]
            dst_prefix = standard[idx]
            if src_prefix == dst_prefix:
                continue
            for suffix in ["MeasuredValue", "Unit", "LowerRange", "UpperRange", "Setpoint", "Yout"]:
                aliases[f"{src_prefix}_{suffix}"] = f"{dst_prefix}_{suffix}"
        return aliases

    return {}


POINTS, LABEL_ALIASES = _load_points()


# -----------------------------
# Settings (edit as needed)
# -----------------------------

SAMPLE_SECONDS = float(os.getenv("SAMPLE_SECONDS", "5"))

# Connection resilience settings (can be overridden via env vars)
MODBUS_TIMEOUT = float(os.getenv("MODBUS_TIMEOUT", "5"))  # seconds (was 3)
MODBUS_RETRIES = int(os.getenv("MODBUS_RETRIES", "3"))    # retry attempts (was 1)
MODBUS_RETRY_DELAY = float(os.getenv("MODBUS_RETRY_DELAY", "0.5"))  # delay between retries

# Network diagnostics settings
PING_CHECK_ENABLED = os.getenv("PING_CHECK_ENABLED", "1").strip() in ("1", "true", "yes")
PING_TIMEOUT = float(os.getenv("PING_TIMEOUT", "1.0"))  # seconds
TCP_PRECHECK_ENABLED = os.getenv("TCP_PRECHECK_ENABLED", "0").strip() in ("1", "true", "yes")

# Health monitoring settings
HEALTH_LOG_INTERVAL = int(os.getenv("HEALTH_LOG_INTERVAL", "60"))  # log health summary every N polls
BACKOFF_ENABLED = os.getenv("BACKOFF_ENABLED", "1").strip() in ("1", "true", "yes")
FAILURE_ALERT_THRESHOLD = int(os.getenv("FAILURE_ALERT_THRESHOLD", "5"))  # alert after N consecutive failures

# Track poll count for periodic health logging
_poll_count = 0

# -----------------------------
# Data Validation
# -----------------------------

VALID_RANGES = {
    "pH": (0.0, 14.0),
    "Temp": (-10.0, 60.0),
    "ORP": (-500.0, 1200.0),
    "Chlorine": (0.0, 20.0),
}


def validate_reading(label: str, value: float) -> bool:
    """
    Validate a reading against known valid ranges.
    Returns True if value is valid, False if out of range.
    """
    if value is None:
        return True  # None values are handled elsewhere
    for key, (vmin, vmax) in VALID_RANGES.items():
        if key in label:
            if value < vmin or value > vmax:
                logging.warning(f"[VALIDATION] {label}={value} out of range [{vmin}, {vmax}]")
                return False
    return True


# -----------------------------
# Systemd Watchdog Support
# -----------------------------

def notify_watchdog() -> None:
    """Notify systemd watchdog that the service is still alive."""
    try:
        import sdnotify
        sdnotify.SystemdNotifier().notify("WATCHDOG=1")
    except ImportError:
        # sdnotify not installed - watchdog disabled
        pass
    except Exception:
        # Silently ignore errors (e.g., not running under systemd)
        pass


def notify_ready() -> None:
    """Notify systemd that the service is ready."""
    try:
        import sdnotify
        sdnotify.SystemdNotifier().notify("READY=1")
    except ImportError:
        pass
    except Exception:
        pass


# -----------------------------
# Graceful Degradation Cache
# -----------------------------

# Cache of last good values: {(controller_host, label): (value, timestamp)}
LAST_GOOD_CACHE: Dict[Tuple[str, str], Tuple[float, datetime]] = {}

# Maximum age for cached values (seconds) - don't use stale data older than this
CACHE_MAX_AGE_SECONDS = 300  # 5 minutes


def cache_value(host: str, label: str, value: float) -> None:
    """Cache a good reading value for potential use during connection failures."""
    if value is not None:
        LAST_GOOD_CACHE[(host, label)] = (value, datetime.now(timezone.utc))


def get_cached(host: str, label: str) -> Optional[Tuple[float, datetime]]:
    """
    Get cached value if available and not too old.
    Returns (value, timestamp) or None if not available/expired.
    """
    cached = LAST_GOOD_CACHE.get((host, label))
    if cached is None:
        return None

    value, ts = cached
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age > CACHE_MAX_AGE_SECONDS:
        return None  # Too old, don't use

    return cached


def get_cache_summary(host: str) -> Dict[str, float]:
    """Get summary of cached values for a host (for logging/debugging)."""
    result = {}
    now = datetime.now(timezone.utc)
    for (h, label), (value, ts) in LAST_GOOD_CACHE.items():
        if h == host:
            age = (now - ts).total_seconds()
            if age <= CACHE_MAX_AGE_SECONDS:
                result[label] = value
    return result

# Tiered logging intervals for different point types
# Points matching these patterns are logged less frequently to save storage
SLOW_LOG_PATTERNS = {
    # Pattern: interval in seconds
    "_Setpoint": 300,      # Setpoints: every 5 minutes
    "_Yout": 60,           # Control output: every 1 minute
    "_LowerRange": 1800,   # Ranges: every 30 minutes
    "_UpperRange": 1800,
    "Lim1_": 1800,         # Limit parameters: every 30 minutes
    "Lim2_": 1800,
    "Lim3_": 1800,
    "Lim4_": 1800,
    "Lim5_": 1800,
    "Ctrl1_": 1800,        # Control parameters: every 30 minutes
    "Ctrl2_": 1800,
    "Ctrl4_": 1800,
}

# Track last log time for slow-changing points: (host, label) -> timestamp
_last_slow_log: Dict[Tuple[str, str], float] = {}

# Pools/devices to poll. Override with a JSON env var if you want.
# Example:
#   export POOLS_JSON='{"Pool 1":{"host":"controller-1","unit":1},"Pool 2":{"host":"controller-2","unit":1}}'
DEFAULT_POOLS = {}

# Bitfield labels to treat as "event" sources (logged only on change).
# These MUST match labels in modbus_points.POINTS.
# Based on Ezetrol Modbus Register Documentation v4.4.2
BITFIELD_LABELS = [
    # Status registers (400300-400307) - operational states
    "Status_DigitalInputs",         # 400301 - Digital inputs (DI1-DI5)
    "Status_LimitContactStates",    # 400300 - Limit contacts 1-8
    "Status_RelayOutputs_K1_8",     # 400302 - Relay outputs K1-K6
    "Status_Mode_Controller1_Chlorine",  # 400304 - Controller 1 operation mode
    "Status_Mode_Controller2_pH",        # 400305 - Controller 2 operation mode
    "Status_Mode_Controller4_Ch4",       # 400307 - Controller 4 operation mode

    # Error code registers (400310-400326) - actual alarms
    # These are uint32 registers with detailed error bits per channel
    "ErrorCode_Chlorine",       # 400310 - Ch.1 Chlorine errors
    "ErrorCode_pH",             # 400314 - Ch.2 pH errors
    "ErrorCode_ORP",            # 400318 - Ch.3 ORP errors
    "ErrorCode_TotalChlorine",  # 400322 - Ch.4 Total chlorine errors
    "ErrorCode_Temperature",    # 400326 - Ch.5 Temperature errors
]

# Strings to pull periodically (so UI can name tabs etc.)
META_STRING_LABELS = ["SystemName", "SerialNumber"]

# Bits that represent actual alarms (warning/critical severity).
# Only these bits will be logged as alarm events.
# Format: "source_label:bit_name" for specific bits, or just "source_label" for all bits.
#
# NOTE: Status_Mode_Controller* registers are NOT error registers!
# Per Ezetrol docs, they contain operation mode bits:
#   b0=Manual, b1=Automatic, b2=Controller Off, b3=Auto tune running, etc.
# These are operational states, NOT faults.
#
# Actual errors are in ErrorCode_* registers (400310-400326)
ALARM_BITS = {
    # Limit/Contact States - these ARE alarms when triggered
    # 400300: Limit contacts 1-8 (generic - meaning depends on wiring)
    "Status_LimitContactStates:b0",    # Limit contact 1 (often flow switch)
    "Status_LimitContactStates:b1",    # Limit contact 2
    "Status_LimitContactStates:b2",    # Limit contact 3
    "Status_LimitContactStates:b3",    # Limit contact 4
    "Status_LimitContactStates:b4",    # Limit contact 5
    "Status_LimitContactStates:b5",    # Limit contact 6
    "Status_LimitContactStates:b6",    # Limit contact 7
    "Status_LimitContactStates:b7",    # Limit contact 8

    # Digital Input - Sample water stop
    "Status_DigitalInputs:b0",         # Sample water Stop - DI1
}

# Labels where ALL bits are alarms (error code registers)
# These are the ACTUAL error registers per Ezetrol documentation
# Each is uint32 with detailed error bits (see ErrorCode bit definitions below)
ALARM_ALL_BITS_LABELS = {
    "ErrorCode_Chlorine",       # 400310 - Ch.1 errors
    "ErrorCode_pH",             # 400314 - Ch.2 errors
    "ErrorCode_ORP",            # 400318 - Ch.3 errors
    "ErrorCode_TotalChlorine",  # 400322 - Ch.4 errors
    "ErrorCode_Temperature",    # 400326 - Ch.5 errors
}

# ErrorCode bit definitions (same for all channels per Ezetrol docs):
# Bit 0  (0x00000001): Zero point calibration error
# Bit 1  (0x00000002): DPD calibration error
# Bit 2  (0x00000004): pH7 calibration error
# Bit 3  (0x00000008): pHX calibration error
# Bit 4  (0x00000010): Calibration error (e.g. ORP)
# Bit 5  (0x00000020): Offset calibration error
# Bit 7  (0x00000080): Cell error
# Bit 8  (0x00000100): Factory calibration error
# Bit 11 (0x00000800): Setpoint error
# Bit 12 (0x00001000): Limit value error
# Bit 13 (0x00002000): Peak chlorination error (Cl2++)
# Bit 14 (0x00004000): Combined chlorine error
# Bit 15 (0x00008000): Overfeed (max dosing time)
# Bit 16 (0x00010000): Auto tune error
# Bit 18 (0x00040000): Temperature error
# Bit 19 (0x00080000): Tank empty message
# Bit 20 (0x00100000): No sample water
# Bit 23 (0x00800000): mA output 1 load error
# Bit 24 (0x01000000): mA output 2 load error
# Bit 25 (0x02000000): mA output 3 load error
# Bit 26 (0x04000000): mA output 4 load error
# Bit 27 (0x08000000): Dosage analog error
# Bit 28 (0x10000000): Flocculation error
# Bit 29 (0x20000000): Peak chlorination error
# Bit 30 (0x40000000): Analog hardware error
# Bit 31 (0x80000000): Data storage error (SD/EEprom)


def is_alarm_bit(source_label: str, bit_name: str) -> bool:
    """Check if a specific bit should be treated as an alarm."""
    # Check if this specific bit is in the alarm set
    if f"{source_label}:{bit_name}" in ALARM_BITS:
        return True
    # Check if all bits from this label are alarms (error registers)
    if source_label in ALARM_ALL_BITS_LABELS:
        return True
    return False


# Bits that represent operational states (not alarms).
# These are displayed in the Controller Status banner for monitoring.
# Based on Ezetrol Modbus Register Documentation v4.4.2
#
# Operation Mode Controller registers (400304, 400305, 400307):
#   b0  (0x0001): Manual
#   b1  (0x0002): Automatic
#   b2  (0x0004): Controller Off
#   b3  (0x0008): Auto tune running
#   b5  (0x0020): Controller Stop (Yout=0%)
#   b6  (0x0040): Freeze controller (Yout=Yout)
#   b7  (0x0080): Controller Yout=100%
#   b11 (0x0800): Eco Mode switchover
#   b13 (0x2000): Controller Standby

# Controller 1 - Chlorine (400304)
CONTROLLER_STATE_BITS = {
    "Status_Mode_Controller1_Chlorine": {
        "channel": "Chlorine",
        "bits": {
            0: {"name": "Manual", "icon": "M", "color": "#ff9800"},
            1: {"name": "Automatic", "icon": "A", "color": "#4caf50"},
            2: {"name": "Off", "icon": "X", "color": "#9e9e9e"},
            3: {"name": "AutoTune", "icon": "T", "color": "#2196f3"},
            5: {"name": "Stopped", "icon": "S", "color": "#f44336"},
            6: {"name": "Frozen", "icon": "F", "color": "#9c27b0"},
            7: {"name": "100%", "icon": "!", "color": "#ff5722"},
            11: {"name": "Eco", "icon": "E", "color": "#8bc34a"},
            13: {"name": "Standby", "icon": "Z", "color": "#607d8b"},
        }
    },
    "Status_Mode_Controller2_pH": {
        "channel": "pH",
        "bits": {
            0: {"name": "Manual", "icon": "M", "color": "#ff9800"},
            1: {"name": "Automatic", "icon": "A", "color": "#4caf50"},
            2: {"name": "Off", "icon": "X", "color": "#9e9e9e"},
            3: {"name": "AutoTune", "icon": "T", "color": "#2196f3"},
            5: {"name": "Stopped", "icon": "S", "color": "#f44336"},
            6: {"name": "Frozen", "icon": "F", "color": "#9c27b0"},
            7: {"name": "100%", "icon": "!", "color": "#ff5722"},
            11: {"name": "Eco", "icon": "E", "color": "#8bc34a"},
            13: {"name": "Standby", "icon": "Z", "color": "#607d8b"},
        }
    },
    "Status_Mode_Controller4_Ch4": {
        "channel": "Ch4",
        "bits": {
            0: {"name": "Manual", "icon": "M", "color": "#ff9800"},
            1: {"name": "Automatic", "icon": "A", "color": "#4caf50"},
            2: {"name": "Off", "icon": "X", "color": "#9e9e9e"},
            3: {"name": "AutoTune", "icon": "T", "color": "#2196f3"},
            5: {"name": "Stopped", "icon": "S", "color": "#f44336"},
            6: {"name": "Frozen", "icon": "F", "color": "#9c27b0"},
            7: {"name": "100%", "icon": "!", "color": "#ff5722"},
            11: {"name": "Eco", "icon": "E", "color": "#8bc34a"},
            13: {"name": "Standby", "icon": "Z", "color": "#607d8b"},
        }
    },
}

# Legacy STATE_BITS for backwards compatibility
STATE_BITS = {
    # Relay states - informational (normal operation)
    "Status_RelayOutputs_K1_8:b0": {
        "name": "Relay K1",
        "description": "Output relay K1 (pump/valve)",
    },
    "Status_RelayOutputs_K1_8:b1": {
        "name": "Relay K2",
        "description": "Output relay K2 (pump/valve)",
    },
    "Status_RelayOutputs_K1_8:b2": {
        "name": "Relay K3",
        "description": "Output relay K3 (pump/valve)",
    },
    "Status_RelayOutputs_K1_8:b3": {
        "name": "Relay K4",
        "description": "Output relay K4 (pump/valve)",
    },
    "Status_RelayOutputs_K1_8:b4": {
        "name": "Relay K5",
        "description": "Output relay K5 (pump/valve)",
    },
    "Status_RelayOutputs_K1_8:b5": {
        "name": "Relay K6",
        "description": "Output relay K6 (pump/valve)",
    },
}


# -----------------------------
# BAYROL Profile Configuration
# -----------------------------

# BAYROL measurement key -> database label mapping (for UI compatibility)
BAYROL_LABEL_MAP = {
    # Measurements (MEAS_REGS keys)
    "ph": "pH_MeasuredValue",
    "freecl_br": "Chlorine_MeasuredValue",
    "redox": "ORP_MeasuredValue",
    "t1": "Temp_MeasuredValue",
    "t2": "Temp2_MeasuredValue",
    "t3": "Temp3_MeasuredValue",
    "battery_v": "Battery_Voltage",
    "o2_dosed_amount": "O2_DosedAmount",
    # Parameters (PARAM_REGS keys)
    "setpoint_ph": "pH_Setpoint",
    "low_alarm_ph": "pH_AlarmLow",
    "high_alarm_ph": "pH_AlarmHigh",
    "setpoint_freecl_br": "Chlorine_Setpoint",
    "low_alarm_freecl_br": "Chlorine_AlarmLow",
    "high_alarm_freecl_br": "Chlorine_AlarmHigh",
    "setpoint_redox_1": "ORP_Setpoint",
    "low_alarm_redox_1": "ORP_AlarmLow",
    "high_alarm_redox_1": "ORP_AlarmHigh",
    "low_alarm_t1": "Temp_AlarmLow",
    "high_alarm_t1": "Temp_AlarmHigh",
}

# BAYROL tiered alarm polling configuration
# Critical alarms: polled every cycle
BAYROL_CRITICAL_ALARMS = {
    "collective_alarm",
    "no_flow_input_flow",
    "no_flow_input_in1",
    "upper_alarm_ph",
    "lower_alarm_ph",
    "upper_alarm_chlor_br",
    "lower_alarm_chlor_br",
}

# Important alarms: polled every 3 cycles
BAYROL_IMPORTANT_ALARMS = {
    "dosing_alarm_ph",
    "dosing_alarm_chlor_br",
    "dosing_alarm_redox",
    "level_alarm_chlor",
    "level_alarm_redox",
    "level_alarm_o2",
    "level_alarm_php",
    "level_alarm_phm",
    "level_alarm_flockmatic",
    "upper_alarm_t1",
    "lower_alarm_t1",
    "upper_alarm_t2",
    "lower_alarm_t2",
    "upper_alarm_t3",
    "lower_alarm_t3",
    "upper_alarm_redox",
    "lower_alarm_redox",
}

# Warning alarms: polled every 10 cycles
BAYROL_WARNING_ALARMS = {
    "power_on_delay",
    "battery_alarm",
    "level_warning_chlor",
    "level_warning_redox",
    "level_warning_o2",
    "level_warning_php",
    "level_warning_phm",
}


def should_log_point(host: str, label: str) -> bool:
    """
    Check if a point should be logged based on tiered logging intervals.
    Fast-changing points (measurements) are always logged.
    Slow-changing points (setpoints, limits) are logged less frequently.
    """
    now = time.time()

    # Check if this label matches any slow-log pattern
    interval = None
    for pattern, secs in SLOW_LOG_PATTERNS.items():
        if pattern in label:
            interval = secs
            break

    if interval is None:
        # Fast point - always log
        return True

    key = (host, label)
    last_time = _last_slow_log.get(key, 0)

    if now - last_time >= interval:
        _last_slow_log[key] = now
        return True

    return False


# -----------------------------
# Helpers
# -----------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def getenv_db_path() -> str:
    # Prefer explicit POOLDB
    p = os.getenv("POOLDB")
    if p:
        return p

    # Prefer /opt/PoolAIssistant if it exists, else local
    preferred = "/opt/PoolAIssistant/data/pool_readings.sqlite3"
    if os.path.isdir("/opt/PoolAIssistant"):
        return preferred
    return os.path.join(os.getcwd(), "pool_readings.sqlite3")

def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return float(int(x))
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None

def manual_to_offset(manual: int) -> int:
    """
    Convert manual register numbers to 0-based offsets.
    Supports common Modbus register bases used in vendor docs.
    """
    manual = int(manual)
    if manual >= 400001:
        return manual - 400001
    if manual >= 40001:
        return manual - 40001
    if manual >= 4001:
        return manual - 4001
    return manual

def chunk_points(points: List[dict]) -> List[Tuple[int, int, List[dict], str]]:
    """
    Build contiguous read chunks (same register space, contiguous offsets).
    Returns list of (start_offset, count, points_in_chunk).
    We only chunk points that live in holding regs and are numeric/str from POINTS list.
    """
    # Sort by manual address
    pts = sorted(points, key=lambda p: p["manual"])
    chunks: List[Tuple[int, int, List[dict]]] = []

    cur: List[dict] = []
    cur_start: Optional[int] = None
    cur_end: Optional[int] = None
    cur_reg: Optional[str] = None
    cur_single = False

    for p in pts:
        start = manual_to_offset(p["manual"])
        count = int(p.get("count", 1))
        end = start + count  # exclusive
        reg_type = p.get("reg_type", "holding")
        single = bool(p.get("single"))

        if cur_start is None:
            cur = [p]
            cur_start = start
            cur_end = end
            cur_reg = reg_type
            cur_single = single
            continue

        # If this point touches/overlaps current chunk, extend; else flush and start new
        if start <= cur_end and reg_type == cur_reg and not single and not cur_single:
            cur.append(p)
            cur_end = max(cur_end, end)
        else:
            chunks.append((cur_start, cur_end - cur_start, cur, cur_reg or "holding"))
            cur = [p]
            cur_start = start
            cur_end = end
            cur_reg = reg_type
            cur_single = single

    if cur_start is not None:
        chunks.append((cur_start, cur_end - cur_start, cur, cur_reg or "holding"))

    return chunks

def decode_str(registers: List[int], reg_count: int, byte_order: str = "AB") -> str:
    # Each 16-bit register holds 2 ASCII chars. Default is big-endian bytes.
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
    # Strip trailing nulls/spaces
    return raw.decode("ascii", errors="ignore").rstrip("\x00").rstrip()

def _order_words(registers: List[int], word_order: str) -> Tuple[int, int]:
    if word_order == "BA":
        return registers[1] & 0xFFFF, registers[0] & 0xFFFF
    return registers[0] & 0xFFFF, registers[1] & 0xFFFF


def decode_f32(registers: List[int], word_order: str = "AB") -> Optional[float]:
    if len(registers) < 2:
        return None
    w0, w1 = _order_words(registers, word_order)
    b = struct.pack(">HH", w0, w1)
    try:
        return safe_float(struct.unpack(">f", b)[0])
    except Exception:
        return None

def decode_u16(registers: List[int]) -> Optional[float]:
    if not registers:
        return None
    return safe_float(registers[0] & 0xFFFF)

def decode_u32(registers: List[int], word_order: str = "AB") -> Optional[float]:
    if len(registers) < 2:
        return None
    w0, w1 = _order_words(registers, word_order)
    v = ((w0 & 0xFFFF) << 16) | (w1 & 0xFFFF)
    return safe_float(v)

def apply_scale(value: Optional[float], scale: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if scale is None:
        return value
    try:
        return value * float(scale)
    except Exception:
        return value

def bit_names_from_value(value: int) -> List[str]:
    """Return list of bit labels 'b0'..'b31' that are ON."""
    on = []
    for i in range(32):
        if value & (1 << i):
            on.append(f"b{i}")
    return on


# -----------------------------
# SQLite
# -----------------------------

def db_connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    # Optimize for Raspberry Pi: reduce memory usage and improve performance
    con.execute("PRAGMA cache_size=-2000;")  # 2MB cache (negative = KB)
    con.execute("PRAGMA mmap_size=268435456;")  # 256MB memory-mapped I/O
    return con

def db_init(con: sqlite3.Connection) -> None:
    con.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        ts TEXT NOT NULL,
        pool TEXT NOT NULL,
        host TEXT NOT NULL,
        system_name TEXT,
        serial_number TEXT,
        point_label TEXT NOT NULL,
        value REAL,
        raw_type TEXT
    );
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_readings_host_ts ON readings(host, ts);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_readings_label_ts ON readings(point_label, ts);")

    con.execute("""
    CREATE TABLE IF NOT EXISTS device_meta (
        host TEXT PRIMARY KEY,
        pool TEXT,
        system_name TEXT,
        serial_number TEXT,
        last_seen_ts TEXT
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS alarm_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_ts TEXT NOT NULL,
        ended_ts TEXT,
        pool TEXT NOT NULL,
        host TEXT NOT NULL,
        system_name TEXT,
        serial_number TEXT,
        source_label TEXT NOT NULL,   -- e.g. Status_RelayOutputs_K1_8
        bit_name TEXT NOT NULL        -- e.g. b0..b31
    );
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_alarm_active ON alarm_events(host, ended_ts);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_alarm_started ON alarm_events(started_ts);")

    # Controller health tracking table
    con.execute("""
    CREATE TABLE IF NOT EXISTS controller_health (
        host TEXT PRIMARY KEY,
        pool TEXT NOT NULL,
        status TEXT NOT NULL,           -- 'online', 'degraded', 'offline'
        success_rate REAL,              -- 0.0 to 1.0
        consecutive_failures INTEGER DEFAULT 0,
        total_successes INTEGER DEFAULT 0,
        total_failures INTEGER DEFAULT 0,
        last_success_ts TEXT,
        last_failure_ts TEXT,
        last_failure_reason TEXT,
        last_ping_ok INTEGER,           -- 1=ok, 0=failed, NULL=not checked
        last_ping_ms REAL,
        updated_ts TEXT NOT NULL
    );
    """)
    con.commit()

def db_upsert_meta(con: sqlite3.Connection, host: str, pool: str, system_name: str, serial_number: str, ts: str) -> None:
    con.execute("""
    INSERT INTO device_meta(host, pool, system_name, serial_number, last_seen_ts)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(host) DO UPDATE SET
      pool=excluded.pool,
      system_name=excluded.system_name,
      serial_number=excluded.serial_number,
      last_seen_ts=excluded.last_seen_ts
    """, (host, pool, system_name, serial_number, ts))

def db_insert_readings(con: sqlite3.Connection, rows: List[Tuple[str, str, str, str, str, str, Optional[float], str]]) -> None:
    if not rows:
        return
    con.executemany("""
    INSERT INTO readings(ts, pool, host, system_name, serial_number, point_label, value, raw_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

def db_open_alarm(con: sqlite3.Connection, started_ts: str, pool: str, host: str, system_name: str, serial_number: str, source_label: str, bit_name: str) -> None:
    con.execute("""
    INSERT INTO alarm_events(started_ts, ended_ts, pool, host, system_name, serial_number, source_label, bit_name)
    VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
    """, (started_ts, pool, host, system_name, serial_number, source_label, bit_name))

def db_close_alarm(con: sqlite3.Connection, ended_ts: str, pool: str, host: str, source_label: str, bit_name: str) -> None:
    # Close the most recent active event for that (host, source_label, bit_name)
    con.execute("""
    UPDATE alarm_events
       SET ended_ts = ?
     WHERE id = (
         SELECT id FROM alarm_events
          WHERE host = ?
            AND pool = ?
            AND source_label = ?
            AND bit_name = ?
            AND ended_ts IS NULL
          ORDER BY started_ts DESC
          LIMIT 1
     )
    """, (ended_ts, host, pool, source_label, bit_name))


def db_update_controller_health(con: sqlite3.Connection, health: ControllerHealth) -> None:
    """Persist controller health status to database for UI access."""
    ts = utc_now_iso()

    if health.is_offline:
        status = "offline"
    elif health.is_degraded:
        status = "degraded"
    else:
        status = "online"

    con.execute("""
    INSERT INTO controller_health (
        host, pool, status, success_rate, consecutive_failures,
        total_successes, total_failures, last_success_ts, last_failure_ts,
        last_failure_reason, last_ping_ok, last_ping_ms, updated_ts
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(host) DO UPDATE SET
        pool = excluded.pool,
        status = excluded.status,
        success_rate = excluded.success_rate,
        consecutive_failures = excluded.consecutive_failures,
        total_successes = excluded.total_successes,
        total_failures = excluded.total_failures,
        last_success_ts = excluded.last_success_ts,
        last_failure_ts = excluded.last_failure_ts,
        last_failure_reason = excluded.last_failure_reason,
        last_ping_ok = excluded.last_ping_ok,
        last_ping_ms = excluded.last_ping_ms,
        updated_ts = excluded.updated_ts
    """, (
        health.host,
        health.name,
        status,
        health.success_rate,
        health.consecutive_failures,
        health.total_successes,
        health.total_failures,
        health.last_success_ts,
        health.last_failure_ts,
        health.last_failure_reason,
        1 if health.last_ping_ok else (0 if health.last_ping_ok is False else None),
        health.last_ping_ms,
        ts
    ))


# -----------------------------
# Modbus reading
# -----------------------------

def _modbus_unit_kw() -> str:
    try:
        params = inspect.signature(ModbusTcpClient.read_holding_registers).parameters
        if "device_id" in params:
            return "device_id"
        if "slave" in params:
            return "slave"
    except Exception:
        pass
    return "unit"


_UNIT_KW = _modbus_unit_kw()


def read_registers(client: ModbusTcpClient, address: int, count: int, unit: int, reg_type: str) -> Optional[List[int]]:
    try:
        kw = {_UNIT_KW: unit}
        if reg_type == "input":
            rr = client.read_input_registers(address=address, count=count, **kw)
        else:
            rr = client.read_holding_registers(address=address, count=count, **kw)
        if rr is None:
            return None
        if hasattr(rr, "isError") and rr.isError():
            return None
        regs = getattr(rr, "registers", None)
        if regs is None:
            return None
        return list(regs)
    except ModbusException:
        return None
    except Exception:
        return None

def build_point_sets() -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Returns:
      meta_points: str points we want (SystemName, SerialNumber)
      event_points: u16/u32 points that represent bitfields (BITFIELD_LABELS)
      numeric_points: all other numeric points (f32/u16/u32) excluding event_points
    """
    meta_points = [p for p in POINTS if p.get("label") in META_STRING_LABELS and p.get("type") == "str"]

    event_points = [p for p in POINTS if p.get("label") in BITFIELD_LABELS and p.get("type") in ("u16", "u32")]
    event_labels_set = set(p["label"] for p in event_points)

    # Skip Reserved fields - they contain no useful data and waste storage
    # Also skip Unit fields (strings logged as numeric) - they never change
    skip_patterns = ("Reserved", "_Unit")

    numeric_points = [
        p for p in POINTS
        if p.get("type") in ("f32", "u16", "u32")
        and p.get("label") not in event_labels_set
        and not any(pat in p.get("label", "") for pat in skip_patterns)
    ]

    return meta_points, event_points, numeric_points

def decode_point_from_chunk(p: dict, chunk_start_offset: int, chunk_regs: List[int]) -> Any:
    start = manual_to_offset(p["manual"])
    rel = start - chunk_start_offset
    cnt = int(p.get("count", 1))
    regs = chunk_regs[rel:rel+cnt]
    t = p.get("type")

    if t == "str":
        return decode_str(regs, cnt, p.get("byte_order", "AB"))
    if t == "f32":
        return decode_f32(regs, p.get("word_order", "AB"))
    if t == "u16":
        return apply_scale(decode_u16(regs), p.get("scale"))
    if t == "u32":
        return apply_scale(decode_u32(regs, p.get("word_order", "AB")), p.get("scale"))
    return None


# -----------------------------
# Main loop
# -----------------------------

def _load_settings_controllers() -> List[dict]:
    settings_path = os.getenv("POOLDASH_SETTINGS_PATH", "").strip()
    if not settings_path or not os.path.exists(settings_path):
        return []
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        controllers = data.get("controllers") or []
        if not isinstance(controllers, list):
            return []
        return [c for c in controllers if isinstance(c, dict)]
    except Exception:
        return []


def parse_pools() -> Dict[str, dict]:
    s = os.getenv("POOLS_JSON", "").strip()
    if not s:
        controllers = _load_settings_controllers()
        if not controllers:
            return DEFAULT_POOLS
        out = {}
        for c in controllers:
            if not c.get("enabled"):
                continue
            host = str(c.get("host", "")).strip()
            if not host:
                continue
            name = str(c.get("name") or host).strip()
            out[name] = {
                "host": host,
                "port": int(c.get("port", 502)),
                "unit": int(c.get("unit", 1)),
            }
        return out if out else DEFAULT_POOLS
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("POOLS_JSON must be a JSON object")
        # normalise
        out = {}
        for pool, cfg in obj.items():
            if not isinstance(cfg, dict):
                continue
            host = str(cfg.get("host", "")).strip()
            if not host:
                continue
            out[pool] = {
                "host": host,
                "port": int(cfg.get("port", 502)),
                "unit": int(cfg.get("unit", 1)),
            }
        return out if out else DEFAULT_POOLS
    except Exception as e:
        logging.warning("Invalid POOLS_JSON (%s). Using defaults.", e)
        return DEFAULT_POOLS

def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

def connect_with_retry(host: str, port: int, pool_name: str, health: ControllerHealth) -> Optional[ModbusTcpClient]:
    """
    Attempt to connect to Modbus device with retries and diagnostics.
    Returns connected client or None.
    """
    ts = utc_now_iso()

    # Pre-connection diagnostics if enabled
    if PING_CHECK_ENABLED:
        ping_ok, ping_ms = ping_host(host, PING_TIMEOUT)
        health.last_ping_ok = ping_ok
        health.last_ping_ms = ping_ms
        if not ping_ok:
            health.record_failure(ts, "ping failed - host unreachable")
            logging.warning("[%s %s] ping failed - host unreachable at network level", pool_name, host)
            return None

    if TCP_PRECHECK_ENABLED:
        tcp_ok, tcp_err = check_tcp_port(host, port, timeout_sec=2.0)
        if not tcp_ok:
            health.record_failure(ts, f"TCP port {port} unreachable: {tcp_err}")
            logging.warning("[%s %s] TCP port %d unreachable: %s", pool_name, host, port, tcp_err)
            return None

    # Attempt connection with retries
    last_error = ""
    for attempt in range(1, MODBUS_RETRIES + 1):
        client = ModbusTcpClient(host=host, port=port, timeout=MODBUS_TIMEOUT, retries=0)
        try:
            if client.connect():
                if attempt > 1:
                    logging.info("[%s %s] connected on attempt %d", pool_name, host, attempt)
                return client
            else:
                last_error = "connect() returned False"
        except Exception as e:
            last_error = str(e)

        # Clean up failed connection
        try:
            client.close()
        except Exception:
            pass

        # Delay before retry (with exponential increase)
        if attempt < MODBUS_RETRIES:
            delay = MODBUS_RETRY_DELAY * (1.5 ** (attempt - 1))
            time.sleep(delay)

    # All retries exhausted
    health.record_failure(ts, f"connect failed after {MODBUS_RETRIES} attempts: {last_error}")
    check_health_alert(health)
    logging.warning("[%s %s] connect failed after %d attempts: %s", pool_name, host, MODBUS_RETRIES, last_error)
    return None


# -----------------------------
# BAYROL-specific polling
# -----------------------------

def get_bayrol_alarms_to_check(poll_count: int) -> set:
    """
    Return the set of BAYROL alarm keys to check this cycle.
    Implements tiered polling to reduce Modbus traffic:
    - Critical alarms: every cycle
    - Important alarms: every 3 cycles
    - Warning alarms: every 10 cycles
    """
    alarms = set(BAYROL_CRITICAL_ALARMS)
    if poll_count % 3 == 0:
        alarms.update(BAYROL_IMPORTANT_ALARMS)
    if poll_count % 10 == 0:
        alarms.update(BAYROL_WARNING_ALARMS)
    return alarms


def poll_bayrol_controller(
    pool_name: str,
    host: str,
    port: int,
    unit: int,
    con: sqlite3.Connection,
    health: ControllerHealth,
    last_alarm_state: Dict[str, bool],
    poll_count: int
) -> Tuple[int, Dict[str, bool]]:
    """
    Poll a BAYROL controller using BayrolPoolManagerModbus reader.

    Args:
        pool_name: Name of the pool for logging/DB
        host: Controller IP address
        port: Modbus TCP port
        unit: Modbus unit/slave ID
        con: SQLite database connection
        health: ControllerHealth tracker for this controller
        last_alarm_state: Dict of alarm_key -> bool from previous poll
        poll_count: Current poll cycle number (for tiered alarm polling)

    Returns:
        Tuple of (readings_count, new_alarm_state)
    """
    from modbus.bayrol_modbus_points import BayrolPoolManagerModbus, MEAS_REGS, PARAM_REGS, ALARM_INPUTS

    ts = utc_now_iso()
    system_name = "BAYROL"
    serial_number = ""

    # Create BAYROL reader
    pm = BayrolPoolManagerModbus(host=host, port=port, unit_id=unit, timeout_s=MODBUS_TIMEOUT)

    if not pm.connect():
        health.record_failure(ts, "BAYROL connect failed")
        check_health_alert(health)
        return 0, last_alarm_state

    readings_count = 0
    new_alarm_state = dict(last_alarm_state)
    reading_rows: List[Tuple[str, str, str, str, str, str, Optional[float], str]] = []

    try:
        # ---- Read measurements (every cycle)
        for key in MEAS_REGS.keys():
            try:
                value = pm.read_measurement(key)
                label = BAYROL_LABEL_MAP.get(key, key)
                fv = safe_float(value)

                # Validate reading
                if fv is not None and not validate_reading(label, fv):
                    continue

                reading_rows.append((ts, pool_name, host, system_name, serial_number, label, fv, "f32"))

                # Cache for graceful degradation
                if fv is not None:
                    cache_value(host, label, fv)

                readings_count += 1
            except IOError as e:
                logging.debug("[%s %s] BAYROL measurement %s read failed: %s", pool_name, host, key, e)
            except Exception as e:
                logging.warning("[%s %s] BAYROL measurement %s error: %s", pool_name, host, key, e)

        # ---- Read parameters (setpoints, alarm thresholds) - less frequently
        if poll_count % 60 == 0:  # Every 5 minutes at 5-second intervals
            for key in PARAM_REGS.keys():
                try:
                    value = pm.read_param(key)
                    label = BAYROL_LABEL_MAP.get(key, key)
                    fv = safe_float(value)

                    reading_rows.append((ts, pool_name, host, system_name, serial_number, label, fv, "f32"))
                    readings_count += 1
                except IOError as e:
                    logging.debug("[%s %s] BAYROL param %s read failed: %s", pool_name, host, key, e)
                except Exception as e:
                    logging.warning("[%s %s] BAYROL param %s error: %s", pool_name, host, key, e)

        # ---- Read alarms (tiered polling)
        alarms_to_check = get_bayrol_alarms_to_check(poll_count)
        for alarm_key in alarms_to_check:
            if alarm_key not in ALARM_INPUTS:
                continue
            try:
                is_active = pm.read_alarm(alarm_key)
                prev_state = last_alarm_state.get(alarm_key)

                # Track state change
                if prev_state is None:
                    # First observation - just record state
                    new_alarm_state[alarm_key] = is_active
                elif is_active != prev_state:
                    # State changed
                    new_alarm_state[alarm_key] = is_active
                    source_label = "BAYROL_Alarm"
                    bit_name = alarm_key

                    if is_active:
                        db_open_alarm(con, ts, pool_name, host, system_name, serial_number, source_label, bit_name)
                        logging.warning("[%s %s] BAYROL alarm ON: %s", pool_name, host, alarm_key)
                    else:
                        db_close_alarm(con, ts, pool_name, host, source_label, bit_name)
                        logging.info("[%s %s] BAYROL alarm OFF: %s", pool_name, host, alarm_key)
                else:
                    new_alarm_state[alarm_key] = is_active

            except IOError as e:
                logging.debug("[%s %s] BAYROL alarm %s read failed: %s", pool_name, host, alarm_key, e)
            except Exception as e:
                logging.warning("[%s %s] BAYROL alarm %s error: %s", pool_name, host, alarm_key, e)

        # ---- Commit to database
        if reading_rows:
            db_insert_readings(con, reading_rows)

        db_upsert_meta(con, host, pool_name, system_name, serial_number, ts)
        con.commit()

        # Record success
        health.record_success(ts)

        # Log with recovery info if applicable
        extra_info = ""
        if health.total_failures > 0 and health.consecutive_failures == 0:
            extra_info = f" [recovered, {health.success_rate*100:.0f}% recent success rate]"

        logging.info("[%s %s] BAYROL wrote %d readings%s",
                     pool_name, host, readings_count, extra_info)

        return readings_count, new_alarm_state

    except Exception as e:
        health.record_failure(ts, f"BAYROL poll error: {e}")
        check_health_alert(health)
        logging.error("[%s %s] BAYROL error: %s (failures: %d consecutive)",
                      pool_name, host, e, health.consecutive_failures)
        try:
            con.rollback()
        except Exception:
            pass
        return 0, last_alarm_state

    finally:
        try:
            pm.close()
        except Exception:
            pass

        # Persist health status
        try:
            db_update_controller_health(con, health)
            con.commit()
        except Exception as e:
            logging.debug("[%s %s] failed to update health: %s", pool_name, host, e)


def main_bayrol_loop(con: sqlite3.Connection, db_path: str) -> int:
    """
    Main polling loop for BAYROL profile.
    Uses BayrolPoolManagerModbus reader instead of batch register reads.
    """
    global _poll_count

    pools = parse_pools()
    if not pools:
        logging.error("No pools configured. Set POOLS_JSON before starting.")
        return 1

    logging.info("BAYROL profile - polling %d pools every %.1fs using BayrolPoolManagerModbus",
                 len(pools), SAMPLE_SECONDS)

    # Notify systemd that we're ready
    notify_ready()

    # Track alarm states per controller: {(pool, host): {alarm_key: bool}}
    last_alarm_states: Dict[Tuple[str, str], Dict[str, bool]] = {}

    while True:
        loop_start = time.time()
        _poll_count += 1

        # Periodic health summary logging
        if HEALTH_LOG_INTERVAL > 0 and _poll_count % HEALTH_LOG_INTERVAL == 0:
            log_health_summary()

        for pool_name, cfg in pools.items():
            host = cfg["host"]
            port = int(cfg.get("port", 502))
            unit = int(cfg.get("unit", 1))

            # Get/create health tracker
            health = get_controller_health(host, pool_name)

            # Check backoff
            if BACKOFF_ENABLED and health.should_skip_this_cycle():
                logging.debug("[%s %s] skipping due to backoff (%.1fs remaining)",
                              pool_name, host, health.next_attempt_after - time.time())
                continue

            # Get previous alarm state for this controller
            alarm_key = (pool_name, host)
            last_alarm_state = last_alarm_states.get(alarm_key, {})

            # Poll the controller
            readings, new_alarm_state = poll_bayrol_controller(
                pool_name, host, port, unit, con, health, last_alarm_state, _poll_count
            )

            # Update alarm state
            last_alarm_states[alarm_key] = new_alarm_state

        # Notify systemd watchdog
        notify_watchdog()

        # Sleep to next tick
        elapsed = time.time() - loop_start
        sleep_s = max(0.1, SAMPLE_SECONDS - elapsed)
        time.sleep(sleep_s)

    # unreachable
    # return 0


def main() -> int:
    global _poll_count
    setup_logging()

    db_path = getenv_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None

    con = db_connect(db_path)
    db_init(con)
    logging.info("DB ready at %s", db_path)
    logging.info("Connection settings: timeout=%.1fs, retries=%d, ping_check=%s, backoff=%s",
                 MODBUS_TIMEOUT, MODBUS_RETRIES, PING_CHECK_ENABLED, BACKOFF_ENABLED)

    # BAYROL profile uses a different polling architecture
    if IS_BAYROL_PROFILE:
        logging.info("BAYROL profile detected - using BayrolPoolManagerModbus reader")
        return main_bayrol_loop(con, db_path)

    meta_points, event_points, numeric_points = build_point_sets()

    meta_chunks = chunk_points(meta_points) if meta_points else []
    event_chunks = chunk_points(event_points) if event_points else []
    numeric_chunks = chunk_points(numeric_points) if numeric_points else []

    pools = parse_pools()
    if not pools:
        logging.error("No pools configured. Set POOLS_JSON before starting.")
        return 1
    logging.info("Polling %d pools every %.1fs", len(pools), SAMPLE_SECONDS)

    # Notify systemd that we're ready
    notify_ready()

    # Keep last known bit states per (pool, host, source_label) -> int value
    last_bitfield_value: Dict[Tuple[str, str, str], int] = {}

    while True:
        loop_start = time.time()
        _poll_count += 1

        # Periodic health summary logging
        if HEALTH_LOG_INTERVAL > 0 and _poll_count % HEALTH_LOG_INTERVAL == 0:
            log_health_summary()

        for pool_name, cfg in pools.items():
            host = cfg["host"]
            port = int(cfg.get("port", 502))
            unit = int(cfg.get("unit", 1))
            ts = utc_now_iso()

            # Get/create health tracker for this controller
            health = get_controller_health(host, pool_name)

            # Check if we should skip due to backoff
            if BACKOFF_ENABLED and health.should_skip_this_cycle():
                logging.debug("[%s %s] skipping due to backoff (%.1fs remaining)",
                              pool_name, host, health.next_attempt_after - time.time())
                continue

            system_name = ""
            serial_number = ""

            # Use improved connection with retry logic
            client = connect_with_retry(host, port, pool_name, health)
            if client is None:
                # Log cached values info for debugging
                cached = get_cache_summary(host)
                if cached:
                    key_values = {k: v for k, v in cached.items() if any(m in k for m in ["pH", "Chlorine", "ORP", "Temp"])}
                    if key_values:
                        logging.debug("[%s %s] Last cached values available: %s", pool_name, host, key_values)
                # Persist health status even on connection failure
                try:
                    db_update_controller_health(con, health)
                    con.commit()
                except Exception:
                    pass
                continue

            try:

                # ---- Read meta strings (SystemName, SerialNumber)
                if meta_chunks:
                    for start_off, count, pts, reg_type in meta_chunks:
                        regs = read_registers(client, start_off, count, unit, reg_type)
                        if regs is None:
                            logging.warning("[%s %s] meta read failed offset=%d count=%d", pool_name, host, start_off, count)
                            continue
                        for p in pts:
                            val = decode_point_from_chunk(p, start_off, regs)
                            if p["label"] == "SystemName" and isinstance(val, str):
                                system_name = val
                            if p["label"] == "SerialNumber" and isinstance(val, str):
                                serial_number = val

                # ---- Continuous numeric readings
                reading_rows: List[Tuple[str, str, str, str, str, str, Optional[float], str]] = []
                if numeric_chunks:
                    for start_off, count, pts, reg_type in numeric_chunks:
                        regs = read_registers(client, start_off, count, unit, reg_type)
                        if regs is None:
                            logging.warning("[%s %s] numeric read failed offset=%d count=%d", pool_name, host, start_off, count)
                            continue
                        for p in pts:
                            label = p["label"]
                            # Apply tiered logging - skip slow-changing points if not due
                            if not should_log_point(host, label):
                                continue
                            raw_type = p.get("type", "")
                            val = decode_point_from_chunk(p, start_off, regs)
                            fv = safe_float(val)
                            # Validate reading before saving
                            final_label = LABEL_ALIASES.get(label) if LABEL_ALIASES.get(label) and LABEL_ALIASES.get(label) != label else label
                            if fv is not None and not validate_reading(final_label, fv):
                                continue  # Skip invalid readings
                            alias = LABEL_ALIASES.get(label)
                            # For Ezetrol layout remapping, write the remapped label only to avoid duplicates.
                            if alias and alias != label:
                                reading_rows.append((ts, pool_name, host, system_name, serial_number, alias, fv, raw_type))
                                # Cache good value for graceful degradation
                                if fv is not None:
                                    cache_value(host, alias, fv)
                            else:
                                reading_rows.append((ts, pool_name, host, system_name, serial_number, label, fv, raw_type))
                                # Cache good value for graceful degradation
                                if fv is not None:
                                    cache_value(host, label, fv)

                # ---- Event bitfields (status/errors), log changes only
                if event_chunks:
                    for start_off, count, pts, reg_type in event_chunks:
                        regs = read_registers(client, start_off, count, unit, reg_type)
                        if regs is None:
                            logging.warning("[%s %s] event read failed offset=%d count=%d", pool_name, host, start_off, count)
                            continue
                        for p in pts:
                            source_label = p["label"]
                            raw_type = p.get("type")
                            val = decode_point_from_chunk(p, start_off, regs)
                            if val is None:
                                continue

                            # val is numeric float (from decode_u16/u32) -> cast to int safely
                            try:
                                ival = int(val)
                            except Exception:
                                continue

                            key = (pool_name, host, source_label)
                            prev = last_bitfield_value.get(key)

                            if prev is None:
                                # First observation: store only (don’t backfill events)
                                last_bitfield_value[key] = ival
                                continue

                            if ival == prev:
                                continue

                            # Determine which bits changed
                            changed = prev ^ ival
                            for bit in range(32):
                                if changed & (1 << bit):
                                    bit_name = f"b{bit}"
                                    # Only log if this bit is an actual alarm (not just status info)
                                    if not is_alarm_bit(source_label, bit_name):
                                        continue
                                    now_on = bool(ival & (1 << bit))
                                    if now_on:
                                        db_open_alarm(con, ts, pool_name, host, system_name, serial_number, source_label, bit_name)
                                    else:
                                        db_close_alarm(con, ts, pool_name, host, source_label, bit_name)

                            last_bitfield_value[key] = ival

                # ---- Commit writes for this device poll
                if reading_rows:
                    db_insert_readings(con, reading_rows)

                db_upsert_meta(con, host, pool_name, system_name, serial_number, ts)
                con.commit()

                # Record successful poll in health tracker
                health.record_success(ts)

                # Log with recovery info if coming back from failures
                extra_info = ""
                if health.total_failures > 0 and health.consecutive_failures == 0:
                    extra_info = f" [recovered, {health.success_rate*100:.0f}% recent success rate]"

                logging.info("[%s %s] wrote %d readings%s%s",
                             pool_name, host, len(reading_rows),
                             f" meta='{system_name}'" if system_name else "",
                             extra_info)

            except Exception as e:
                # Record failure in health tracker
                health.record_failure(ts, f"poll error: {e}")
                check_health_alert(health)
                logging.error("[%s %s] error: %s (failures: %d consecutive)",
                              pool_name, host, e, health.consecutive_failures)
                try:
                    con.rollback()
                except Exception:
                    pass
            finally:
                try:
                    if client.connected:
                        client.close()
                except Exception:
                    pass

                # Persist health status to database
                try:
                    db_update_controller_health(con, health)
                    con.commit()
                except Exception as e:
                    logging.debug("[%s %s] failed to update health: %s", pool_name, host, e)

        # Notify systemd watchdog that we're still alive
        notify_watchdog()

        # sleep to next tick
        elapsed = time.time() - loop_start
        sleep_s = max(0.1, SAMPLE_SECONDS - elapsed)
        time.sleep(sleep_s)

    # unreachable
    # return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
