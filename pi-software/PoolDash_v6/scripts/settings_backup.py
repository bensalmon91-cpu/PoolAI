# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Settings Backup to Cloud

"""
Backs up device settings to the cloud server.
Run daily via systemd timer or after settings changes.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/opt/PoolAIssistant/data")
APP_DIR = Path("/opt/PoolAIssistant/app")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
BACKUP_STATUS_FILE = DATA_DIR / "backup_status.json"

# Files to backup
BACKUP_FILES = [
    SETTINGS_FILE,
    DATA_DIR / "maintenance.json",
    DATA_DIR / "host_names.json",
]


def load_settings():
    """Load settings from JSON file."""
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def get_version():
    """Get current software version."""
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return os.environ.get("SOFTWARE_VERSION", "unknown")


def get_system_info():
    """Get system information for backup metadata."""
    info = {
        "version": get_version(),
        "backup_time": datetime.now().isoformat(),
        "hostname": os.uname().nodename if hasattr(os, 'uname') else "unknown",
    }

    # Get uptime
    try:
        with open("/proc/uptime") as f:
            info["uptime_seconds"] = int(float(f.read().split()[0]))
    except:
        pass

    # Get disk usage
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        info["disk_used_pct"] = round((1 - free / total) * 100, 1)
    except:
        pass

    return info


def backup_settings():
    """Backup settings to cloud server."""
    settings = load_settings()
    api_key = settings.get("api_key") or settings.get("remote_api_key", "")
    backend_url = (settings.get("backend_url") or settings.get("remote_sync_url", "")).rstrip("/")

    if not api_key or not backend_url:
        print("ERROR: No API key or backend URL configured")
        return False

    # Collect all settings into one payload
    backup_data = {
        "system_info": get_system_info(),
        "files": {}
    }

    for file_path in BACKUP_FILES:
        if file_path.exists():
            try:
                with open(file_path) as f:
                    backup_data["files"][file_path.name] = json.load(f)
            except json.JSONDecodeError:
                # Read as text if not JSON
                backup_data["files"][file_path.name] = file_path.read_text()
            except Exception as e:
                print(f"Warning: Could not read {file_path.name}: {e}")

    # Upload to server
    upload_url = f"{backend_url}/api/backup_settings.php"

    try:
        response = requests.post(
            upload_url,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=backup_data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                print(f"Settings backed up successfully")
                save_status({"ok": True, "time": datetime.now().isoformat()})
                return True
            else:
                print(f"Backup failed: {result.get('error')}")
        else:
            print(f"Backup failed with status {response.status_code}")

    except Exception as e:
        print(f"Backup error: {e}")

    save_status({"ok": False, "time": datetime.now().isoformat(), "error": str(e) if 'e' in dir() else "Unknown"})
    return False


def save_status(status):
    """Save backup status."""
    try:
        with open(BACKUP_STATUS_FILE, "w") as f:
            json.dump(status, f)
    except:
        pass


if __name__ == "__main__":
    backup_settings()
