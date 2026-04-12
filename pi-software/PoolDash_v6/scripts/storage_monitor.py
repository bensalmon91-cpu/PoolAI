#!/usr/bin/env python3
"""
Storage Monitor Daemon for PoolAIssistant

Monitors disk usage and only triggers cleanup when storage is critically low.
ALWAYS syncs data to remote server BEFORE deleting anything locally.

Design philosophy: Keep ALL data locally as long as possible for AI analysis.
Only delete when absolutely necessary (disk nearly full).
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("POOLDASH_DATA_DIR", "/opt/PoolAIssistant/data"))
SETTINGS_PATH = Path(os.environ.get("POOLDASH_SETTINGS_PATH", DATA_DIR / "pooldash_settings.json"))
POOL_DB_PATH = Path(os.environ.get("POOL_DB_PATH", DATA_DIR / "pool_readings.sqlite3"))
CLEANUP_SCRIPT = SCRIPT_DIR / "data_cleanup.py"
SYNC_SCRIPT = SCRIPT_DIR / "remote_sync.py"

# Monitor settings
CHECK_INTERVAL_SECONDS = 300  # Check every 5 minutes

# ONLY delete data when disk is critically low
CRITICAL_FREE_MB = 500        # Start cleanup when less than 500MB free
EMERGENCY_FREE_MB = 200       # Aggressive cleanup when less than 200MB free

# State
running = True
last_cleanup_time = None
last_sync_time = None
MIN_CLEANUP_INTERVAL = 1800   # Don't run cleanup more than once per 30 minutes


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global running
    log.info(f"Received signal {signum}, shutting down...")
    running = False


def load_settings():
    """Load settings from JSON file."""
    defaults = {
        "remote_sync_enabled": False,
        "remote_sync_url": "",
        "remote_api_key": "",
    }

    if not SETTINGS_PATH.exists():
        return defaults

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            defaults.update(data)
            return defaults
    except Exception as e:
        log.warning(f"Could not load settings: {e}")
        return defaults


def get_storage_info():
    """Get current storage usage information."""
    info = {
        "db_size_mb": 0,
        "disk_used_percent": 0,
        "disk_free_mb": 0,
        "disk_total_mb": 0,
    }

    try:
        # Database size (including WAL files)
        if POOL_DB_PATH.exists():
            db_size = POOL_DB_PATH.stat().st_size
            # Include WAL and SHM files
            wal_path = Path(str(POOL_DB_PATH) + "-wal")
            shm_path = Path(str(POOL_DB_PATH) + "-shm")
            if wal_path.exists():
                db_size += wal_path.stat().st_size
            if shm_path.exists():
                db_size += shm_path.stat().st_size
            info["db_size_mb"] = db_size / (1024 * 1024)

        # Disk usage
        if DATA_DIR.exists():
            total, used, free = shutil.disk_usage(str(DATA_DIR))
            info["disk_total_mb"] = total / (1024 * 1024)
            info["disk_used_percent"] = (used / total) * 100
            info["disk_free_mb"] = free / (1024 * 1024)
    except Exception as e:
        log.warning(f"Could not get storage info: {e}")

    return info


def run_sync():
    """Sync data to remote server before cleanup."""
    global last_sync_time

    settings = load_settings()
    if not settings.get("remote_sync_enabled") or not settings.get("remote_api_key"):
        log.info("Remote sync not configured - skipping sync before cleanup")
        return False

    if not SYNC_SCRIPT.exists():
        log.warning(f"Sync script not found: {SYNC_SCRIPT}")
        return False

    log.info("Syncing data to remote server before cleanup...")

    try:
        result = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--force"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for sync
            cwd=str(SCRIPT_DIR.parent),
            env={
                **os.environ,
                "POOLDASH_SETTINGS_PATH": str(SETTINGS_PATH),
                "POOL_DB_PATH": str(POOL_DB_PATH),
                "POOLDASH_DATA_DIR": str(DATA_DIR),
            }
        )

        if result.returncode == 0:
            log.info("Remote sync completed successfully")
            last_sync_time = time.time()
            return True
        else:
            log.error(f"Remote sync failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        log.error("Remote sync timed out")
        return False
    except Exception as e:
        log.error(f"Failed to run sync: {e}")
        return False


def run_cleanup(reason: str, aggressive: bool = False):
    """Run the cleanup script. Always sync first if configured."""
    global last_cleanup_time

    # Check if we've run cleanup recently
    if last_cleanup_time:
        elapsed = time.time() - last_cleanup_time
        if elapsed < MIN_CLEANUP_INTERVAL and not aggressive:
            log.info(f"Skipping cleanup - last run {elapsed/60:.1f} minutes ago")
            return False

    log.warning(f"{'EMERGENCY ' if aggressive else ''}Cleanup triggered: {reason}")

    # ALWAYS try to sync before deleting data
    run_sync()

    if not CLEANUP_SCRIPT.exists():
        log.error(f"Cleanup script not found: {CLEANUP_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(CLEANUP_SCRIPT), "--force"] + (["--aggressive"] if aggressive else []),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout
            cwd=str(SCRIPT_DIR.parent),
            env={
                **os.environ,
                "POOLDASH_SETTINGS_PATH": str(SETTINGS_PATH),
                "POOL_DB_PATH": str(POOL_DB_PATH),
                "POOLDASH_DATA_DIR": str(DATA_DIR),
            }
        )

        if result.returncode == 0:
            log.info("Cleanup completed successfully")
            if result.stdout:
                # Log last 500 chars of output
                log.info(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            last_cleanup_time = time.time()
            return True
        else:
            log.error(f"Cleanup failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        log.error("Cleanup timed out after 30 minutes")
        return False
    except Exception as e:
        log.error(f"Failed to run cleanup: {e}")
        return False


def check_storage():
    """Check storage and trigger cleanup ONLY if disk is critically low."""
    storage = get_storage_info()

    log.info(
        f"Storage: DB={storage['db_size_mb']:.1f}MB, "
        f"Disk={storage['disk_used_percent']:.1f}% used, "
        f"{storage['disk_free_mb']:.0f}MB free"
    )

    # EMERGENCY: Very low disk space - aggressive cleanup
    if storage["disk_free_mb"] < EMERGENCY_FREE_MB:
        run_cleanup(
            f"EMERGENCY: Only {storage['disk_free_mb']:.0f}MB free (need {EMERGENCY_FREE_MB}MB)",
            aggressive=True
        )
        return

    # WARNING: Low disk space - normal cleanup
    if storage["disk_free_mb"] < CRITICAL_FREE_MB:
        run_cleanup(f"Low disk space: {storage['disk_free_mb']:.0f}MB free (threshold: {CRITICAL_FREE_MB}MB)")
        return

    # Otherwise: Do nothing - keep all data!
    log.debug("Storage OK - keeping all data")


def main():
    """Main monitor loop."""
    global running

    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    log.info("=" * 60)
    log.info("Storage Monitor starting (DATA PRESERVATION MODE)")
    log.info(f"  Data dir: {DATA_DIR}")
    log.info(f"  Database: {POOL_DB_PATH}")
    log.info(f"  Settings: {SETTINGS_PATH}")
    log.info(f"  Check interval: {CHECK_INTERVAL_SECONDS}s")
    log.info(f"  Cleanup threshold: <{CRITICAL_FREE_MB}MB free")
    log.info(f"  Emergency threshold: <{EMERGENCY_FREE_MB}MB free")
    log.info("  Policy: Keep ALL data until disk is nearly full")
    log.info("=" * 60)

    # Initial status
    storage = get_storage_info()
    log.info(
        f"Initial: DB={storage['db_size_mb']:.1f}MB, "
        f"Disk={storage['disk_used_percent']:.1f}% used, "
        f"{storage['disk_free_mb']:.0f}MB free"
    )

    if storage["disk_free_mb"] >= CRITICAL_FREE_MB:
        log.info(f"Storage healthy - data will be preserved until <{CRITICAL_FREE_MB}MB free")

    while running:
        try:
            check_storage()
        except Exception as e:
            log.error(f"Error during check: {e}")

        # Sleep in small increments to respond to signals quickly
        for _ in range(CHECK_INTERVAL_SECONDS):
            if not running:
                break
            time.sleep(1)

    log.info("Storage Monitor stopped")


if __name__ == "__main__":
    main()
