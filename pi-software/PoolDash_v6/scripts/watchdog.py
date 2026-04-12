# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Service Watchdog

"""
Watchdog script to monitor and restart critical services if they fail.
Checks disk space, memory, and service health.
"""

import os
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/opt/PoolAIssistant/data")
LOG_FILE = DATA_DIR / "watchdog.log"
ALERT_FILE = DATA_DIR / "alerts.json"

# Critical services to monitor
SERVICES = ["poolaissistant_ui", "poolaissistant_logger", "poolaissistant_ap_manager"]

# Thresholds
DISK_WARNING_PCT = 80
DISK_CRITICAL_PCT = 90
MEMORY_WARNING_PCT = 85


def log(message, level="INFO"):
    """Log message to file and stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


def check_disk_space():
    """Check disk usage and return alerts."""
    alerts = []
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_pct = (1 - free / total) * 100

        if used_pct >= DISK_CRITICAL_PCT:
            alerts.append({
                "type": "disk_critical",
                "message": f"CRITICAL: Disk usage at {used_pct:.1f}%",
                "value": used_pct
            })
            log(f"CRITICAL: Disk usage at {used_pct:.1f}%", "CRITICAL")
        elif used_pct >= DISK_WARNING_PCT:
            alerts.append({
                "type": "disk_warning",
                "message": f"WARNING: Disk usage at {used_pct:.1f}%",
                "value": used_pct
            })
            log(f"WARNING: Disk usage at {used_pct:.1f}%", "WARNING")
        else:
            log(f"Disk usage: {used_pct:.1f}%")
    except Exception as e:
        log(f"Error checking disk: {e}", "ERROR")

    return alerts


def check_memory():
    """Check memory usage."""
    alerts = []
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    meminfo[key] = int(parts[1])

        total = meminfo.get("MemTotal", 1)
        available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        used_pct = (1 - available / total) * 100

        if used_pct >= MEMORY_WARNING_PCT:
            alerts.append({
                "type": "memory_warning",
                "message": f"WARNING: Memory usage at {used_pct:.1f}%",
                "value": used_pct
            })
            log(f"WARNING: Memory usage at {used_pct:.1f}%", "WARNING")
        else:
            log(f"Memory usage: {used_pct:.1f}%")
    except Exception as e:
        log(f"Error checking memory: {e}", "ERROR")

    return alerts


def check_services():
    """Check and restart failed services."""
    alerts = []

    for service in SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=10
            )
            status = result.stdout.strip()

            if status != "active":
                log(f"Service {service} is {status}, attempting restart...", "WARNING")
                alerts.append({
                    "type": "service_restart",
                    "message": f"Service {service} was {status}, restarted",
                    "service": service
                })

                # Attempt restart
                subprocess.run(
                    ["systemctl", "restart", service],
                    capture_output=True, timeout=30
                )

                # Verify restart
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True, timeout=10
                )
                if result.stdout.strip() == "active":
                    log(f"Service {service} restarted successfully")
                else:
                    log(f"Service {service} failed to restart!", "CRITICAL")
                    alerts.append({
                        "type": "service_failed",
                        "message": f"CRITICAL: Service {service} failed to restart",
                        "service": service
                    })
            else:
                log(f"Service {service}: OK")

        except Exception as e:
            log(f"Error checking service {service}: {e}", "ERROR")

    return alerts


def save_alerts(alerts):
    """Save alerts to JSON file for dashboard."""
    if not alerts:
        return

    try:
        existing = []
        if ALERT_FILE.exists():
            try:
                with open(ALERT_FILE) as f:
                    existing = json.load(f)
            except:
                pass

        # Add timestamp to new alerts
        for alert in alerts:
            alert["timestamp"] = datetime.now().isoformat()

        # Keep last 100 alerts
        all_alerts = alerts + existing
        all_alerts = all_alerts[:100]

        with open(ALERT_FILE, "w") as f:
            json.dump(all_alerts, f, indent=2)

    except Exception as e:
        log(f"Error saving alerts: {e}", "ERROR")


def cleanup_old_logs():
    """Trim watchdog log if it gets too large."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 10 * 1024 * 1024:  # 10MB
            # Keep last 1000 lines
            with open(LOG_FILE) as f:
                lines = f.readlines()
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-1000:])
            log("Trimmed watchdog log file")
    except Exception as e:
        log(f"Error cleaning up logs: {e}", "ERROR")


def main():
    log("=" * 50)
    log("Watchdog check started")

    all_alerts = []

    all_alerts.extend(check_disk_space())
    all_alerts.extend(check_memory())
    all_alerts.extend(check_services())

    save_alerts(all_alerts)
    cleanup_old_logs()

    status = "OK" if not all_alerts else f"{len(all_alerts)} alerts"
    log(f"Watchdog check complete: {status}")

    # Exit with error code if critical alerts
    critical = any(a.get("type", "").endswith("critical") or a.get("type") == "service_failed" for a in all_alerts)
    sys.exit(1 if critical else 0)


if __name__ == "__main__":
    main()
