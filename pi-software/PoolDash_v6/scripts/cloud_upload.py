#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoolAIssistant Cloud Upload Service

Uploads periodic snapshots to the cloud portal including:
- Latest pool chemistry readings (pH, chlorine, ORP, temperature)
- Device health metrics (CPU temp, memory, disk, uptime)
- Controller status (online/offline)
- Active alarms

Default interval: 6 minutes (configurable via settings)
"""

from __future__ import annotations

import json
import os
import sys
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import requests


# =============================================================================
# CONFIGURATION
# =============================================================================

def load_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATA_DIR = Path(load_env("POOLAISSISTANT_DATA", "/opt/PoolAIssistant/data"))
SETTINGS_PATH = DATA_DIR / "pooldash_settings.json"
TOKEN_PATH = DATA_DIR / "device_token.json"
DB_PATH = DATA_DIR / "pool_readings.sqlite3"
UPLOAD_STATE_PATH = DATA_DIR / "cloud_upload_state.json"

DEFAULT_INTERVAL_MINUTES = 6
REQUEST_TIMEOUT = 30


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save {path}: {e}")


def get_setting(key: str, default: Any = None) -> Any:
    settings = load_json(SETTINGS_PATH)
    return settings.get(key, default)


def update_settings(updates: Dict[str, Any]) -> None:
    """Update specific settings without overwriting others."""
    settings = load_json(SETTINGS_PATH)
    settings.update(updates)
    save_json(SETTINGS_PATH, settings)


# =============================================================================
# DEVICE HEALTH COLLECTION
# =============================================================================

def get_cpu_temperature() -> Optional[float]:
    """Get CPU temperature in Celsius."""
    try:
        # Try reading from thermal zone
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            with open(temp_path) as f:
                return int(f.read().strip()) / 1000.0
        # Fallback to vcgencmd
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # Output: temp=45.0'C
            temp_str = result.stdout.strip()
            return float(temp_str.replace("temp=", "").replace("'C", ""))
    except Exception:
        pass
    return None


def get_memory_usage() -> Optional[float]:
    """Get memory usage percentage."""
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total = meminfo.get("MemTotal", 1)
            available = meminfo.get("MemAvailable", 0)
            used = total - available
            return round((used / total) * 100, 1)
    except Exception:
        pass
    return None


def get_disk_usage() -> Optional[float]:
    """Get disk usage percentage for root filesystem."""
    try:
        result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    pct = parts[4].rstrip("%")
                    return float(pct)
    except Exception:
        pass
    return None


def get_uptime_seconds() -> Optional[int]:
    """Get system uptime in seconds."""
    try:
        with open("/proc/uptime") as f:
            uptime_str = f.read().split()[0]
            return int(float(uptime_str))
    except Exception:
        pass
    return None


def collect_health_data() -> Dict[str, Any]:
    """Collect all device health metrics."""
    return {
        "uptime_seconds": get_uptime_seconds(),
        "cpu_temp": get_cpu_temperature(),
        "memory_used_pct": get_memory_usage(),
        "disk_used_pct": get_disk_usage(),
    }


# =============================================================================
# DATABASE QUERIES
# =============================================================================

def get_latest_readings(db_path: Path, minutes: int = 10) -> List[Dict]:
    """
    Get the latest reading for each pool/metric combination from the last N minutes.
    """
    if not db_path.exists():
        return []

    readings = []
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row

        # Get readings from the last N minutes, taking the most recent per pool/metric
        cutoff = (utc_now() - timedelta(minutes=minutes)).isoformat()
        query = """
            SELECT pool, point_label as metric, value, ts,
                   ROW_NUMBER() OVER (PARTITION BY pool, point_label ORDER BY ts DESC) as rn
            FROM readings
            WHERE ts > ?
        """
        cursor = conn.execute(query, (cutoff,))
        rows = cursor.fetchall()

        # Filter to only the most recent per pool/metric
        for row in rows:
            if row["rn"] == 1:
                readings.append({
                    "pool": row["pool"] or "",
                    "metric": row["metric"],
                    "value": row["value"],
                    "ts": row["ts"],
                })

        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}")

    return readings


def get_active_alarms(db_path: Path) -> Dict[str, Any]:
    """Get active alarm summary from the database."""
    if not db_path.exists():
        return {"total": 0, "critical": 0, "warning": 0, "active": []}

    alarms = {"total": 0, "critical": 0, "warning": 0, "active": []}

    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row

        # Get alarms that haven't ended yet
        query = """
            SELECT pool, source_label, bit_name, started_ts
            FROM alarm_events
            WHERE ended_ts IS NULL OR ended_ts = ''
            ORDER BY started_ts DESC
            LIMIT 20
        """
        cursor = conn.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            alarm_name = row["bit_name"] or row["source_label"] or "Unknown"
            # Simple severity detection based on common alarm patterns
            is_critical = any(kw in alarm_name.lower() for kw in
                            ["critical", "emergency", "fail", "error"])

            alarms["total"] += 1
            if is_critical:
                alarms["critical"] += 1
            else:
                alarms["warning"] += 1

            alarms["active"].append({
                "pool": row["pool"] or "",
                "source": alarm_name,
                "since": row["started_ts"],
            })

        conn.close()
    except sqlite3.OperationalError:
        # Table might not exist yet
        pass
    except Exception as e:
        print(f"Error reading alarms: {e}")

    return alarms


def get_controller_status(db_path: Path) -> List[Dict]:
    """Get controller online/offline status based on recent readings."""
    if not db_path.exists():
        return []

    controllers = []
    settings = load_json(SETTINGS_PATH)
    configured_controllers = settings.get("controllers", [])

    if not configured_controllers:
        return []

    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row

        now = utc_now()

        for ctrl in configured_controllers:
            host = ctrl.get("host", "")
            name = ctrl.get("name", host)
            enabled = ctrl.get("enabled", True)

            if not host or not enabled:
                continue

            # Get most recent reading from this controller
            query = """
                SELECT ts FROM readings
                WHERE host = ?
                ORDER BY ts DESC
                LIMIT 1
            """
            cursor = conn.execute(query, (host,))
            row = cursor.fetchone()

            if row and row["ts"]:
                try:
                    last_ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                    minutes_ago = (now - last_ts).total_seconds() / 60
                    online = minutes_ago < 60  # Online if reading within 60 minutes
                except Exception:
                    online = False
                    minutes_ago = None
            else:
                online = False
                minutes_ago = None

            controllers.append({
                "host": host,
                "name": name,
                "online": online,
                "minutes_ago": int(minutes_ago) if minutes_ago is not None else None,
            })

        conn.close()
    except Exception as e:
        print(f"Error checking controller status: {e}")

    return controllers


# =============================================================================
# SNAPSHOT BUILDING
# =============================================================================

def build_snapshot() -> Dict[str, Any]:
    """Build the complete snapshot payload to upload."""
    settings = load_json(SETTINGS_PATH)
    device_id = settings.get("device_id", "")

    readings = get_latest_readings(DB_PATH)
    health = collect_health_data()
    controllers = get_controller_status(DB_PATH)
    alarms = get_active_alarms(DB_PATH)

    # Count online/offline controllers
    controllers_online = sum(1 for c in controllers if c.get("online"))
    controllers_offline = len(controllers) - controllers_online

    return {
        "device_id": device_id,
        "timestamp": utc_now_iso(),
        "readings": readings,
        "health": {
            **health,
            "controllers_online": controllers_online,
            "controllers_offline": controllers_offline,
        },
        "controllers": controllers,
        "alarms": alarms,
    }


# =============================================================================
# UPLOAD
# =============================================================================

def upload_snapshot(backend_url: str, api_key: str, snapshot: Dict) -> Dict:
    """Upload snapshot to the server."""
    url = backend_url.rstrip("/") + "/api/device/snapshot.php"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=snapshot,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 200:
        return response.json()
    else:
        raise RuntimeError(f"Upload failed: {response.status_code} {response.text}")


# =============================================================================
# MAIN
# =============================================================================

def should_upload() -> bool:
    """Check if enough time has passed since last upload."""
    settings = load_json(SETTINGS_PATH)

    # Check if uploads are enabled
    if not settings.get("cloud_upload_enabled", True):
        return False

    # Get interval from settings
    interval_minutes = settings.get("cloud_upload_interval_minutes", DEFAULT_INTERVAL_MINUTES)

    # Check last upload time
    last_ts = settings.get("cloud_upload_last_ts", "")
    if not last_ts:
        return True

    try:
        last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        elapsed = (utc_now() - last_dt).total_seconds() / 60
        return elapsed >= interval_minutes
    except Exception:
        return True


def main() -> int:
    print(f"[{utc_now_iso()}] Cloud upload starting...")

    # Check if we should upload
    if not should_upload():
        print("Skipping upload - not enough time elapsed or uploads disabled")
        return 0

    # Load device token
    token_data = load_json(TOKEN_PATH)
    api_key = token_data.get("token", "")
    backend_url = token_data.get("backend", "") or get_setting("backend_url", "")

    if not api_key:
        print("ERROR: Device not provisioned (no API token)")
        update_settings({
            "cloud_upload_last_status": "error",
            "cloud_upload_last_error": "Device not provisioned",
        })
        return 1

    if not backend_url:
        print("ERROR: Backend URL not configured")
        update_settings({
            "cloud_upload_last_status": "error",
            "cloud_upload_last_error": "Backend URL not configured",
        })
        return 1

    # Build snapshot
    try:
        snapshot = build_snapshot()
        readings_count = len(snapshot.get("readings", []))
        print(f"Built snapshot with {readings_count} readings")
    except Exception as e:
        print(f"ERROR: Failed to build snapshot: {e}")
        update_settings({
            "cloud_upload_last_status": "error",
            "cloud_upload_last_error": str(e),
        })
        return 1

    # Upload
    try:
        result = upload_snapshot(backend_url, api_key, snapshot)
        print(f"Upload successful: {result}")
        update_settings({
            "cloud_upload_last_ts": utc_now_iso(),
            "cloud_upload_last_status": "ok",
            "cloud_upload_last_error": "",
        })
        return 0
    except requests.RequestException as e:
        print(f"ERROR: Network error during upload: {e}")
        update_settings({
            "cloud_upload_last_status": "warning",
            "cloud_upload_last_error": f"Network error: {e}",
        })
        return 1
    except Exception as e:
        print(f"ERROR: Upload failed: {e}")
        update_settings({
            "cloud_upload_last_status": "error",
            "cloud_upload_last_error": str(e),
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
