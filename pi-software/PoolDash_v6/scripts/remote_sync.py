#!/usr/bin/env python3
"""
Remote Sync Script for MOD Projects Backend

Uploads pool readings database to the MOD Projects server.
Supports both full file upload and incremental delta sync.

Usage:
    python remote_sync.py          # Normal scheduled sync (respects interval)
    python remote_sync.py --force  # Force immediate sync
    python remote_sync.py --delta  # Incremental sync (readings since last upload)
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INSTANCE_DIR = PROJECT_DIR / "instance"
DATA_DIR = Path(os.environ.get("POOLDASH_DATA_DIR", "/opt/PoolAIssistant/data"))

# Settings and state files
SETTINGS_PATH = Path(os.environ.get("POOLDASH_SETTINGS_PATH", INSTANCE_DIR / "pooldash_settings.json"))
SYNC_STATE_PATH = DATA_DIR / "remote_sync_state.json"
POOL_DB_PATH = Path(os.environ.get("POOL_DB_PATH", DATA_DIR / "pool_readings.sqlite3"))


def load_settings():
    """Load settings from JSON file."""
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {}


def save_settings(settings):
    """Save settings to JSON file."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Error saving settings: {e}")


def load_sync_state():
    """Load sync state (last sync timestamp, etc.)."""
    if not SYNC_STATE_PATH.exists():
        return {"last_sync_ts": None, "last_uploaded_row": 0}
    try:
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_sync_ts": None, "last_uploaded_row": 0}


def save_sync_state(state):
    """Save sync state."""
    try:
        SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving sync state: {e}")


def calculate_checksum(file_path):
    """Calculate SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def should_sync(settings, state, force=False):
    """Check if we should sync based on schedule."""
    if force:
        return True

    if not settings.get("remote_sync_enabled"):
        print("Remote sync is disabled.")
        return False

    if not settings.get("remote_api_key"):
        print("No API key configured.")
        return False

    last_sync = state.get("last_sync_ts")
    if not last_sync:
        return True

    try:
        last_sync_dt = datetime.fromisoformat(last_sync)
    except ValueError:
        return True

    interval_hours = settings.get("remote_sync_interval_hours", 72)
    next_sync = last_sync_dt + timedelta(hours=interval_hours)

    if datetime.now() >= next_sync:
        return True

    print(f"Next sync scheduled for: {next_sync.isoformat()}")
    return False


def upload_file(settings, file_path, file_type="database"):
    """Upload a file to the MOD Projects server."""
    url = settings.get("remote_sync_url", "https://modprojects.co.uk").rstrip("/")
    api_key = settings.get("remote_api_key", "")
    device_id = settings.get("device_id", "")
    device_alias = settings.get("device_alias", "")

    if not api_key:
        raise ValueError("No API key configured")

    upload_url = f"{url}/api/upload.php"

    file_size = os.path.getsize(file_path)
    checksum = calculate_checksum(file_path)

    print(f"Device: {device_alias or device_id[:8] + '...'}")
    print(f"Uploading {file_path.name} ({file_size / 1024 / 1024:.2f} MB)")
    print(f"Checksum: {checksum[:16]}...")

    headers = {
        "X-API-Key": api_key,
        "X-Device-Id": device_id,
        "X-Device-Alias": device_alias,
    }

    with open(file_path, "rb") as f:
        # Include device info in filename for easier identification
        upload_filename = f"{device_alias or device_id[:8]}_{file_path.name}" if device_id else file_path.name
        files = {"file": (upload_filename, f, "application/octet-stream")}
        data = {
            "type": file_type,
            "device_id": device_id,
            "device_alias": device_alias,
        }

        response = requests.post(
            upload_url,
            headers=headers,
            files=files,
            data=data,
            timeout=300,
        )

    if response.status_code != 200:
        raise Exception(f"Upload failed: {response.status_code} - {response.text}")

    result = response.json()
    if not result.get("ok"):
        raise Exception(f"Upload failed: {result.get('error', 'Unknown error')}")

    print(f"Upload successful! ID: {result.get('upload_id')}")
    return result


def upload_delta(settings, state):
    """Upload only new readings since last sync (incremental)."""
    if not POOL_DB_PATH.exists():
        print(f"Database not found: {POOL_DB_PATH}")
        return False

    url = settings.get("remote_sync_url", "https://modprojects.co.uk").rstrip("/")
    api_key = settings.get("remote_api_key", "")

    last_row = state.get("last_uploaded_row", 0)

    # Connect to database
    con = sqlite3.connect(str(POOL_DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row

    # Get new readings
    cursor = con.execute(
        """
        SELECT rowid, ts, pool, host, system_name, serial_number, point_label, value, raw_type
        FROM readings
        WHERE rowid > ?
        ORDER BY rowid ASC
        LIMIT 10000
        """,
        (last_row,),
    )

    rows = cursor.fetchall()
    con.close()

    if not rows:
        print("No new readings to upload.")
        return True

    print(f"Found {len(rows)} new readings since rowid {last_row}")

    # Format as JSON
    readings = []
    max_rowid = last_row
    for row in rows:
        readings.append({
            "ts": row["ts"],
            "pool": row["pool"],
            "host": row["host"],
            "system_name": row["system_name"],
            "serial_number": row["serial_number"],
            "point_label": row["point_label"],
            "value": row["value"],
            "raw_type": row["raw_type"],
        })
        max_rowid = max(max_rowid, row["rowid"])

    # Upload as JSON
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    # Note: This would require a dedicated endpoint on the server
    # For now, we'll fall back to full file upload
    print("Delta upload not yet implemented on server - falling back to full upload")
    return None  # Signal to use full upload


def sync_full(settings):
    """Perform a full database file upload."""
    if not POOL_DB_PATH.exists():
        print(f"Database not found: {POOL_DB_PATH}")
        return False

    try:
        result = upload_file(settings, POOL_DB_PATH, "database")
        return True
    except Exception as e:
        print(f"Upload failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Sync pool data to MOD Projects server")
    parser.add_argument("--force", action="store_true", help="Force immediate sync")
    parser.add_argument("--delta", action="store_true", help="Incremental sync only")
    args = parser.parse_args()

    print(f"=== Remote Sync - {datetime.now().isoformat()} ===")

    settings = load_settings()
    state = load_sync_state()

    if not should_sync(settings, state, args.force):
        return 0

    success = False

    if args.delta:
        result = upload_delta(settings, state)
        if result is None:
            # Fall back to full sync
            success = sync_full(settings)
        else:
            success = result
    else:
        success = sync_full(settings)

    if success:
        # Update state
        state["last_sync_ts"] = datetime.now().isoformat()
        save_sync_state(state)

        # Also update settings with last sync time
        settings["last_remote_sync_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_settings(settings)

        print("Sync completed successfully!")
        return 0
    else:
        print("Sync failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
