# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Health Check Endpoint

"""
Health check endpoint for monitoring Pi status.
Server can ping this to verify the Pi is alive and functioning.
"""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, current_app
from ..db.connection import get_connection, check_database_health

health_bp = Blueprint("health", __name__)
logger = logging.getLogger(__name__)

DATA_DIR = Path("/opt/PoolAIssistant/data")
APP_DIR = Path("/opt/PoolAIssistant/app")


def get_disk_usage():
    """Get disk usage percentage."""
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_pct = round((1 - free / total) * 100, 1)
        return {"total_gb": round(total / 1e9, 2), "free_gb": round(free / 1e9, 2), "used_pct": used_pct}
    except OSError as e:
        logger.warning(f"Failed to get disk usage: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting disk usage: {e}")
        return None


def get_db_stats():
    """Get database statistics."""
    db_path = DATA_DIR / "pool_readings.sqlite3"

    try:
        if not db_path.exists():
            logger.debug("Database file does not exist yet")
            return None

        size_mb = round(db_path.stat().st_size / 1e6, 2)

        with get_connection(str(db_path), readonly=True, timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM readings")
            row_count = cursor.fetchone()[0]
            cursor.execute("SELECT MAX(ts) FROM readings")
            last_reading = cursor.fetchone()[0]

        return {"size_mb": size_mb, "row_count": row_count, "last_reading": last_reading}

    except sqlite3.Error as e:
        logger.warning(f"Database error getting stats: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting db stats: {e}")
        return None


def get_version():
    """Get current software version."""
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return os.environ.get("SOFTWARE_VERSION", "unknown")


def get_uptime():
    """Get system uptime."""
    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return {"seconds": int(uptime_seconds), "human": f"{days}d {hours}h {minutes}m"}
    except FileNotFoundError:
        logger.debug("/proc/uptime not found (not running on Linux?)")
        return None
    except (ValueError, IOError) as e:
        logger.warning(f"Failed to read uptime: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting uptime: {e}")
        return None


def get_cpu_temperature():
    """Get CPU temperature in Celsius (Raspberry Pi)."""
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        if not thermal_path.exists():
            logger.debug("Thermal zone not found (not running on Pi?)")
            return None
        temp_raw = thermal_path.read_text().strip()
        temp_c = float(temp_raw) / 1000.0
        return {
            "celsius": round(temp_c, 1),
            "fahrenheit": round(temp_c * 9 / 5 + 32, 1)
        }
    except (ValueError, IOError) as e:
        logger.warning(f"Failed to read CPU temperature: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting CPU temperature: {e}")
        return None


def check_services():
    """Check if critical services are running."""
    import subprocess
    services = {}
    for svc in ["poolaissistant_ui", "poolaissistant_logger"]:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5
            )
            services[svc] = result.stdout.strip() == "active"
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout checking service {svc}")
            services[svc] = False
        except FileNotFoundError:
            logger.debug("systemctl not found (not running on systemd system?)")
            services[svc] = False
        except Exception as e:
            logger.warning(f"Failed to check service {svc}: {e}")
            services[svc] = False
    return services


@health_bp.route("/api/health")
def health_check():
    """
    Health check endpoint.
    Returns system status for monitoring.
    """
    disk = get_disk_usage()
    db = get_db_stats()
    services = check_services()
    temperature = get_cpu_temperature()

    # Determine overall health
    healthy = True
    issues = []

    if disk and disk["used_pct"] > 90:
        healthy = False
        issues.append("Disk usage critical (>90%)")

    if not all(services.values()):
        healthy = False
        issues.append("Some services not running")

    # Temperature warnings
    if temperature:
        temp_c = temperature["celsius"]
        if temp_c > 80:
            healthy = False
            issues.append(f"CPU temperature critical ({temp_c}°C)")
        elif temp_c > 70:
            issues.append(f"CPU temperature high ({temp_c}°C)")

    return jsonify({
        "ok": healthy,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": get_version(),
        "uptime": get_uptime(),
        "disk": disk,
        "database": db,
        "services": services,
        "temperature": temperature,
        "issues": issues
    })


@health_bp.route("/api/ping")
def ping():
    """Simple ping endpoint - minimal response for quick checks."""
    return jsonify({"ok": True, "ts": datetime.utcnow().isoformat() + "Z"})
