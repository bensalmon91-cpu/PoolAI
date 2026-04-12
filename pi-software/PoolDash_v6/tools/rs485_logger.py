#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoolAIssistant - RS485 Modbus RTU Logger

Dedicated logger for RS485 serial water testing devices.
Writes to the same database as the TCP Modbus logger for unified data access.

What it does:
1) Reads configured RS485 devices from settings
2) Polls each device at regular intervals
3) Writes readings to SQLite table: readings (long format)
   - host field uses "rs485:<device_name>" format to distinguish from TCP devices
4) Supports standalone or merged display modes with pools

DB path:
- Uses env var POOLDB if set
- Else defaults to: /opt/PoolAIssistant/data/pool_readings.sqlite3

Settings:
- Uses env var POOLDASH_SETTINGS_PATH for RS485 device configuration

Important:
- This script is read-only (no Modbus writes)
- Runs separately from the TCP logger for isolation during debugging
"""

from __future__ import annotations

import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for modbus imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modbus.rs485.rtu_client import (
    RS485Client,
    RS485Health,
    decode_u16,
    decode_u32,
    decode_f32,
    decode_str,
    apply_scale,
)
from modbus.rs485.water_tester_points import (
    POINTS,
    MEASUREMENT_LABELS,
    validate_reading,
)

# -----------------------------
# Settings
# -----------------------------

SAMPLE_SECONDS = float(os.getenv("RS485_SAMPLE_SECONDS", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper().strip()

# Health monitoring
HEALTH_LOG_INTERVAL = int(os.getenv("HEALTH_LOG_INTERVAL", "60"))
FAILURE_ALERT_THRESHOLD = int(os.getenv("FAILURE_ALERT_THRESHOLD", "5"))

# Track poll count for periodic health logging
_poll_count = 0

# Global health tracker: port -> RS485Health
_device_health: Dict[str, RS485Health] = {}


# -----------------------------
# Helpers
# -----------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def getenv_db_path() -> str:
    p = os.getenv("POOLDB")
    if p:
        return p
    preferred = "/opt/PoolAIssistant/data/pool_readings.sqlite3"
    if os.path.isdir("/opt/PoolAIssistant"):
        return preferred
    return os.path.join(os.getcwd(), "pool_readings.sqlite3")


def safe_float(x: Any) -> Optional[float]:
    import math
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
    """Convert manual register numbers to 0-based offsets."""
    manual = int(manual)
    if manual >= 400001:
        return manual - 400001
    if manual >= 40001:
        return manual - 40001
    if manual >= 4001:
        return manual - 4001
    return manual


# -----------------------------
# Settings Loading
# -----------------------------

def load_rs485_devices() -> List[Dict[str, Any]]:
    """Load RS485 device configuration from settings."""
    settings_path = os.getenv("POOLDASH_SETTINGS_PATH", "").strip()
    if not settings_path or not os.path.exists(settings_path):
        logging.warning("No settings file found at POOLDASH_SETTINGS_PATH")
        return []

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        devices = data.get("rs485_devices") or []
        if not isinstance(devices, list):
            return []

        # Filter to enabled devices only
        enabled = []
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if not dev.get("enabled", True):
                continue
            if not dev.get("port"):
                continue
            enabled.append(dev)

        return enabled

    except Exception as e:
        logging.error("Failed to load RS485 settings: %s", e)
        return []


# -----------------------------
# SQLite
# -----------------------------

def db_connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-2000;")
    con.execute("PRAGMA mmap_size=268435456;")
    return con


def db_init(con: sqlite3.Connection) -> None:
    """Ensure database tables exist (same schema as TCP logger)."""
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

    # RS485 health tracking table
    con.execute("""
    CREATE TABLE IF NOT EXISTS rs485_health (
        port TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        success_rate REAL,
        consecutive_failures INTEGER DEFAULT 0,
        total_successes INTEGER DEFAULT 0,
        total_failures INTEGER DEFAULT 0,
        last_success_ts TEXT,
        last_failure_ts TEXT,
        last_failure_reason TEXT,
        updated_ts TEXT NOT NULL
    );
    """)
    con.commit()


def db_insert_readings(
    con: sqlite3.Connection,
    rows: List[Tuple[str, str, str, str, str, str, Optional[float], str]]
) -> None:
    if not rows:
        return
    con.executemany("""
    INSERT INTO readings(ts, pool, host, system_name, serial_number, point_label, value, raw_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)


def db_upsert_meta(
    con: sqlite3.Connection,
    host: str,
    pool: str,
    system_name: str,
    serial_number: str,
    ts: str
) -> None:
    con.execute("""
    INSERT INTO device_meta(host, pool, system_name, serial_number, last_seen_ts)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(host) DO UPDATE SET
      pool=excluded.pool,
      system_name=excluded.system_name,
      serial_number=excluded.serial_number,
      last_seen_ts=excluded.last_seen_ts
    """, (host, pool, system_name, serial_number, ts))


def db_update_rs485_health(con: sqlite3.Connection, health: RS485Health) -> None:
    """Persist RS485 device health status to database."""
    ts = utc_now_iso()

    if health.is_offline:
        status = "offline"
    elif health.is_degraded:
        status = "degraded"
    else:
        status = "online"

    con.execute("""
    INSERT INTO rs485_health (
        port, name, status, success_rate, consecutive_failures,
        total_successes, total_failures, last_success_ts, last_failure_ts,
        last_failure_reason, updated_ts
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(port) DO UPDATE SET
        name = excluded.name,
        status = excluded.status,
        success_rate = excluded.success_rate,
        consecutive_failures = excluded.consecutive_failures,
        total_successes = excluded.total_successes,
        total_failures = excluded.total_failures,
        last_success_ts = excluded.last_success_ts,
        last_failure_ts = excluded.last_failure_ts,
        last_failure_reason = excluded.last_failure_reason,
        updated_ts = excluded.updated_ts
    """, (
        health.port,
        health.name,
        status,
        health.success_rate,
        health.consecutive_failures,
        health.total_successes,
        health.total_failures,
        health.last_success_ts,
        health.last_failure_ts,
        health.last_failure_reason,
        ts
    ))


# -----------------------------
# Reading & Decoding
# -----------------------------

def decode_point(
    client: RS485Client,
    point: Dict[str, Any]
) -> Tuple[Optional[float], str]:
    """
    Read and decode a single point from the RS485 device.

    Returns:
        (value, raw_type) tuple
    """
    address = manual_to_offset(point["manual"])
    count = int(point.get("count", 1))
    reg_type = point.get("reg_type", "holding")
    data_type = point.get("type", "u16")

    # Read registers
    if reg_type == "input":
        regs = client.read_input_registers(address, count)
    else:
        regs = client.read_holding_registers(address, count)

    if regs is None:
        return None, data_type

    # Decode based on type
    value = None
    word_order = point.get("word_order", "AB")
    byte_order = point.get("byte_order", "AB")

    if data_type == "u16":
        value = decode_u16(regs)
    elif data_type == "u32":
        value = decode_u32(regs, word_order)
    elif data_type == "f32":
        value = decode_f32(regs, word_order)
    elif data_type == "str":
        # Return string as None for numeric readings
        # (strings should be handled separately for metadata)
        return None, data_type

    # Apply scaling if defined
    scale = point.get("scale")
    if scale is not None and value is not None:
        value = apply_scale(value, scale)

    return safe_float(value), data_type


def poll_device(
    client: RS485Client,
    device_config: Dict[str, Any],
    con: sqlite3.Connection
) -> int:
    """
    Poll a single RS485 device and write readings to database.

    Returns:
        Number of readings written.
    """
    ts = utc_now_iso()
    device_name = device_config.get("name", "Water Tester")
    mode = device_config.get("mode", "standalone")
    merged_pool = device_config.get("merged_with_pool", "")

    # Determine pool name based on mode
    if mode == "merged" and merged_pool:
        pool_name = merged_pool
    else:
        pool_name = device_name

    # Host identifier for RS485 devices
    host = f"rs485:{device_name}"

    reading_rows = []

    # Read all measurement points
    for point in POINTS:
        label = point.get("label", "")

        # Skip non-measurement points for regular logging
        # (info/config points could be logged less frequently)
        if label not in MEASUREMENT_LABELS:
            continue

        try:
            value, raw_type = decode_point(client, point)

            if value is not None:
                # Validate reading
                if not validate_reading(label, value):
                    logging.warning("[%s] Invalid reading: %s=%s", device_name, label, value)
                    continue

                reading_rows.append((
                    ts,
                    pool_name,
                    host,
                    device_name,  # system_name
                    "",           # serial_number
                    label,
                    value,
                    raw_type
                ))

        except Exception as e:
            logging.warning("[%s] Error reading %s: %s", device_name, label, e)

    # Write to database
    if reading_rows:
        db_insert_readings(con, reading_rows)
        db_upsert_meta(con, host, pool_name, device_name, "", ts)
        con.commit()

    return len(reading_rows)


# -----------------------------
# Health Tracking
# -----------------------------

def get_device_health(port: str, name: str) -> RS485Health:
    """Get or create health tracker for a device."""
    if port not in _device_health:
        _device_health[port] = RS485Health(port=port, name=name)
    return _device_health[port]


def log_health_summary() -> None:
    """Log health summary for all devices."""
    if not _device_health:
        return
    lines = ["RS485 Device Health Summary:"]
    for port, health in _device_health.items():
        lines.append(
            f"  {health.name} ({port}): {health.status_summary()} "
            f"[{health.total_successes}/{health.total_successes + health.total_failures} polls]"
        )
    logging.info("\n".join(lines))


def check_health_alert(health: RS485Health) -> None:
    """Check if device has exceeded failure threshold and log alert."""
    if health.consecutive_failures >= FAILURE_ALERT_THRESHOLD:
        logging.error(
            "[ALERT] RS485 device %s (%s) failed %d times consecutively! Last error: %s",
            health.name, health.port, health.consecutive_failures, health.last_failure_reason
        )


# -----------------------------
# Systemd Watchdog Support
# -----------------------------

def notify_watchdog() -> None:
    """Notify systemd watchdog that the service is still alive."""
    try:
        import sdnotify
        sdnotify.SystemdNotifier().notify("WATCHDOG=1")
    except ImportError:
        pass
    except Exception:
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
# Main Loop
# -----------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)sZ %(levelname)s [RS485] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> int:
    global _poll_count
    setup_logging()

    db_path = getenv_db_path()
    if os.path.dirname(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    con = db_connect(db_path)
    db_init(con)
    logging.info("DB ready at %s", db_path)

    # Notify systemd we're ready
    notify_ready()

    while True:
        loop_start = time.time()
        _poll_count += 1

        # Reload device config each loop (allows hot-reload of settings)
        devices = load_rs485_devices()

        if not devices:
            logging.debug("No enabled RS485 devices configured")
            time.sleep(SAMPLE_SECONDS)
            continue

        # Periodic health summary
        if HEALTH_LOG_INTERVAL > 0 and _poll_count % HEALTH_LOG_INTERVAL == 0:
            log_health_summary()

        for device_config in devices:
            port = device_config.get("port", "")
            baud = int(device_config.get("baud", 9600))
            name = device_config.get("name", "Water Tester")
            unit_id = int(device_config.get("unit_id", 1))
            ts = utc_now_iso()

            health = get_device_health(port, name)

            # Check backoff
            if health.should_skip_this_cycle():
                logging.debug("[%s] Skipping due to backoff", name)
                continue

            # Create client and poll
            client = RS485Client(
                port=port,
                baudrate=baud,
                unit_id=unit_id,
                name=name,
            )

            try:
                if not client.connect():
                    health.record_failure(ts, "Connection failed")
                    check_health_alert(health)
                    logging.warning("[%s] Failed to connect to %s", name, port)
                    continue

                readings_count = poll_device(client, device_config, con)

                if readings_count > 0:
                    health.record_success(ts)
                    logging.info("[%s] Wrote %d readings", name, readings_count)
                else:
                    health.record_failure(ts, "No readings returned")
                    logging.warning("[%s] No readings from device", name)

            except Exception as e:
                health.record_failure(ts, str(e))
                check_health_alert(health)
                logging.error("[%s] Poll error: %s", name, e)
                try:
                    con.rollback()
                except Exception:
                    pass

            finally:
                client.disconnect()

                # Update health in database
                try:
                    db_update_rs485_health(con, health)
                    con.commit()
                except Exception as e:
                    logging.debug("[%s] Failed to update health: %s", name, e)

        # Notify systemd watchdog
        notify_watchdog()

        # Sleep to next tick
        elapsed = time.time() - loop_start
        sleep_s = max(0.1, SAMPLE_SECONDS - elapsed)
        time.sleep(sleep_s)

    # Unreachable
    # return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
