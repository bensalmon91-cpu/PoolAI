import os
import json
import threading
import subprocess
import socket
import sqlite3
import zipfile
import time
from io import BytesIO
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint, current_app, render_template, request, redirect,
    url_for, flash, send_file, Response
)

from ..utils.net import tcp_connect_ok, scan_all_subnets_for_modbus, test_modbus_connection

# ---- Network info cache (avoid slow subprocess calls on every page load) ----
_net_cache = {"ssid": "", "wlan_ip": "", "eth_ip": "", "ts": 0}
_net_cache_ttl = 10  # Cache for 10 seconds (short enough that a dropped WiFi is visible on next page load)
_net_cache_lock = threading.Lock()


def _invalidate_net_cache():
    """Invalidate network cache to force refresh on next read."""
    global _net_cache
    with _net_cache_lock:
        _net_cache["ts"] = 0


def _run_subprocess_safe(cmd, timeout=10, check=False):
    """
    Run a subprocess safely with proper error handling.
    Returns (success: bool, stdout: str, stderr: str)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if check and result.returncode != 0:
            return False, result.stdout, result.stderr
        return True, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, "", str(e)


def _get_cached_network_info():
    """Get network info with caching to avoid slow subprocess calls."""
    global _net_cache
    now = time.time()
    if now - _net_cache["ts"] < _net_cache_ttl:
        return _net_cache["ssid"], _net_cache["wlan_ip"], _net_cache["eth_ip"]

    # Refresh cache
    ssid = ""
    try:
        # Use nmcli to get current WiFi SSID (iwgetid not available on all systems)
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("yes:"):
                    ssid = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass

    def ip_of(dev: str) -> str:
        # `ip -4 -o addr show dev <dev>` prints one line per address.
        # When an interface has multiple IPs (e.g. wlan0 carrying both a
        # DHCP lease and a leftover AP-mode 192.168.4.1 alias), pick the
        # DHCP one: skip the AP subnet and prefer addresses whose
        # valid_lft is not "forever".
        try:
            out = subprocess.check_output(
                ["ip", "-4", "-o", "addr", "show", "dev", dev],
                text=True, timeout=2
            )
        except Exception:
            return ""
        fallback = ""
        for line in out.splitlines():
            parts = line.split()
            ip_str = ""
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    ip_str = parts[i + 1].split("/")[0]
                    break
            if not ip_str or ip_str.startswith("192.168.4."):
                continue
            if "valid_lft" in parts:
                idx = parts.index("valid_lft")
                if idx + 1 < len(parts) and parts[idx + 1] != "forever":
                    return ip_str
            if not fallback:
                fallback = ip_str
        return fallback

    wlan_ip = ip_of("wlan0")
    eth_ip = ip_of("eth0")

    _net_cache = {"ssid": ssid, "wlan_ip": wlan_ip, "eth_ip": eth_ip, "ts": now}
    return ssid, wlan_ip, eth_ip


def _default_route_iface_ip():
    """Return (iface, src_ip) for the current IPv4 default route, or ("", "").

    The src field tells us which IP the kernel uses as the source address
    for outbound traffic — that's the IP a phone on the same network can
    actually reach, which is what we want to display as the device IP.
    """
    try:
        out = subprocess.check_output(
            ["ip", "-4", "route", "show", "default"],
            text=True, timeout=2
        )
    except Exception:
        return "", ""
    for line in out.splitlines():
        parts = line.split()
        if not parts or parts[0] != "default":
            continue
        iface = ""
        src = ""
        for i, p in enumerate(parts):
            if p == "dev" and i + 1 < len(parts):
                iface = parts[i + 1]
            elif p == "src" and i + 1 < len(parts):
                src = parts[i + 1]
        if iface:
            return iface, src
    return "", ""


def _ap_is_active():
    """True when the setup-mode hotspot is currently running."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "hostapd"],
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def _primary_device_ip():
    """Pick the single IP address to display as 'the device IP'.

    Prefers the interface carrying the default route, because that's the
    one a phone on the same network can actually reach. Falls back to
    wlan0 then eth0 when there's no default route (e.g. ethernet-only
    deployments on an isolated pool-controller LAN).
    """
    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    default_iface, default_src = _default_route_iface_ip()
    if default_src:
        return default_src
    if default_iface == "wlan0":
        return wlan_ip
    if default_iface == "eth0":
        return eth_ip
    return wlan_ip or eth_ip or ""


def _get_wifi_ip_config():
    """Get current WiFi (wlan0) IPv4 configuration.

    WiFi IP is a property of the NetworkManager connection profile, not of
    the interface — so we look up the active profile bound to wlan0 and
    read ipv4.method / ipv4.addresses / ipv4.gateway from there.
    """
    config = {
        "mode": "dhcp",     # "dhcp" or "static"
        "ip": "",
        "netmask": "24",
        "gateway": "",
        "current_ip": "",
        "conn_name": "",
    }

    # Find the active WiFi profile name (the one we'll modify)
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] == "802-11-wireless" and parts[2] == "wlan0":
                config["conn_name"] = parts[0]
                break
    except Exception:
        pass

    # Current observed IP (what the kernel has on wlan0 right now).
    # Reuse the same picker logic as ip_of() — skip the AP subnet, prefer
    # the DHCP lease over any static alias.
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "dev", "wlan0"],
            text=True, timeout=2
        )
        for line in out.splitlines():
            parts = line.split()
            ip_cidr = ""
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    ip_cidr = parts[i + 1]
                    break
            if not ip_cidr:
                continue
            ip_only = ip_cidr.split("/")[0]
            if ip_only.startswith("192.168.4."):
                continue
            config["current_ip"] = ip_only
            break
    except Exception:
        pass

    # Authoritative configured method / address / gateway from the profile.
    # This is what the UI form should reflect, even if the current runtime
    # IP was obtained differently (e.g. the lease hasn't refreshed yet).
    if config["conn_name"]:
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "ipv4.method,ipv4.addresses,ipv4.gateway",
                 "con", "show", config["conn_name"]],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                key, _, val = line.partition(":")
                val = val.strip()
                if key == "ipv4.method":
                    config["mode"] = "static" if val == "manual" else "dhcp"
                elif key == "ipv4.addresses" and val and val != "--":
                    # nmcli can return "10.0.30.50/24" or a comma-separated list
                    first = val.split(",")[0].strip()
                    if "/" in first:
                        config["ip"], config["netmask"] = first.split("/", 1)
                    else:
                        config["ip"] = first
                elif key == "ipv4.gateway" and val and val != "--":
                    config["gateway"] = val
        except Exception:
            pass

    return config


def _get_ethernet_config():
    """Get current ethernet configuration."""
    config = {
        "mode": "dhcp",
        "ip": "",
        "netmask": "24",
        "gateway": "",
        "current_ip": "",
    }

    # Get current IP
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "dev", "eth0"],
            text=True, timeout=2
        ).strip()
        if out:
            parts = out.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    ip_cidr = parts[i + 1]
                    if "/" in ip_cidr:
                        config["current_ip"], config["netmask"] = ip_cidr.split("/")
                    else:
                        config["current_ip"] = ip_cidr
                    break
    except Exception:
        pass

    # Try to detect if using static or DHCP via NetworkManager
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "ipv4.method", "con", "show", "--active"],
            capture_output=True, text=True, timeout=5
        )
        if "manual" in result.stdout:
            config["mode"] = "static"
            config["ip"] = config["current_ip"]
    except Exception:
        pass

    # Try to get gateway
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default", "dev", "eth0"],
            capture_output=True, text=True, timeout=2
        )
        if result.stdout:
            parts = result.stdout.split()
            for i, p in enumerate(parts):
                if p == "via" and i + 1 < len(parts):
                    config["gateway"] = parts[i + 1]
                    break
    except Exception:
        pass

    return config
from ..langelier import lsi_from_values
from ..db import maintenance as mdb
from ..persist import load as load_persisted, save as save_persisted, actions_from_text, unique_names

main_bp = Blueprint("main", __name__)

# ----------------------------
# Helpers
# ----------------------------

def _get_actions():
    return current_app.config.get("MAINTENANCE_ACTIONS") or []

def _persisted():
    data = load_persisted(current_app.instance_path)
    # Keep app.config in sync with file
    current_app.config["MAINTENANCE_ACTIONS"] = data.get("maintenance_actions", [])
    current_app.config["HOST_NAMES"] = data.get("host_names", {})
    current_app.config["CONTROLLERS"] = data.get("controllers", [])
    current_app.config["MODBUS_PROFILE"] = data.get("modbus_profile", "ezetrol")
    current_app.config["DULCOPOOL_CHANNEL_MAP"] = data.get("dulcopool_channel_map", {})
    current_app.config["EZETROL_CHANNEL_MAP"] = data.get("ezetrol_channel_map", {})
    current_app.config["EZETROL_LAYOUT"] = data.get("ezetrol_layout", "CDAB")
    current_app.config["CHART_DOWNSAMPLE"] = data.get("chart_downsample", True)
    current_app.config["CHART_MAX_POINTS"] = data.get("chart_max_points", 5000)
    current_app.config["UPLOAD_INTERVAL_MINUTES"] = data.get("upload_interval_minutes", 10)
    current_app.config["BACKEND_URL"] = data.get("backend_url", "")
    current_app.config["BOOTSTRAP_SECRET"] = data.get("bootstrap_secret", "")
    # Remote sync settings
    current_app.config["REMOTE_SYNC_ENABLED"] = data.get("remote_sync_enabled", False)
    current_app.config["REMOTE_SYNC_URL"] = data.get("remote_sync_url", "https://modprojects.co.uk")
    current_app.config["REMOTE_API_KEY"] = data.get("remote_api_key", "")
    current_app.config["REMOTE_SYNC_SCHEDULE"] = data.get("remote_sync_schedule", "3days")
    current_app.config["REMOTE_SYNC_INTERVAL_HOURS"] = data.get("remote_sync_interval_hours", 72)
    current_app.config["LAST_REMOTE_SYNC_TS"] = data.get("last_remote_sync_ts", "")
    # Data retention settings
    current_app.config["DATA_RETENTION_ENABLED"] = data.get("data_retention_enabled", True)
    current_app.config["DATA_RETENTION_FULL_DAYS"] = data.get("data_retention_full_days", 30)
    current_app.config["DATA_RETENTION_HOURLY_DAYS"] = data.get("data_retention_hourly_days", 90)
    current_app.config["DATA_RETENTION_DAILY_DAYS"] = data.get("data_retention_daily_days", 365)
    current_app.config["STORAGE_THRESHOLD_PERCENT"] = data.get("storage_threshold_percent", 80)
    current_app.config["STORAGE_MAX_MB"] = data.get("storage_max_mb", 500)
    # Display settings
    current_app.config["SCREEN_ROTATION"] = data.get("screen_rotation", 0)
    return data

def _save_persisted(data):
    save_persisted(current_app.instance_path, data)
    current_app.config["MAINTENANCE_ACTIONS"] = data.get("maintenance_actions", [])
    current_app.config["HOST_NAMES"] = data.get("host_names", {})
    current_app.config["CONTROLLERS"] = data.get("controllers", [])
    current_app.config["MODBUS_PROFILE"] = data.get("modbus_profile", "ezetrol")
    current_app.config["DULCOPOOL_CHANNEL_MAP"] = data.get("dulcopool_channel_map", {})
    current_app.config["EZETROL_CHANNEL_MAP"] = data.get("ezetrol_channel_map", {})
    current_app.config["EZETROL_LAYOUT"] = data.get("ezetrol_layout", "CDAB")
    current_app.config["CHART_DOWNSAMPLE"] = data.get("chart_downsample", True)
    current_app.config["CHART_MAX_POINTS"] = data.get("chart_max_points", 5000)
    current_app.config["UPLOAD_INTERVAL_MINUTES"] = data.get("upload_interval_minutes", 10)
    current_app.config["BACKEND_URL"] = data.get("backend_url", "")
    current_app.config["BOOTSTRAP_SECRET"] = data.get("bootstrap_secret", "")
    # Remote sync settings
    current_app.config["REMOTE_SYNC_ENABLED"] = data.get("remote_sync_enabled", False)
    current_app.config["REMOTE_SYNC_URL"] = data.get("remote_sync_url", "https://modprojects.co.uk")
    current_app.config["REMOTE_API_KEY"] = data.get("remote_api_key", "")
    current_app.config["REMOTE_SYNC_SCHEDULE"] = data.get("remote_sync_schedule", "3days")
    current_app.config["REMOTE_SYNC_INTERVAL_HOURS"] = data.get("remote_sync_interval_hours", 72)
    current_app.config["LAST_REMOTE_SYNC_TS"] = data.get("last_remote_sync_ts", "")
    # Data retention settings
    current_app.config["DATA_RETENTION_ENABLED"] = data.get("data_retention_enabled", True)
    current_app.config["DATA_RETENTION_FULL_DAYS"] = data.get("data_retention_full_days", 30)
    current_app.config["DATA_RETENTION_HOURLY_DAYS"] = data.get("data_retention_hourly_days", 90)
    current_app.config["DATA_RETENTION_DAILY_DAYS"] = data.get("data_retention_daily_days", 365)
    current_app.config["STORAGE_THRESHOLD_PERCENT"] = data.get("storage_threshold_percent", 80)
    current_app.config["STORAGE_MAX_MB"] = data.get("storage_max_mb", 500)
    # Display settings
    current_app.config["SCREEN_ROTATION"] = data.get("screen_rotation", 0)

def _pool_db_hosts():
    """Get distinct hosts from recent database entries (optimized for large databases)"""
    db_path = current_app.config.get("POOL_DB_PATH", "")
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        # Use short timeout to avoid hanging
        con = sqlite3.connect(db_path, timeout=5)
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        table = "readings" if "readings" in tables else ("pool_readings" if "pool_readings" in tables else None)
        if not table:
            con.close()
            return []

        # OPTIMIZED: Only scan recent data (last 10000 rows) instead of entire table
        # This avoids full table scan on multi-GB databases
        rows = con.execute(f"""
            SELECT DISTINCT host
            FROM (
                SELECT host FROM {table}
                WHERE host IS NOT NULL AND host != ''
                ORDER BY rowid DESC
                LIMIT 10000
            )
            ORDER BY host
        """).fetchall()
        con.close()
        return [r["host"] for r in rows if r["host"]]
    except Exception as e:
        # Log error but don't crash
        import logging
        logging.warning(f"Could not fetch hosts from DB: {e}")
        return []

def _rebuild_tabs_from_hosts(hosts):
    data = _persisted()
    # Merge discovered hosts into controllers list (do not delete existing entries)
    controllers = list(data.get("controllers") or [])
    by_host = {c.get("host"): c for c in controllers if isinstance(c, dict) and c.get("host")}
    changed = False
    for h in hosts:
        if h not in by_host:
            by_host[h] = {
                "host": h,
                "name": data.get("host_names", {}).get(h, h),
                "enabled": True,
                "port": 502,
                "volume_l": None,
            }
            changed = True

    # Preserve ordering: existing controllers first, then any new ones appended
    ordered_hosts = [c.get("host") for c in controllers if c.get("host")] + [h for h in hosts if h not in {c.get("host") for c in controllers if c.get("host")}]
    new_controllers = [by_host[h] for h in ordered_hosts if h in by_host]
    data["controllers"] = new_controllers
    if changed:
        _save_persisted(data)

    # Apply enabled controllers to tabs
    enabled = [c for c in new_controllers if c.get("enabled")]
    host_names = {c["host"]: c.get("name") or c["host"] for c in enabled}
    host_to_name = unique_names([c["host"] for c in enabled], host_names)
    current_app.config["POOL_IPS"] = {name: host for host, name in host_to_name.items()}
    current_app.config["POOLS"] = list(current_app.config["POOL_IPS"].keys())


def _reload_config_from_persist():
    """Reload app config from persisted settings (after adding new controllers, etc.)."""
    data = _persisted()
    controllers = list(data.get("controllers") or [])
    enabled = [c for c in controllers if c.get("enabled")]
    hosts = [c["host"] for c in enabled]
    host_names = {c["host"]: c.get("name") or c["host"] for c in enabled}
    if hosts:
        host_to_name = unique_names(hosts, host_names)
        current_app.config["POOL_IPS"] = {name: host for host, name in host_to_name.items()}
        current_app.config["POOLS"] = list(current_app.config["POOL_IPS"].keys())
    else:
        current_app.config["POOL_IPS"] = {}
        current_app.config["POOLS"] = []


# Provide pools list and appearance settings to base.html
@main_bp.app_context_processor
def inject_pools():
    pools = current_app.config.get("POOLS") or []
    pool_ips = current_app.config.get("POOL_IPS") or {}

    # Load appearance settings for theme injection in base.html
    data = load_persisted(current_app.instance_path)

    return {
        "pools": pools,
        "pool_ips": pool_ips,
        "app_version": current_app.config.get("APP_VERSION", "PoolAIssistant v6.1.1"),
        # Appearance settings
        "appearance_theme": data.get("appearance_theme", "light"),
        "appearance_accent_color": data.get("appearance_accent_color", "blue"),
        "appearance_font_size": data.get("appearance_font_size", "medium"),
        "appearance_compact_mode": data.get("appearance_compact_mode", False),
        # Device name (used for hostname, AP name, etc.)
        "device_name": data.get("device_name", ""),
    }

@main_bp.route("/")
def home():
    from ..persist import load_settings
    settings = load_settings()

    # Check if first boot setup is needed
    if not settings.get("setup_wizard_completed", False):
        # Check if FIRST_BOOT marker exists or no controllers configured
        first_boot_marker = Path("/opt/PoolAIssistant/data/FIRST_BOOT")
        controllers = settings.get("controllers", [])
        if first_boot_marker.exists() or not controllers:
            return redirect(url_for("main.setup_wizard"))

    pools = current_app.config.get("POOLS") or []
    if pools:
        return redirect(url_for("main.pool_page", pool=pools[0]))
    return redirect(url_for("main.settings"))

@main_bp.route("/pool/<pool>")
def pool_page(pool: str):
    return render_template(
        "pool.html",
        pool=pool,
        active_tab=pool,
    )

@main_bp.route("/pool/<pool>/maintenance", methods=["GET", "POST"])
def maintenance_page(pool: str):
    # Maintenance logs now stored in pool_readings.sqlite3 for unified sync/backup
    db_path = current_app.config.get("POOL_DB_PATH", "pool_readings.sqlite3")

    # Use pool-specific actions if available, otherwise global actions
    data = _persisted()
    pool_actions_map = data.get("pool_actions", {})
    pool_specific_actions = pool_actions_map.get(pool, [])
    actions = pool_specific_actions if pool_specific_actions else _get_actions()
    lsi_result = None
    lsi_error = ""
    lsi_inputs = {
        "ph": "",
        "temperature_c": "",
        "calcium_hardness": "",
        "total_alkalinity": "",
        "tds": "1000",
    }

    if request.method == "POST":
        form_type = (request.form.get("form") or "").strip()
        if form_type == "lsi":
            try:
                def _f(key: str) -> float:
                    raw = (request.form.get(key) or "").strip()
                    if not raw:
                        raise ValueError(f"{key} is required")
                    return float(raw)

                lsi_inputs = {
                    "ph": request.form.get("ph", "").strip(),
                    "temperature_c": request.form.get("temperature_c", "").strip(),
                    "calcium_hardness": request.form.get("calcium_hardness", "").strip(),
                    "total_alkalinity": request.form.get("total_alkalinity", "").strip(),
                    "tds": request.form.get("tds", "1000").strip() or "1000",
                }
                ph_val = _f("ph")
                temp_val = _f("temperature_c")
                ca_val = _f("calcium_hardness")
                alk_val = _f("total_alkalinity")
                tds_val = float(request.form.get("tds", "1000"))

                lsi_result = lsi_from_values(
                    ph=ph_val,
                    temperature_c=temp_val,
                    calcium_hardness_mgL_as_CaCO3=ca_val,
                    total_alkalinity_mgL_as_CaCO3=alk_val,
                    tds_mgL=tds_val,
                )

                # Store LSI result in history
                try:
                    from ..db import lsi_history
                    source = request.form.get("source", "manual")
                    lsi_history.store_lsi_reading(
                        pool=pool,
                        lsi_value=lsi_result.get("lsi", 0),
                        ph=ph_val,
                        temperature_c=temp_val,
                        calcium_hardness=ca_val,
                        total_alkalinity=alk_val,
                        tds=tds_val,
                        ph_saturation=lsi_result.get("pH_saturation"),
                        source=source,
                        db_path=db_path
                    )
                except Exception as e:
                    # Don't fail the calculation if storage fails
                    current_app.logger.warning(f"Failed to store LSI history: {e}")

            except ValueError as e:
                lsi_error = str(e)
        else:
            action = (request.form.get("action") or "").strip()
            note = (request.form.get("note") or "").strip()
            if not action:
                flash("No action provided.")
                return redirect(url_for("main.maintenance_page", pool=pool))
            if action == "TDS":
                tds_val = (request.form.get("tds") or request.form.get("tds_value") or "").strip()
                if tds_val:
                    note = f"{tds_val} ppm" + (f" - {note}" if note else "")
                else:
                    flash("Please enter a TDS value.")
                    return redirect(url_for("main.maintenance_page", pool=pool))

            mdb.log_action(db_path, pool, action, note)
            flash(f"Logged: {action}")
            return redirect(url_for("main.maintenance_page", pool=pool))

    last_info = {}
    for a in actions:
        last_info[a] = mdb.last_entry(db_path, pool, a)

    return render_template(
        "maintenance.html",
        pool=pool,
        actions=actions,
        last_info=last_info,
        lsi_result=lsi_result,
        lsi_error=lsi_error,
        lsi_inputs=lsi_inputs,
        active_tab=pool
    )

@main_bp.route("/pool/<pool>/maintenance/logs")
def maintenance_logs_page(pool: str):
    # Maintenance logs now stored in pool_readings.sqlite3 for unified sync/backup
    db_path = current_app.config.get("POOL_DB_PATH", "pool_readings.sqlite3")
    rows = mdb.fetch_all(db_path, pool, limit=2000)
    return render_template("maintenance_logs.html", pool=pool, rows=rows, active_tab=pool)


@main_bp.route("/pool/<pool>/lsi/autofill")
def lsi_autofill(pool: str):
    """Get latest pH and temperature from controller sensors for LSI auto-fill."""
    db_path = current_app.config.get("POOL_DB_PATH", "pool_readings.sqlite3")

    result = {"ok": False, "ph": None, "temperature_c": None}

    try:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Get latest pH reading
            ph_row = conn.execute("""
                SELECT value FROM readings
                WHERE pool = ? AND point_label = 'pH_MeasuredValue'
                ORDER BY ts DESC LIMIT 1
            """, [pool]).fetchone()

            # Get latest temperature reading
            temp_row = conn.execute("""
                SELECT value FROM readings
                WHERE pool = ? AND point_label = 'Temp_MeasuredValue'
                ORDER BY ts DESC LIMIT 1
            """, [pool]).fetchone()

            if ph_row:
                result["ph"] = round(ph_row["value"], 2)
            if temp_row:
                result["temperature_c"] = round(temp_row["value"], 1)

            result["ok"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


@main_bp.route("/pool/<pool>/lsi/history")
def lsi_history_api(pool: str):
    """Get LSI history for a pool."""
    try:
        from ..db import lsi_history
        db_path = current_app.config.get("POOL_DB_PATH", "pool_readings.sqlite3")

        limit = request.args.get("limit", 50, type=int)
        since_days = request.args.get("days", 90, type=int)

        history = lsi_history.get_lsi_history(
            pool=pool,
            limit=limit,
            since_days=since_days,
            db_path=db_path
        )

        return {"ok": True, "history": history}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------
# Settings
# ----------------------------

@main_bp.route("/settings")
def settings():
    data = _persisted()

    # PERFORMANCE FIX: Only auto-discover hosts if explicitly requested via refresh button
    # This avoids slow DISTINCT query on every settings page load with large databases
    # Users can click "Refresh from DB" button instead

    controllers = data.get("controllers") or []
    actions_text = "\n".join(current_app.config.get("MAINTENANCE_ACTIONS") or [])
    pools = current_app.config.get("POOLS") or []

    system_info = {
        "POOL_DB_PATH": current_app.config.get("POOL_DB_PATH", ""),
        "MAINT_DB_PATH": current_app.config.get("MAINT_DB_PATH", ""),
        "POOLDASH_SETTINGS_PATH": current_app.config.get("POOLDASH_SETTINGS_PATH", ""),
        "SOFTWARE_VERSION": os.getenv("SOFTWARE_VERSION", ""),
        "UPDATE_CHANNEL": os.getenv("UPDATE_CHANNEL", "stable"),
        "MODBUS_PROFILE": current_app.config.get("MODBUS_PROFILE", "ezetrol"),
        "UPLOAD_INTERVAL_MINUTES": current_app.config.get("UPLOAD_INTERVAL_MINUTES", 10),
    }

    update_status_path = os.getenv("UPDATE_STATUS_PATH", "/opt/PoolAIssistant/data/update_status.json")
    update_status = {}
    if update_status_path and os.path.exists(update_status_path):
        try:
            with open(update_status_path, "r", encoding="utf-8") as f:
                update_status = json.load(f)
        except Exception:
            update_status = {}

    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    device_ip = _primary_device_ip()
    ap_active = _ap_is_active()

    # Advanced settings data (merged into protected section)
    storage_info = _get_storage_info()
    ethernet_config = _get_ethernet_config()
    wifi_ip_config = _get_wifi_ip_config()

    return render_template(
        "settings.html",
        active_tab="Settings",
        current_ssid=ssid,
        eth_ip=eth_ip,
        ethernet_config=ethernet_config,
        wifi_ip_config=wifi_ip_config,
        actions_text=actions_text,
        controllers=controllers,
        pools=pools,
        system_info=system_info,
        modbus_profile=current_app.config.get("MODBUS_PROFILE", "ezetrol"),
        dulcopool_channel_map=current_app.config.get("DULCOPOOL_CHANNEL_MAP", {}),
        ezetrol_channel_map=current_app.config.get("EZETROL_CHANNEL_MAP", {}),
        ezetrol_layout=current_app.config.get("EZETROL_LAYOUT", "CDAB"),
        chart_downsample=current_app.config.get("CHART_DOWNSAMPLE", True),
        upload_interval=current_app.config.get("UPLOAD_INTERVAL_MINUTES", 10),
        backend_url=current_app.config.get("BACKEND_URL", ""),
        bootstrap_secret=current_app.config.get("BOOTSTRAP_SECRET", ""),
        update_status=update_status,
        device_ip=device_ip,
        wlan_ip=wlan_ip,
        ap_active=ap_active,
        # Advanced settings (protected section)
        device_id=data.get("device_id", ""),
        device_alias=data.get("device_alias", ""),
        screen_rotation=data.get("screen_rotation", 0),
        chart_max_points=data.get("chart_max_points", 5000),
        remote_sync_enabled=data.get("remote_sync_enabled", False),
        remote_sync_url=data.get("remote_sync_url", "https://modprojects.co.uk"),
        remote_api_key=data.get("remote_api_key", ""),
        remote_sync_schedule=data.get("remote_sync_schedule", "3days"),
        remote_sync_interval_hours=data.get("remote_sync_interval_hours", 72),
        last_remote_sync_ts=data.get("last_remote_sync_ts", ""),
        data_retention_enabled=data.get("data_retention_enabled", True),
        data_retention_full_days=data.get("data_retention_full_days", 30),
        data_retention_hourly_days=data.get("data_retention_hourly_days", 90),
        data_retention_daily_days=data.get("data_retention_daily_days", 365),
        storage_threshold_percent=data.get("storage_threshold_percent", 80),
        storage_max_mb=data.get("storage_max_mb", 500),
        storage_info=storage_info,
        # AP settings
        ap_suffix=data.get("ap_suffix", ""),
        ap_password_enabled=data.get("ap_password_enabled", False),
        ap_password=data.get("ap_password", ""),
        ap_ssid_display="PoolAI" + (f" ({data.get('ap_suffix')})" if data.get("ap_suffix") else ""),
        # Device name (for unique hostname)
        device_name=data.get("device_name", ""),
        # RS485 devices
        rs485_devices=data.get("rs485_devices", []),
    )

@main_bp.route("/qr")
def qr_code():
    """Generate QR code for easy device access."""
    import qrcode
    import qrcode.image.svg

    # Get device info
    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    device_ip = _primary_device_ip()
    data = _persisted()
    device_id = data.get("device_id", "")

    # QR code points to smart connect page that will detect local vs cloud
    # Format: /connect?ip=<local_ip>&id=<device_id>
    if device_ip:
        url = f"http://{device_ip}/connect"
    else:
        url = "http://poolai.local/connect"

    # Generate SVG QR code
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=factory)

    # Convert to bytes
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)

    return Response(buf.getvalue(), mimetype="image/svg+xml")


@main_bp.route("/connect")
def smart_connect():
    """Smart connect landing page - detects local vs cloud and prompts for PWA install."""
    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    device_ip = _primary_device_ip()
    data = _persisted()
    device_id = data.get("device_id", "")
    backend_url = data.get("backend_url", "https://poolaissistant.modprojects.co.uk")

    local_url = f"http://{device_ip}" if device_ip else "http://poolai.local"
    cloud_url = f"{backend_url}/portal"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#4a90e2">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>PoolAIssistant</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 100%);
            color: white;
            font-family: system-ui, -apple-system, sans-serif;
            text-align: center;
            padding: 20px;
        }}
        .container {{
            max-width: 400px;
            width: 100%;
        }}
        .logo {{
            font-size: 32px;
            font-weight: 700;
            color: #4a90e2;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: #8892b0;
            font-size: 14px;
            margin-bottom: 32px;
        }}
        .status {{
            padding: 16px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            margin-bottom: 24px;
        }}
        .status-icon {{
            font-size: 48px;
            margin-bottom: 12px;
        }}
        .status-text {{
            font-size: 16px;
            color: #e6f2ff;
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 16px 24px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            margin-bottom: 12px;
            transition: transform 0.2s, opacity 0.2s;
        }}
        .btn:active {{ transform: scale(0.98); }}
        .btn--primary {{
            background: #4a90e2;
            color: white;
        }}
        .btn--secondary {{
            background: rgba(255,255,255,0.1);
            color: #e6f2ff;
            border: 1px solid rgba(255,255,255,0.2);
        }}
        .btn--install {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
        }}
        .divider {{
            display: flex;
            align-items: center;
            margin: 24px 0;
            color: #8892b0;
            font-size: 12px;
        }}
        .divider::before, .divider::after {{
            content: "";
            flex: 1;
            height: 1px;
            background: rgba(255,255,255,0.1);
        }}
        .divider span {{ padding: 0 12px; }}
        .pwa-section {{
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin-top: 24px;
        }}
        .pwa-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
            color: #10b981;
        }}
        .pwa-steps {{
            text-align: left;
            font-size: 14px;
            color: #8892b0;
            padding-left: 20px;
        }}
        .pwa-steps li {{ margin-bottom: 6px; }}
        .hidden {{ display: none; }}
        .checking {{ animation: pulse 1.5s infinite; }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">PoolAIssistant</div>
        <div class="subtitle">Pool Monitoring & Control</div>

        <div class="status" id="statusBox">
            <div class="status-icon checking">&#128260;</div>
            <div class="status-text">Checking connection...</div>
        </div>

        <div id="localSection" class="hidden">
            <a href="{local_url}" class="btn btn--primary" id="localBtn">
                Open Local Dashboard
            </a>
            <p style="font-size: 12px; color: #8892b0; margin-bottom: 16px;">
                Connected via local network
            </p>
        </div>

        <div id="cloudSection" class="hidden">
            <a href="{cloud_url}" class="btn btn--secondary">
                Open Cloud Portal
            </a>
            <p style="font-size: 12px; color: #8892b0; margin-bottom: 16px;">
                Access from anywhere
            </p>
        </div>

        <div class="divider"><span>or</span></div>

        <div class="pwa-section" id="pwaSection">
            <div class="pwa-title">&#128241; Install the App</div>
            <div id="pwaInstructions"></div>
            <button class="btn btn--install hidden" id="installBtn" onclick="installPWA()">
                Install PoolAIssistant
            </button>
        </div>
    </div>

    <script>
        const localUrl = "{local_url}";
        const cloudUrl = "{cloud_url}";
        let deferredPrompt = null;

        // Detect platform
        function getPlatform() {{
            const ua = navigator.userAgent;
            if (/iPhone|iPad|iPod/.test(ua)) return 'ios';
            if (/Android/.test(ua)) return 'android';
            return 'desktop';
        }}

        // Check if local device is reachable
        async function checkLocalAccess() {{
            const statusBox = document.getElementById('statusBox');
            const localSection = document.getElementById('localSection');
            const cloudSection = document.getElementById('cloudSection');

            try {{
                // Try to reach the local device with a short timeout
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 3000);

                const response = await fetch(localUrl + '/health', {{
                    method: 'GET',
                    mode: 'no-cors',
                    signal: controller.signal
                }});

                clearTimeout(timeout);

                // If we get here, local is reachable
                statusBox.innerHTML = '<div class="status-icon">&#9989;</div>' +
                    '<div class="status-text">Connected to local device</div>';
                localSection.classList.remove('hidden');
                cloudSection.classList.remove('hidden');

            }} catch (e) {{
                // Local not reachable, show cloud option
                statusBox.innerHTML = '<div class="status-icon">&#9729;&#65039;</div>' +
                    '<div class="status-text">Not on local network</div>';
                cloudSection.classList.remove('hidden');
                localSection.classList.add('hidden');
            }}
        }}

        // Setup PWA install
        function setupPWA() {{
            const platform = getPlatform();
            const instructions = document.getElementById('pwaInstructions');
            const installBtn = document.getElementById('installBtn');

            if (platform === 'ios') {{
                instructions.innerHTML = '<ol class="pwa-steps">' +
                    '<li>Tap the <strong>Share</strong> button &#9757;</li>' +
                    '<li>Scroll down and tap <strong>Add to Home Screen</strong></li>' +
                    '<li>Tap <strong>Add</strong> to install</li>' +
                '</ol>';
            }} else if (platform === 'android') {{
                instructions.innerHTML = '<ol class="pwa-steps">' +
                    '<li>Tap the <strong>&#8942; menu</strong> button</li>' +
                    '<li>Tap <strong>Install app</strong> or <strong>Add to Home Screen</strong></li>' +
                '</ol>';
            }} else {{
                instructions.innerHTML = '<p class="pwa-steps" style="padding-left: 0;">' +
                    'Visit this page on your phone to install the app for easy access.</p>';
            }}

            // Listen for PWA install prompt (Chrome/Edge on Android)
            window.addEventListener('beforeinstallprompt', (e) => {{
                e.preventDefault();
                deferredPrompt = e;
                installBtn.classList.remove('hidden');
                instructions.classList.add('hidden');
            }});
        }}

        function installPWA() {{
            if (deferredPrompt) {{
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((result) => {{
                    deferredPrompt = null;
                    if (result.outcome === 'accepted') {{
                        document.getElementById('pwaSection').innerHTML =
                            '<div class="pwa-title">&#9989; App Installed!</div>';
                    }}
                }});
            }}
        }}

        // Initialize
        checkLocalAccess();
        setupPWA();
    </script>
</body>
</html>'''
    return html


@main_bp.route("/qr/page")
def qr_page():
    """Full-page QR code display for easy scanning."""
    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    device_ip = _primary_device_ip()
    url = f"http://{device_ip}/connect" if device_ip else "http://poolai.local/connect"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PoolAIssistant - Connect</title>
    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            font-family: system-ui, -apple-system, sans-serif;
            text-align: center;
            padding: 20px;
        }}
        .qr-container {{
            background: white;
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}
        .qr-container img {{
            width: 250px;
            height: 250px;
        }}
        h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
            color: #64ffda;
        }}
        .url {{
            font-family: monospace;
            font-size: 18px;
            color: #64ffda;
            margin: 20px 0;
            padding: 10px 20px;
            background: rgba(100,255,218,0.1);
            border-radius: 8px;
            word-break: break-all;
        }}
        .hint {{
            color: #8892b0;
            font-size: 14px;
            margin-top: 10px;
        }}
        .back {{
            margin-top: 30px;
            color: #4a90e2;
            text-decoration: none;
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <h1>Scan to Connect</h1>
    <div class="qr-container">
        <img src="/qr" alt="QR Code">
    </div>
    <div class="url">{url}</div>
    <div class="hint">Scan with your phone camera to open PoolAIssistant</div>
    <a href="/" class="back">&larr; Back to Dashboard</a>
</body>
</html>'''
    return html

def _get_current_wifi_ssid():
    """Get the currently connected WiFi SSID using nmcli."""
    try:
        # Use nmcli to get the active WiFi connection name
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("yes:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


@main_bp.route("/settings/wifi/scan")
def scan_wifi():
    """Scan for available WiFi networks and return as JSON."""
    networks = []
    current_ssid = None
    try:
        # Get current SSID before disconnecting (to show it in results)
        current_ssid = _get_current_wifi_ssid()

        # First, ensure wlan0 is released from hostapd (AP mode)
        # Stop AP services and set interface to managed
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"], capture_output=True, timeout=5)
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], capture_output=True, timeout=5)
        subprocess.run(["sudo", "nmcli", "device", "set", "wlan0", "managed", "yes"], capture_output=True, timeout=5)
        import time
        time.sleep(1)  # Give NetworkManager time to take over

        # Disconnect from current network to allow proper scanning
        # NetworkManager doesn't scan properly while connected
        subprocess.run(["sudo", "nmcli", "device", "disconnect", "wlan0"], capture_output=True, timeout=10)
        time.sleep(2)  # Allow interface to settle after disconnect

        # Trigger a fresh scan
        subprocess.run(["sudo", "nmcli", "device", "wifi", "rescan"], capture_output=True, timeout=10)
        time.sleep(3)  # Allow scan to complete

        # Use nmcli to list networks (rescan already done above)
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            seen = set()
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 2:
                    ssid = parts[0].strip()
                    signal = parts[1].strip() if len(parts) > 1 else "0"
                    security = parts[2].strip() if len(parts) > 2 else ""
                    if ssid and ssid not in seen:
                        seen.add(ssid)
                        networks.append({
                            "ssid": ssid,
                            "signal": int(signal) if signal.isdigit() else 0,
                            "security": security,
                            "current": ssid == current_ssid,
                        })
            # Sort by signal strength (strongest first)
            networks.sort(key=lambda x: x["signal"], reverse=True)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    return {"networks": networks, "was_connected": current_ssid}


@main_bp.route("/settings/wifi", methods=["POST"])
def update_wifi():
    ssid = (request.form.get("ssid") or "").strip()
    psk = (request.form.get("psk") or "").strip()

    if not ssid:
        flash("Please select or enter a network name.")
        return redirect(url_for("main.settings"))

    # Password can be empty for open networks, but warn user
    if not psk:
        flash("Warning: Connecting without a password (open network).")

    try:
        # The update_wifi.sh script handles stopping AP services, disconnecting,
        # and connecting to the new network. Just ensure wlan0 is managed mode.
        subprocess.run(["sudo", "nmcli", "device", "set", "wlan0", "managed", "yes"], capture_output=True, timeout=5)

        result = subprocess.run(
            ["sudo", "/usr/local/bin/update_wifi.sh", ssid, psk],
            capture_output=True,
            text=True,
            timeout=120,  # Allow up to 2 minutes for connection attempts
        )
        # Invalidate network cache after WiFi change
        _invalidate_net_cache()

        if result.returncode == 0:
            # Check if output indicates success
            if "SUCCESS" in result.stdout:
                flash(f"Connected to '{ssid}' successfully!")
            else:
                flash(f"Connecting to '{ssid}'. The device may briefly disconnect.")
        else:
            # Connection failed
            if "FAILED" in result.stdout:
                flash(f"Failed to connect to '{ssid}'. Please check password and try again.")
            else:
                flash(f"WiFi update completed with warnings: {result.stderr or result.stdout}")
    except subprocess.TimeoutExpired:
        _invalidate_net_cache()
        flash(f"WiFi connection timed out. The AP should be available for recovery.")
    except subprocess.CalledProcessError as e:
        flash(f"Failed to update Wi-Fi: {e.stderr or e.stdout or e}")
    except FileNotFoundError:
        flash("update_wifi.sh not found. Make sure /usr/local/bin/update_wifi.sh exists and sudo is configured.")
    return redirect(url_for("main.settings") + "#wifi-section")


@main_bp.route("/settings/wifi/disconnect", methods=["POST"])
def disconnect_wifi():
    """Disconnect from current WiFi network."""
    try:
        # Get current SSID for the message
        current_ssid = _get_current_wifi_ssid()

        # Disconnect from WiFi
        result = subprocess.run(
            ["sudo", "nmcli", "device", "disconnect", "wlan0"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Invalidate network cache after disconnect
        _invalidate_net_cache()

        if result.returncode == 0:
            if current_ssid:
                flash(f"Disconnected from '{current_ssid}'.")
            else:
                flash("WiFi disconnected.")
        else:
            # Check if already disconnected
            if "not active" in result.stderr.lower() or "not connected" in result.stderr.lower():
                flash("WiFi is already disconnected.")
            else:
                flash(f"Failed to disconnect: {result.stderr or 'Unknown error'}")

    except subprocess.TimeoutExpired:
        _invalidate_net_cache()
        flash("Disconnect timed out.")
    except Exception as e:
        flash(f"Failed to disconnect WiFi: {e}")

    return redirect(url_for("main.settings") + "#wifi-section")


@main_bp.route("/settings/ethernet", methods=["POST"])
def update_ethernet():
    """Update ethernet interface configuration."""
    mode = (request.form.get("eth_mode") or "dhcp").strip().lower()
    ip = (request.form.get("eth_ip") or "").strip()
    netmask = (request.form.get("eth_netmask") or "24").strip()
    gateway = (request.form.get("eth_gateway") or "").strip()

    if mode not in ("dhcp", "static"):
        flash("Invalid mode. Use 'dhcp' or 'static'.")
        return redirect(url_for("main.settings") + "#ethernet-section")

    if mode == "static" and not ip:
        flash("Static mode requires an IP address.")
        return redirect(url_for("main.settings") + "#ethernet-section")

    # Validate IP format and range if provided
    if ip:
        import re
        ip_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(ip_pattern, ip)
        if not match:
            flash("Invalid IP address format.")
            return redirect(url_for("main.settings") + "#ethernet-section")

        # Validate each octet is 0-255
        octets = [int(g) for g in match.groups()]
        if any(o < 0 or o > 255 for o in octets):
            flash("Invalid IP address: octets must be 0-255.")
            return redirect(url_for("main.settings") + "#ethernet-section")

        # Warn about common problematic IPs
        if octets[0] == 0:
            flash("Invalid IP address: cannot start with 0.")
            return redirect(url_for("main.settings") + "#ethernet-section")
        if octets[0] == 127:
            flash("Invalid IP address: 127.x.x.x is loopback.")
            return redirect(url_for("main.settings") + "#ethernet-section")
        if octets == [255, 255, 255, 255]:
            flash("Invalid IP address: broadcast address.")
            return redirect(url_for("main.settings") + "#ethernet-section")

    # Validate gateway if provided
    if gateway:
        import re
        gw_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        gw_match = re.match(gw_pattern, gateway)
        if not gw_match:
            flash("Invalid gateway format.")
            return redirect(url_for("main.settings") + "#ethernet-section")
        gw_octets = [int(g) for g in gw_match.groups()]
        if any(o < 0 or o > 255 for o in gw_octets):
            flash("Invalid gateway: octets must be 0-255.")
            return redirect(url_for("main.settings") + "#ethernet-section")

    # Validate netmask (CIDR notation: 1-32)
    try:
        netmask_int = int(netmask)
        if netmask_int < 1 or netmask_int > 32:
            raise ValueError()
    except ValueError:
        flash("Invalid netmask. Use CIDR notation (1-32).")
        return redirect(url_for("main.settings") + "#ethernet-section")

    try:
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "update_ethernet.sh"
        if not script_path.exists():
            # Try /usr/local/bin as fallback
            script_path = Path("/usr/local/bin/update_ethernet.sh")

        if mode == "dhcp":
            cmd = ["sudo", str(script_path), "dhcp"]
        else:
            cmd = ["sudo", str(script_path), "static", ip, netmask]
            if gateway:
                cmd.append(gateway)

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Invalidate network cache after ethernet change
        _invalidate_net_cache()

        if mode == "dhcp":
            flash("Ethernet set to DHCP. IP address will be assigned automatically.")
        else:
            flash(f"Ethernet configured: {ip}/{netmask}" + (f" gateway {gateway}" if gateway else ""))
    except subprocess.CalledProcessError as e:
        _invalidate_net_cache()
        flash(f"Failed to update Ethernet: {e.stderr or e.stdout or e}")
    except subprocess.TimeoutExpired:
        _invalidate_net_cache()
        flash("Ethernet configuration timed out.")
    except FileNotFoundError:
        flash("update_ethernet.sh not found.")
    except Exception as e:
        flash(f"Ethernet configuration error: {e}")

    return redirect(url_for("main.settings") + "#ethernet-section")


@main_bp.route("/settings/wifi/ip", methods=["POST"])
def update_wifi_ip():
    """Set wlan0 to DHCP or a static IPv4 address.

    This edits the currently-active WiFi NM profile, not the interface,
    so the setting persists across reboots (and across re-associations
    with the same SSID). Warn the user in the UI: a wrong static config
    will leave the Pi unreachable until a touchscreen/console recovery.
    """
    import re

    mode = (request.form.get("wifi_mode") or "dhcp").strip().lower()
    ip = (request.form.get("wifi_ip") or "").strip()
    netmask = (request.form.get("wifi_netmask") or "24").strip()
    gateway = (request.form.get("wifi_gateway") or "").strip()

    if mode not in ("dhcp", "static"):
        flash("Invalid mode. Use 'dhcp' or 'static'.")
        return redirect(url_for("main.settings") + "?tab=connectivity")

    if mode == "static":
        if not ip or not gateway:
            flash("Static mode requires both IP and gateway.")
            return redirect(url_for("main.settings") + "?tab=connectivity")

        # Validate IP + gateway. Keep the rules in sync with the Ethernet
        # validation — same addressing conventions apply.
        ip_re = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
        for label, addr in (("IP", ip), ("gateway", gateway)):
            m = ip_re.match(addr)
            if not m:
                flash(f"Invalid {label} address format.")
                return redirect(url_for("main.settings") + "?tab=connectivity")
            octets = [int(g) for g in m.groups()]
            if any(o < 0 or o > 255 for o in octets):
                flash(f"Invalid {label}: octets must be 0-255.")
                return redirect(url_for("main.settings") + "?tab=connectivity")
            if octets[0] in (0, 127) or octets == [255, 255, 255, 255]:
                flash(f"Invalid {label}: reserved address.")
                return redirect(url_for("main.settings") + "?tab=connectivity")

    # Build command for the shell script
    if mode == "static":
        cmd = ["sudo", "/usr/local/bin/update_wifi_ip.sh", "static", ip, netmask, gateway]
    else:
        cmd = ["sudo", "/usr/local/bin/update_wifi_ip.sh", "dhcp"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        _invalidate_net_cache()
        if result.returncode == 0:
            if mode == "static":
                flash(f"WiFi set to static {ip}/{netmask} (gateway {gateway}). Reconnecting…")
            else:
                flash("WiFi set to DHCP. Reconnecting…")
        else:
            err = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
            flash(f"Failed to update WiFi IP: {err[-1]}")
    except subprocess.TimeoutExpired:
        _invalidate_net_cache()
        flash("WiFi IP change timed out. The device may briefly disconnect; check /settings after ~30 seconds.")
    except FileNotFoundError:
        flash("update_wifi_ip.sh not found on this Pi. Rerun ensure_dependencies.sh.")
    except Exception as e:
        flash(f"WiFi IP configuration error: {e}")

    return redirect(url_for("main.settings") + "?tab=connectivity")


@main_bp.route("/settings/network/reset", methods=["POST"])
def reset_network():
    """Emergency network reset - clears WiFi, resets ethernet to DHCP, forces AP mode."""
    def _do_reset():
        try:
            script_path = Path(__file__).resolve().parents[2] / "scripts" / "network_reset.sh"
            if not script_path.exists():
                script_path = Path("/usr/local/bin/network_reset.sh")

            subprocess.run(
                ["sudo", str(script_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass

    threading.Thread(target=_do_reset, name="pooldash_network_reset", daemon=True).start()
    flash("Network reset initiated. Connect to 'PoolAI' WiFi (open network, no password) to reconfigure.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/network/diagnostics")
def network_diagnostics():
    """Run network diagnostics and return results as JSON."""
    results = {
        "wifi": {"connected": False, "ssid": "", "signal": "", "ip": ""},
        "ethernet": {"connected": False, "ip": "", "mode": "unknown"},
        "gateway": {"reachable": False, "ip": ""},
        "dns": {"working": False, "server": ""},
        "internet": {"reachable": False},
        "ap_mode": {"active": False, "ssid": ""},
    }

    # WiFi status (use nmcli instead of iwgetid/iwconfig for broader compatibility)
    try:
        wifi_result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid,signal", "dev", "wifi"],
            capture_output=True, text=True, timeout=5
        )
        if wifi_result.returncode == 0:
            for line in wifi_result.stdout.strip().split("\n"):
                if line.startswith("yes:"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        results["wifi"]["connected"] = True
                        results["wifi"]["ssid"] = parts[1]
                        if len(parts) >= 3 and parts[2]:
                            results["wifi"]["signal"] = f"{parts[2]}%"
                    break
    except Exception:
        pass

    # Get IPs
    ssid, wlan_ip, eth_ip = _get_cached_network_info()
    results["wifi"]["ip"] = wlan_ip
    results["ethernet"]["ip"] = eth_ip
    results["ethernet"]["connected"] = bool(eth_ip)

    # Ethernet mode
    eth_config = _get_ethernet_config()
    results["ethernet"]["mode"] = eth_config.get("mode", "unknown")

    # Check gateway
    try:
        gw_result = subprocess.check_output(
            ["ip", "route", "show", "default"],
            text=True, timeout=2
        ).strip()
        if gw_result:
            parts = gw_result.split()
            for i, p in enumerate(parts):
                if p == "via" and i + 1 < len(parts):
                    gw_ip = parts[i + 1]
                    results["gateway"]["ip"] = gw_ip
                    # Ping gateway
                    ping_result = subprocess.run(
                        ["ping", "-c", "1", "-W", "2", gw_ip],
                        capture_output=True, timeout=5
                    )
                    results["gateway"]["reachable"] = ping_result.returncode == 0
                    break
    except Exception:
        pass

    # Check DNS
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.startswith("nameserver"):
                    dns_server = line.split()[1]
                    results["dns"]["server"] = dns_server
                    # Test DNS resolution
                    try:
                        socket.gethostbyname("google.com")
                        results["dns"]["working"] = True
                    except Exception:
                        pass
                    break
    except Exception:
        pass

    # Check internet connectivity
    try:
        ping_result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, timeout=5
        )
        results["internet"]["reachable"] = ping_result.returncode == 0
    except Exception:
        pass

    # Check if AP mode is active
    try:
        hostapd_status = subprocess.run(
            ["systemctl", "is-active", "hostapd"],
            capture_output=True, text=True, timeout=2
        )
        if hostapd_status.stdout.strip() == "active":
            results["ap_mode"]["active"] = True
            results["ap_mode"]["ssid"] = "PoolAI"
    except Exception:
        pass

    return results


@main_bp.route("/settings/reboot", methods=["POST"])
def reboot_device():
    def _do_reboot():
        try:
            subprocess.run(
                ["sudo", "/sbin/reboot"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            pass

    threading.Thread(target=_do_reboot, name="pooldash_reboot", daemon=True).start()
    flash("Reboot requested. The device will go offline briefly.")
    return redirect(url_for("main.settings"))

@main_bp.route("/settings/restart_logger", methods=["POST"])
def restart_logger():
    def _do_restart():
        try:
            subprocess.run(
                ["sudo", "/bin/systemctl", "restart", "poolaissistant_logger.service"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            pass

    threading.Thread(target=_do_restart, name="pooldash_restart_logger", daemon=True).start()
    flash("Logger restart requested.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/ssh/keys", methods=["POST"])
def manage_ssh_keys():
    """Add or restore SSH authorized_keys via web UI."""
    action = (request.form.get("action") or "").strip().lower()

    if action == "restore":
        # Restore from backup
        backup_path = "/opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup"
        auth_keys_path = "/home/poolai/.ssh/authorized_keys"

        try:
            # Check if backup exists
            if not os.path.exists(backup_path):
                flash("No SSH key backup found. Add a key first.")
                return redirect(url_for("main.settings"))

            # Ensure .ssh directory exists
            subprocess.run(
                ["sudo", "mkdir", "-p", "/home/poolai/.ssh"],
                check=True, capture_output=True, timeout=10
            )
            subprocess.run(
                ["sudo", "chmod", "700", "/home/poolai/.ssh"],
                check=True, capture_output=True, timeout=10
            )

            # Copy backup to authorized_keys
            subprocess.run(
                ["sudo", "cp", backup_path, auth_keys_path],
                check=True, capture_output=True, timeout=10
            )
            subprocess.run(
                ["sudo", "chmod", "600", auth_keys_path],
                check=True, capture_output=True, timeout=10
            )
            subprocess.run(
                ["sudo", "chown", "poolai:poolai", auth_keys_path],
                check=True, capture_output=True, timeout=10
            )

            flash("SSH keys restored from backup successfully!")
        except Exception as e:
            flash(f"Failed to restore SSH keys: {e}")

    elif action == "add":
        # Add a new SSH public key
        pubkey = (request.form.get("ssh_pubkey") or "").strip()
        if not pubkey:
            flash("Please enter an SSH public key.")
            return redirect(url_for("main.settings"))

        # Basic validation - should start with ssh-rsa, ssh-ed25519, etc.
        if not pubkey.startswith(("ssh-rsa", "ssh-ed25519", "ssh-dss", "ecdsa-sha2")):
            flash("Invalid SSH public key format. Key should start with ssh-rsa, ssh-ed25519, etc.")
            return redirect(url_for("main.settings"))

        try:
            auth_keys_path = "/home/poolai/.ssh/authorized_keys"
            backup_path = "/opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup"

            # Ensure directories exist
            subprocess.run(["sudo", "mkdir", "-p", "/home/poolai/.ssh"], check=True, capture_output=True, timeout=10)
            subprocess.run(["sudo", "mkdir", "-p", "/opt/PoolAIssistant/data/admin"], check=True, capture_output=True, timeout=10)

            # Append key to authorized_keys (create if doesn't exist)
            with subprocess.Popen(
                ["sudo", "tee", "-a", auth_keys_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            ) as proc:
                proc.communicate(input=(pubkey + "\n").encode(), timeout=10)

            # Fix permissions
            subprocess.run(["sudo", "chmod", "700", "/home/poolai/.ssh"], check=True, capture_output=True, timeout=10)
            subprocess.run(["sudo", "chmod", "600", auth_keys_path], check=True, capture_output=True, timeout=10)
            subprocess.run(["sudo", "chown", "-R", "poolai:poolai", "/home/poolai/.ssh"], check=True, capture_output=True, timeout=10)

            # Also backup the keys
            subprocess.run(["sudo", "cp", auth_keys_path, backup_path], check=True, capture_output=True, timeout=10)

            flash("SSH public key added successfully!")
        except Exception as e:
            flash(f"Failed to add SSH key: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/ap", methods=["POST"])
def manage_ap():
    """Start/stop Access Point or update AP settings."""
    action = (request.form.get("action") or "").strip().lower()

    # ap_control.sh is the single source of truth for AP start/stop.
    # Calling systemctl on hostapd/dnsmasq directly (the old behaviour)
    # didn't assign 192.168.4.1 to wlan0, didn't hand the interface off
    # from NetworkManager, and didn't clean up on stop — so the AP either
    # failed to serve DHCP or left ghost IPs behind when torn down.
    if action == "start":
        try:
            result = subprocess.run(
                ["sudo", "/usr/local/bin/ap_control.sh", "start"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                flash("Setup mode on. Connect your phone to the 'PoolAI' WiFi, then browse to 192.168.4.1.")
            else:
                flash(f"Failed to start setup mode: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}")
        except Exception as e:
            flash(f"Failed to start setup mode: {e}")

    elif action == "stop":
        try:
            result = subprocess.run(
                ["sudo", "/usr/local/bin/ap_control.sh", "stop"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                flash("Setup mode off. Reconnecting to WiFi...")
            else:
                flash(f"Failed to stop setup mode: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}")
            _invalidate_net_cache()
        except Exception as e:
            flash(f"Failed to stop setup mode: {e}")

    elif action == "update":
        ssid = (request.form.get("ap_ssid") or "PoolAI").strip()
        password = (request.form.get("ap_password") or "").strip()

        if len(password) < 8:
            flash("AP password must be at least 8 characters.")
            return redirect(url_for("main.settings"))

        try:
            # Update hostapd.conf
            hostapd_conf = f"""interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""
            with subprocess.Popen(
                ["sudo", "tee", "/etc/hostapd/hostapd.conf"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            ) as proc:
                proc.communicate(input=hostapd_conf.encode(), timeout=10)

            # Also save to ap_config.sh for the AP manager
            ap_config = f"""# Custom AP configuration
AP_SSID="{ssid}"
AP_PSK="{password}"
"""
            config_path = "/opt/PoolAIssistant/data/ap_config.sh"
            with subprocess.Popen(
                ["sudo", "tee", config_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            ) as proc:
                proc.communicate(input=ap_config.encode(), timeout=10)

            flash(f"AP settings updated: SSID={ssid}. Restart AP to apply.")
        except Exception as e:
            flash(f"Failed to update AP settings: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/ap/config", methods=["POST"])
def update_ap_settings():
    """Update AP settings from protected settings (suffix, password toggle)."""
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    # Get form values
    ap_suffix = (request.form.get("ap_suffix") or "").strip()[:20]  # Max 20 chars
    ap_password_enabled = request.form.get("ap_password_enabled") == "on"
    ap_password = (request.form.get("ap_password") or "").strip()

    # Validate password if enabled
    if ap_password_enabled and len(ap_password) < 8:
        flash("AP password must be at least 8 characters.")
        return redirect(url_for("main.settings"))

    # Build the SSID
    if ap_suffix:
        ap_ssid = f"PoolAI ({ap_suffix})"
    else:
        ap_ssid = "PoolAI"

    # Save to persist.py settings
    data["ap_suffix"] = ap_suffix
    data["ap_password_enabled"] = ap_password_enabled
    data["ap_password"] = ap_password
    _save_persisted(data)

    # Write to ap_config.sh for the AP manager service
    try:
        if ap_password_enabled:
            ap_config = f'''# PoolAIssistant AP Configuration (auto-generated)
AP_SSID="{ap_ssid}"
AP_PSK="{ap_password}"
'''
        else:
            # Open network (no password) - hostapd config will need different handling
            ap_config = f'''# PoolAIssistant AP Configuration (auto-generated)
AP_SSID="{ap_ssid}"
AP_PSK=""
AP_OPEN="true"
'''

        config_path = "/opt/PoolAIssistant/data/ap_config.sh"
        with subprocess.Popen(
            ["sudo", "tee", config_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        ) as proc:
            proc.communicate(input=ap_config.encode(), timeout=10)

        # If action is "apply", also restart AP services
        if action == "apply":
            subprocess.run(["sudo", "systemctl", "restart", "poolaissistant_ap_manager"], capture_output=True, timeout=30)
            flash(f"AP settings applied: {ap_ssid}. AP manager restarted.")
        else:
            flash(f"AP settings saved: {ap_ssid}. Restart AP to apply changes.")

    except Exception as e:
        flash(f"Failed to update AP configuration: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/wifi/radio", methods=["POST"])
def manage_wifi_radio():
    """Enable or disable WiFi radio."""
    action = (request.form.get("action") or "").strip().lower()

    try:
        if action == "enable":
            result = subprocess.run(
                ["nmcli", "radio", "wifi", "on"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                flash("WiFi radio enabled.")
            else:
                flash(f"Failed to enable WiFi: {result.stderr}")

        elif action == "disable":
            result = subprocess.run(
                ["nmcli", "radio", "wifi", "off"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                flash("WiFi radio disabled.")
            else:
                flash(f"Failed to disable WiFi: {result.stderr}")
    except Exception as e:
        flash(f"WiFi radio control failed: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/ssh", methods=["POST"])
def manage_ssh():
    """Enable/disable SSH service and regenerate host keys if missing."""
    action = (request.form.get("action") or "enable").strip().lower()

    if action == "enable":
        errors = []

        # Step 1: Generate host keys if missing
        try:
            keygen_result = subprocess.run(
                ["sudo", "ssh-keygen", "-A"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if keygen_result.returncode != 0:
                errors.append(f"Key generation warning: {keygen_result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            errors.append("Key generation timed out")
        except Exception as e:
            errors.append(f"Key generation error: {e}")

        # Step 2: Stop SSH first (to ensure clean restart with new keys)
        try:
            subprocess.run(
                ["sudo", "systemctl", "stop", "ssh"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass  # OK if it wasn't running

        # Step 3: Enable SSH service
        try:
            subprocess.run(
                ["sudo", "systemctl", "enable", "ssh"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as e:
            errors.append(f"Enable failed: {e}")

        # Step 4: Start SSH service
        try:
            start_result = subprocess.run(
                ["sudo", "systemctl", "start", "ssh"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if start_result.returncode != 0:
                errors.append(f"Start failed: {start_result.stderr.strip()}")
        except Exception as e:
            errors.append(f"Start error: {e}")

        # Step 5: Verify SSH is running
        try:
            status_result = subprocess.run(
                ["sudo", "systemctl", "is-active", "ssh"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ssh_active = status_result.stdout.strip() == "active"
        except Exception:
            ssh_active = False

        if ssh_active:
            flash("SSH enabled successfully. Connect to poolai@<this-pi-ip> with password: 12345678")
        elif errors:
            flash(f"SSH may have issues: {'; '.join(errors)}")
        else:
            flash("SSH enable attempted but status unclear. Try rebooting if connection fails.")

    elif action == "disable":
        try:
            subprocess.run(
                ["sudo", "systemctl", "stop", "ssh"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            subprocess.run(
                ["sudo", "systemctl", "disable", "ssh"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            flash("SSH disabled.")
        except Exception as e:
            flash(f"SSH disable failed: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/actions", methods=["POST"])
def update_actions():
    text = request.form.get("actions_text") or ""
    actions = actions_from_text(text)
    if not actions:
        flash("Please provide at least one action.")
        return redirect(url_for("main.settings"))

    data = _persisted()
    data["maintenance_actions"] = actions
    _save_persisted(data)
    flash("Maintenance actions updated.")
    return redirect(url_for("main.settings"))

@main_bp.route("/settings/hosts", methods=["POST"])
def update_hosts():
    # Controllers table uses indexed fields:
    #   c_host__0, c_name__0, c_enabled__0, c_port__0
    indices = set()
    for k in request.form.keys():
        if k.startswith("c_host__"):
            try:
                indices.add(int(k.split("__", 1)[1]))
            except Exception:
                pass

    controllers = []
    for i in sorted(indices):
        host = (request.form.get(f"c_host__{i}") or "").strip()
        name = (request.form.get(f"c_name__{i}") or host).strip() or host
        enabled = request.form.get(f"c_enabled__{i}") == "on"
        port_raw = (request.form.get(f"c_port__{i}") or "502").strip()
        volume_raw = (request.form.get(f"c_volume__{i}") or "").strip()
        if not host:
            continue
        try:
            port = int(port_raw)
        except Exception:
            port = 502
        volume_l = None
        if volume_raw:
            try:
                volume_l = float(volume_raw)
            except Exception:
                volume_l = None
        controllers.append({"host": host, "name": name, "enabled": enabled, "port": port, "volume_l": volume_l})

    data = _persisted()
    data["controllers"] = controllers
    _save_persisted(data)

    # Rebuild visible tabs from enabled controllers
    enabled_list = [c for c in controllers if c.get("enabled")]
    hosts = [c["host"] for c in enabled_list]
    host_names = {c["host"]: c.get("name") or c["host"] for c in enabled_list}
    if hosts:
        host_to_name = unique_names(hosts, host_names)
        current_app.config["POOL_IPS"] = {name: host for host, name in host_to_name.items()}
        current_app.config["POOLS"] = list(current_app.config["POOL_IPS"].keys())
    else:
        current_app.config["POOL_IPS"] = {}
        current_app.config["POOLS"] = []

    flash("Controllers updated.")
    return redirect(url_for("main.settings") + "#controllers-section")

@main_bp.route("/settings/refresh_hosts", methods=["POST"])
def refresh_hosts():
    # Use whatever hosts appear in the pool DB, and update tabs + saved mapping.
    hosts = _pool_db_hosts()
    if not hosts:
        flash("No Modbus hosts found in the readings DB yet. Try 'Scan Network' to discover controllers.")
        return redirect(url_for("main.settings"))
    _rebuild_tabs_from_hosts(hosts)
    flash(f"Updated tabs from readings DB ({len(hosts)} host(s)).")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/scan_network")
def scan_network():
    """
    Scan local network for Modbus controllers (port 502).
    Returns JSON with discovered devices.
    """
    import logging
    try:
        logging.info("Starting network scan for Modbus controllers...")
        result = scan_all_subnets_for_modbus(port=502, timeout_s=0.5, max_workers=50)
        logging.info(f"Network scan complete: {result['devices_found']} devices found")

        # Test each discovered device with actual Modbus connection
        verified_devices = []
        for device in result.get('devices', []):
            test_result = test_modbus_connection(device['ip'], device['port'], timeout_s=2.0)
            verified_devices.append({
                'ip': device['ip'],
                'port': device['port'],
                'modbus_ok': test_result['modbus_ok'],
                'error': test_result.get('error')
            })

        return {
            'success': True,
            'subnets_scanned': result.get('subnets_scanned', []),
            'devices_found': len(verified_devices),
            'devices': verified_devices
        }
    except Exception as e:
        logging.exception("Network scan failed")
        return {'success': False, 'error': str(e), 'devices': []}


@main_bp.route("/settings/add_discovered", methods=["POST"])
def add_discovered_controllers():
    """
    Add discovered controllers to the configuration.
    Expects JSON body with list of IPs to add.
    """
    try:
        data = request.get_json()
        ips_to_add = data.get('ips', [])
        if not ips_to_add:
            return {'success': False, 'error': 'No IPs provided'}

        # Load current settings
        settings = _persisted()
        controllers = list(settings.get("controllers") or [])
        existing_hosts = {c.get("host") for c in controllers if c.get("host")}

        added = 0
        for ip in ips_to_add:
            ip = ip.strip()
            if ip and ip not in existing_hosts:
                controllers.append({
                    "host": ip,
                    "name": f"Controller {ip.split('.')[-1]}",  # Use last octet as name
                    "enabled": True,
                    "port": 502,
                    "volume_l": None
                })
                existing_hosts.add(ip)
                added += 1

        if added > 0:
            settings["controllers"] = controllers
            _save_persisted(settings)
            _reload_config_from_persist()

        return {'success': True, 'added': added, 'total': len(controllers)}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@main_bp.route("/settings/export")
def export_data():
    """Export DB tables to CSV. Returns a ZIP with CSV files."""
    # Maintenance logs are now in pool_readings.sqlite3 (merged database)
    pool_db = current_app.config.get("POOL_DB_PATH", "")

    # Build the ZIP in-memory so the download always lands on the client device (head) and
    # we don't leave export artifacts on the Pi.
    zip_buf = BytesIO()

    def dump_sqlite(db_path: str, prefix: str):
        if not db_path or not os.path.exists(db_path):
            return
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        for t in tables:
            if t.startswith("sqlite_"):
                continue
            rows = con.execute(f"SELECT * FROM {t}").fetchall()
            # Write each table as a CSV entry inside the ZIP
            csv_name = f"{prefix}_{t}.csv"
            csv_buf = BytesIO()
            # csv needs a text stream
            import io
            text_stream = io.TextIOWrapper(csv_buf, encoding="utf-8", newline="")
            w = csv.writer(text_stream)
            if rows:
                w.writerow(rows[0].keys())
                for r in rows:
                    w.writerow([r[k] for k in r.keys()])
            else:
                cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})").fetchall()]
                w.writerow(cols)
            text_stream.flush()
            # rewind to read bytes
            csv_bytes = csv_buf.getvalue()
            z.writestr(csv_name, csv_bytes)
        con.close()

    import csv
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # All data (readings + maintenance_logs) is now in pool_readings.sqlite3
        dump_sqlite(pool_db, "pool")

    if zip_buf.getbuffer().nbytes == 0:
        flash("No databases found to export.")
        return redirect(url_for("main.settings"))

    zip_buf.seek(0)
    return send_file(
        zip_buf,
        as_attachment=True,
        download_name=f"poolaissistant_export_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        mimetype="application/zip",
    )

@main_bp.route("/settings/clear", methods=["POST"])
def clear_db():
    target = (request.form.get("target") or "").strip()
    if target not in {"maintenance", "readings"}:
        flash("Invalid clear target.")
        return redirect(url_for("main.settings"))

    if target == "maintenance":
        # Maintenance logs now stored in pool_readings.sqlite3
        db_path = current_app.config.get("POOL_DB_PATH", "pool_readings.sqlite3")
        try:
            con = sqlite3.connect(db_path)
            con.execute("DELETE FROM maintenance_logs")
            con.commit()
            con.close()
            flash("Maintenance log cleared.")
        except Exception as e:
            flash(f"Failed to clear maintenance DB: {e}")
    else:
        db_path = current_app.config.get("POOL_DB_PATH", "")
        if not db_path or not os.path.exists(db_path):
            flash("Pool readings DB not found.")
            return redirect(url_for("main.settings"))
        try:
            con = sqlite3.connect(db_path)
            con.execute("DELETE FROM readings")
            con.commit()
            con.close()
            flash("Readings DB cleared.")
        except Exception as e:
            flash(f"Failed to clear readings DB: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/clear_alarms", methods=["POST"])
def clear_alarms():
    """Clear all active alarms by setting their ended_ts to now."""
    db_path = current_app.config.get("POOL_DB_PATH", "")
    if not db_path or not os.path.exists(db_path):
        flash("Pool readings DB not found.")
        return redirect(url_for("main.settings"))

    try:
        con = sqlite3.connect(db_path, timeout=10)
        cursor = con.execute(
            "UPDATE alarm_events SET ended_ts = datetime('now') WHERE ended_ts IS NULL"
        )
        cleared = cursor.rowcount
        con.commit()
        con.close()
        flash(f"Cleared {cleared} active alarm(s). They will be re-detected if still present.")
    except Exception as e:
        flash(f"Failed to clear alarms: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/modbus_profile", methods=["POST"])
def update_modbus_profile():
    profile = (request.form.get("modbus_profile") or "").strip().lower()
    allowed = {"bayrol", "dulcopool", "ezetrol"}
    if profile not in allowed:
        flash("Invalid Modbus profile selection.")
        return redirect(url_for("main.settings"))

    data = _persisted()
    old_profile = data.get("modbus_profile", "ezetrol")
    data["modbus_profile"] = profile
    _save_persisted(data)

    # Auto-restart logger if profile actually changed
    if profile != old_profile:
        def _restart_logger():
            try:
                subprocess.run(
                    ["sudo", "/bin/systemctl", "restart", "poolaissistant_logger.service"],
                    timeout=30
                )
            except Exception:
                pass
        threading.Thread(target=_restart_logger, daemon=True).start()
        flash(f"Controller type changed to {profile.upper()}. Logger restarting...")
    else:
        flash(f"Controller type is already {profile.upper()}.")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/dulcopool_mapping", methods=["POST"])
def update_dulcopool_mapping():
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    if action == "reset":
        data["dulcopool_channel_map"] = {
            "ph": "E1",
            "chlorine": "E2",
            "orp": "E3",
            "temp": "E4",
        }
        _save_persisted(data)
        flash("DULCOPOOL mapping reset to defaults.")
        return redirect(url_for("main.settings"))

    def _pick(name: str) -> str:
        val = (request.form.get(name) or "").strip().upper()
        return val if val in {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"} else ""

    mapping = {
        "ph": _pick("map_ph"),
        "chlorine": _pick("map_chlorine"),
        "orp": _pick("map_orp"),
        "temp": _pick("map_temp"),
    }
    if not all(mapping.values()):
        flash("Select a valid channel for each metric.")
        return redirect(url_for("main.settings"))

    data["dulcopool_channel_map"] = mapping
    _save_persisted(data)
    flash("DULCOPOOL channel mapping updated. Restart logger to apply.")
    return redirect(url_for("main.settings"))

@main_bp.route("/settings/ezetrol_mapping", methods=["POST"])
def update_ezetrol_mapping():
    if request.form.get("action") == "reset":
        data = _persisted()
        data["ezetrol_channel_map"] = {
            "ch1": "Chlorine",
            "ch2": "pH",
            "ch3": "ORP",
            "ch4": "",
        }
        _save_persisted(data)
        flash("Ezetrol channel mapping reset to default.")
        return redirect(url_for("main.settings"))

    def _norm(val: str) -> str:
        v = (val or "").strip()
        return v if v in {"Chlorine", "pH", "ORP", "Ch4", ""} else ""

    data = _persisted()
    data["ezetrol_channel_map"] = {
        "ch1": _norm(request.form.get("ezetrol_ch1")),
        "ch2": _norm(request.form.get("ezetrol_ch2")),
        "ch3": _norm(request.form.get("ezetrol_ch3")),
        "ch4": _norm(request.form.get("ezetrol_ch4")),
    }
    _save_persisted(data)
    flash("Ezetrol channel mapping updated. Restart logger to apply.")
    return redirect(url_for("main.settings"))

@main_bp.route("/settings/chart_downsample", methods=["POST"])
def update_chart_downsample():
    data = _persisted()
    enabled = request.form.get("chart_downsample") == "on"
    data["chart_downsample"] = bool(enabled)
    _save_persisted(data)
    flash("Chart downsampling updated.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/ezetrol_layout", methods=["POST"])
def update_ezetrol_layout():
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    if action == "reset":
        data["ezetrol_layout"] = "CDAB"
        _save_persisted(data)
        flash("Ezetrol layout reset to default (CDAB).")
        return redirect(url_for("main.settings"))

    layout = (request.form.get("ezetrol_layout") or "").strip().upper()
    allowed = {"ABCD", "CDAB", "BADC", "DCBA"}
    if layout not in allowed:
        flash("Invalid Ezetrol layout selection.")
        return redirect(url_for("main.settings"))

    data["ezetrol_layout"] = layout
    _save_persisted(data)
    flash("Ezetrol layout updated. Restart logger to apply.")
    return redirect(url_for("main.settings"))


# ----------------------------
# RS485 Water Tester Settings
# ----------------------------

@main_bp.route("/settings/rs485", methods=["POST"])
def update_rs485_devices():
    """Update RS485 water tester device configuration."""
    # RS485 devices table uses indexed fields:
    #   rs485_port__0, rs485_name__0, rs485_enabled__0, rs485_baud__0, etc.
    indices = set()
    for k in request.form.keys():
        if k.startswith("rs485_port__") or k.startswith("rs485_name__"):
            try:
                indices.add(int(k.split("__", 1)[1]))
            except Exception:
                pass

    devices = []
    for i in sorted(indices):
        # Handle port selection (dropdown or custom)
        port_select = (request.form.get(f"rs485_port__{i}") or "").strip()
        port_custom = (request.form.get(f"rs485_port_custom__{i}") or "").strip()
        if port_select == "custom" and port_custom:
            port = port_custom
        elif port_select and port_select != "custom":
            port = port_select
        else:
            continue  # Skip entries without a valid port

        name = (request.form.get(f"rs485_name__{i}") or "Water Tester").strip()
        enabled = request.form.get(f"rs485_enabled__{i}") == "on"
        baud_raw = (request.form.get(f"rs485_baud__{i}") or "9600").strip()
        mode = (request.form.get(f"rs485_mode__{i}") or "standalone").strip()
        merged_pool = (request.form.get(f"rs485_merged_pool__{i}") or "").strip()

        try:
            baud = int(baud_raw)
        except Exception:
            baud = 9600

        if mode not in ("standalone", "merged"):
            mode = "standalone"

        # If mode is standalone, clear merged_pool
        if mode == "standalone":
            merged_pool = ""

        devices.append({
            "port": port,
            "baud": baud,
            "name": name,
            "unit_id": 1,  # Default Modbus unit ID
            "mode": mode,
            "merged_with_pool": merged_pool,
            "enabled": enabled,
        })

    data = _persisted()
    data["rs485_devices"] = devices
    _save_persisted(data)

    flash(f"RS485 devices updated ({len(devices)} device(s)). Restart RS485 logger to apply.")
    return redirect(url_for("main.settings") + "#rs485-section")


@main_bp.route("/settings/rs485/detect")
def detect_rs485_devices():
    """Detect available serial ports for RS485 devices."""
    ports = []

    # Try serial.tools.list_ports if available
    try:
        import serial.tools.list_ports
        for port_info in serial.tools.list_ports.comports():
            ports.append({
                "port": port_info.device,
                "description": port_info.description,
                "hwid": port_info.hwid,
            })
    except ImportError:
        # Fallback: list common serial device paths on Linux
        import glob
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/serial*"]:
            for path in glob.glob(pattern):
                ports.append({
                    "port": path,
                    "description": "",
                    "hwid": "",
                })

    return {"success": True, "ports": ports}


@main_bp.route("/settings/upload_interval", methods=["POST"])
def update_upload_interval():
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()
    allowed = {1, 3, 6, 12, 20, 30, 40, 60}

    if action == "reset":
        data["upload_interval_minutes"] = 10
        _save_persisted(data)
        flash("Upload interval reset to default (10 minutes).")
        return redirect(url_for("main.settings"))

    try:
        value = int(request.form.get("upload_interval") or "")
    except Exception:
        value = 0

    if value not in allowed:
        flash("Invalid upload interval selection.")
        return redirect(url_for("main.settings"))

    data["upload_interval_minutes"] = value
    _save_persisted(data)
    flash("Upload interval updated. Next sync will follow this schedule.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/backend_credentials", methods=["POST"])
def update_backend_credentials():
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    if action == "reset":
        data["backend_url"] = ""
        data["bootstrap_secret"] = ""
        _save_persisted(data)
        flash("Backend credentials cleared.")
        return redirect(url_for("main.settings"))

    backend_url = (request.form.get("backend_url") or "").strip()
    bootstrap_secret = (request.form.get("bootstrap_secret") or "").strip()

    if backend_url and not backend_url.startswith("http"):
        flash("Backend URL must start with http or https.")
        return redirect(url_for("main.settings"))

    data["backend_url"] = backend_url
    data["bootstrap_secret"] = bootstrap_secret
    _save_persisted(data)
    flash("Backend credentials saved. Restart sync service if needed.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/check_update", methods=["POST"])
def check_update():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "update_check.py"
    if not script_path.exists():
        flash("Update check script not found.")
        return redirect(url_for("main.system_page"))

    try:
        subprocess.run(
            ["python3", str(script_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        flash("Update check complete.")
    except subprocess.CalledProcessError as e:
        flash(f"Update check failed: {e.stderr or e.stdout or e}")
    except Exception as e:
        flash(f"Update check failed: {e}")
    return redirect(url_for("main.system_page"))


@main_bp.route("/settings/apply_update", methods=["POST"])
def apply_update():
    """Apply a downloaded update package."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "update_check.py"
    if not script_path.exists():
        flash("Update script not found.")
        return redirect(url_for("main.system_page"))

    try:
        result = subprocess.run(
            ["sudo", "python3", str(script_path), "--apply"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for extraction
        )
        if result.returncode == 0:
            flash("Update applied successfully! Restarting services...")
            # Restart services in background
            subprocess.Popen(
                ["sudo", "systemctl", "restart", "poolaissistant_ui", "poolaissistant_logger"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            flash(f"Update apply failed: {result.stderr or result.stdout}")
    except subprocess.TimeoutExpired:
        flash("Update apply timed out. Check logs.")
    except Exception as e:
        flash(f"Update apply failed: {e}")
    return redirect(url_for("main.system_page"))


@main_bp.route("/settings/update_timer_status")
def update_timer_status():
    """AJAX endpoint to check auto-update timer status."""
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "update_check.timer"],
            capture_output=True, text=True
        )
        enabled = result.returncode == 0

        result2 = subprocess.run(
            ["systemctl", "is-active", "update_check.timer"],
            capture_output=True, text=True
        )
        active = result2.returncode == 0

        return {"ok": True, "enabled": enabled, "active": active}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@main_bp.route("/settings/enable_update_timer", methods=["POST"])
def enable_update_timer():
    """Enable the auto-update timer."""
    try:
        app_dir = Path(__file__).resolve().parents[2]
        service_src = app_dir / "scripts" / "update_check.service"
        timer_src = app_dir / "scripts" / "update_check.timer"

        # Also check systemd subdirectory
        if not service_src.exists():
            service_src = app_dir / "scripts" / "systemd" / "update_check.service"
            timer_src = app_dir / "scripts" / "systemd" / "update_check.timer"

        if service_src.exists() and timer_src.exists():
            # Remount root filesystem as read-write (for read-only Pi setups)
            subprocess.run(
                ["sudo", "mount", "-o", "remount,rw", "/"],
                capture_output=True, text=True
            )
            try:
                # Copy service and timer files
                subprocess.run(
                    ["sudo", "cp", str(service_src), "/etc/systemd/system/"],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    ["sudo", "cp", str(timer_src), "/etc/systemd/system/"],
                    check=True, capture_output=True, text=True
                )
                # Reload, enable and start
                subprocess.run(
                    ["sudo", "systemctl", "daemon-reload"],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    ["sudo", "systemctl", "enable", "update_check.timer"],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    ["sudo", "systemctl", "start", "update_check.timer"],
                    check=True, capture_output=True, text=True
                )
                flash("Auto-update timer enabled successfully.")
            finally:
                # Remount root filesystem as read-only again
                subprocess.run(
                    ["sudo", "mount", "-o", "remount,ro", "/"],
                    capture_output=True, text=True
                )
        else:
            flash("Timer files not found. Update may be required.")
    except subprocess.CalledProcessError as e:
        flash(f"Failed to enable timer: {e.stderr or e}")
    except Exception as e:
        flash(f"Failed to enable timer: {e}")

    return redirect(url_for("main.system_page"))


# ----------------------------
# Advanced Settings (discreet page for remote sync & data management)
# ----------------------------

def _get_storage_info():
    """Get storage usage information for the data directory."""
    # Maintenance logs are now merged into pool_readings.sqlite3
    pool_db = current_app.config.get("POOL_DB_PATH", "")

    info = {
        "pool_db_size_mb": 0,
        "maint_db_size_mb": 0,  # Kept for backward compatibility, will be 0
        "total_db_size_mb": 0,
        "disk_free_mb": 0,
        "disk_total_mb": 0,
        "disk_used_percent": 0,
    }

    try:
        if pool_db and os.path.exists(pool_db):
            info["pool_db_size_mb"] = round(os.path.getsize(pool_db) / (1024 * 1024), 2)
        # Maintenance is now in pool_db, so total equals pool_db size
        info["total_db_size_mb"] = info["pool_db_size_mb"]

        # Get disk space for the data directory
        data_dir = os.path.dirname(pool_db) if pool_db else "/opt/PoolAIssistant/data"
        if os.path.exists(data_dir):
            import shutil
            total, used, free = shutil.disk_usage(data_dir)
            info["disk_total_mb"] = round(total / (1024 * 1024), 0)
            info["disk_free_mb"] = round(free / (1024 * 1024), 0)
            info["disk_used_percent"] = round((used / total) * 100, 1)
    except Exception:
        pass

    return info


def _get_external_storage_info():
    """Detect external storage devices (USB drives, SD cards)."""
    devices = []
    data_dir = "/opt/PoolAIssistant/data"
    current_storage = "internal"  # Default to internal SD card

    # Check if data dir is a symlink to external storage
    try:
        if os.path.islink(data_dir):
            target = os.readlink(data_dir)
            if "/mnt/" in target or "/media/" in target:
                current_storage = "external"
    except Exception:
        pass

    try:
        # Use lsblk to find removable/USB devices
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL,RM,HOTPLUG"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json as json_mod
            data = json_mod.loads(result.stdout)

            for device in data.get("blockdevices", []):
                # Skip loop devices, zram, and the main SD card (mmcblk0)
                name = device.get("name", "")
                if name.startswith("loop") or name.startswith("zram") or name == "mmcblk0":
                    continue

                # Check if it's removable or hotplug (USB)
                is_removable = device.get("rm") == "1" or device.get("rm") is True
                is_hotplug = device.get("hotplug") == "1" or device.get("hotplug") is True

                # Look at partitions
                children = device.get("children", [])
                if not children:
                    # No partitions, check the device itself
                    children = [device]

                for part in children:
                    if part.get("type") not in ("part", "disk"):
                        continue

                    mountpoint = part.get("mountpoint")
                    fstype = part.get("fstype")

                    # Skip if no filesystem
                    if not fstype:
                        continue

                    # Get device path
                    part_name = part.get("name", "")
                    dev_path = f"/dev/{part_name}"

                    # Get size and usage info
                    size_str = part.get("size", "0")
                    model = device.get("model", "").strip() or "External Storage"

                    # Get usage if mounted
                    used_percent = 0
                    free_bytes = 0
                    total_bytes = 0
                    if mountpoint:
                        try:
                            import shutil
                            total_bytes, used_bytes, free_bytes = shutil.disk_usage(mountpoint)
                            used_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
                        except Exception:
                            pass

                    # Check if this is the active data storage
                    is_active = False
                    if current_storage == "external" and mountpoint:
                        try:
                            data_target = os.readlink(data_dir)
                            if data_target.startswith(mountpoint):
                                is_active = True
                        except Exception:
                            pass

                    devices.append({
                        "device": dev_path,
                        "name": part_name,
                        "model": model,
                        "size": size_str,
                        "fstype": fstype,
                        "mountpoint": mountpoint,
                        "mounted": bool(mountpoint),
                        "used_percent": used_percent,
                        "free_gb": round(free_bytes / (1024**3), 2) if free_bytes else 0,
                        "total_gb": round(total_bytes / (1024**3), 2) if total_bytes else 0,
                        "is_removable": is_removable or is_hotplug,
                        "is_active": is_active,
                    })

    except Exception as e:
        pass

    return {
        "devices": devices,
        "current_storage": current_storage,
        "data_dir": data_dir,
        "is_symlink": os.path.islink(data_dir),
    }


@main_bp.route("/settings/external-storage")
def get_external_storage():
    """API endpoint to get external storage info."""
    info = _get_external_storage_info()
    return {"ok": True, **info}


@main_bp.route("/settings/external-storage/enable", methods=["POST"])
def enable_external_storage():
    """Enable external storage for data."""
    device = request.form.get("device", "").strip()
    if not device:
        flash("No device specified.", "error")
        return redirect(url_for("main.system_page"))

    # Validate device path to prevent injection
    if not device.startswith("/dev/") or ".." in device:
        flash("Invalid device path.", "error")
        return redirect(url_for("main.system_page"))

    try:
        # Run the USB data mount script with the device as argument
        script_path = "/opt/PoolAIssistant/app/scripts/usb_data_mount.sh"
        if os.path.exists(script_path):
            # Increased timeout to 180s for formatting/copying large data
            result = subprocess.run(
                ["sudo", script_path, device],
                capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0:
                flash("External storage enabled successfully. Services will restart.", "success")
                # Restart services to use new storage
                subprocess.run(["sudo", "systemctl", "restart", "poolaissistant_logger"], timeout=30)
                subprocess.run(["sudo", "systemctl", "restart", "poolaissistant_ui"], timeout=30)
            else:
                flash(f"Failed to enable external storage: {result.stderr}", "error")
        else:
            flash("External storage script not found.", "error")
    except subprocess.TimeoutExpired:
        flash("Operation timed out. The device may still be formatting. Check back shortly.", "warning")
    except Exception as e:
        flash(f"Error enabling external storage: {e}", "error")

    return redirect(url_for("main.system_page"))


@main_bp.route("/settings/external-storage/disable", methods=["POST"])
def disable_external_storage():
    """Disable external storage, revert to internal SD card."""
    data_dir = "/opt/PoolAIssistant/data"
    backup_dir = f"{data_dir}.sd_backup"

    try:
        # Check if currently using external storage
        if not os.path.islink(data_dir):
            flash("Already using internal storage.", "info")
            return redirect(url_for("main.settings"))

        # Stop services first
        subprocess.run(["sudo", "systemctl", "stop", "poolaissistant_logger"], timeout=30)
        subprocess.run(["sudo", "systemctl", "stop", "poolaissistant_ui"], timeout=30)

        # Remove symlink and restore SD backup
        subprocess.run(["sudo", "rm", data_dir], timeout=10)

        if os.path.exists(backup_dir):
            subprocess.run(["sudo", "mv", backup_dir, data_dir], timeout=30)
            flash("Reverted to internal storage (restored from backup).", "success")
        else:
            subprocess.run(["sudo", "mkdir", "-p", data_dir], timeout=10)
            subprocess.run(["sudo", "chown", "poolaissistant:poolaissistant", data_dir], timeout=10)
            flash("Reverted to internal storage (fresh directory).", "success")

        # Restart services
        subprocess.run(["sudo", "systemctl", "start", "poolaissistant_logger"], timeout=30)
        subprocess.run(["sudo", "systemctl", "start", "poolaissistant_ui"], timeout=30)

    except Exception as e:
        flash(f"Error disabling external storage: {e}", "error")
        # Try to restart services anyway
        subprocess.run(["sudo", "systemctl", "start", "poolaissistant_logger"], timeout=30)
        subprocess.run(["sudo", "systemctl", "start", "poolaissistant_ui"], timeout=30)

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced")
def advanced_settings():
    """Redirect to main settings (advanced settings now in protected section)."""
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/remote_sync", methods=["POST"])
def update_remote_sync():
    """Update remote sync settings."""
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    if action == "reset":
        data["remote_sync_enabled"] = False
        data["remote_sync_url"] = "https://modprojects.co.uk"
        data["remote_api_key"] = ""
        data["remote_sync_schedule"] = "3days"
        data["remote_sync_interval_hours"] = 72
        _save_persisted(data)
        flash("Remote sync settings reset to defaults.")
        return redirect(url_for("main.settings"))

    # Update settings
    data["remote_sync_enabled"] = request.form.get("remote_sync_enabled") == "on"
    data["remote_sync_url"] = (request.form.get("remote_sync_url") or "https://modprojects.co.uk").strip()
    data["remote_api_key"] = (request.form.get("remote_api_key") or "").strip()

    schedule = (request.form.get("remote_sync_schedule") or "3days").strip()
    if schedule not in ("daily", "3days", "weekly", "custom"):
        schedule = "3days"
    data["remote_sync_schedule"] = schedule

    # Set interval based on schedule
    schedule_hours = {"daily": 24, "3days": 72, "weekly": 168}
    if schedule == "custom":
        try:
            data["remote_sync_interval_hours"] = max(1, int(request.form.get("remote_sync_interval_hours") or 72))
        except ValueError:
            data["remote_sync_interval_hours"] = 72
    else:
        data["remote_sync_interval_hours"] = schedule_hours.get(schedule, 72)

    # Validate URL
    if data["remote_sync_enabled"] and data["remote_sync_url"]:
        if not data["remote_sync_url"].startswith("http"):
            flash("Remote sync URL must start with http or https.")
            return redirect(url_for("main.settings"))

    _save_persisted(data)
    flash("Remote sync settings updated.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/data_retention", methods=["POST"])
def update_data_retention():
    """Update data retention settings."""
    action = (request.form.get("action") or "").strip().lower()
    data = _persisted()

    if action == "reset":
        data["data_retention_enabled"] = True
        data["data_retention_full_days"] = 30
        data["data_retention_hourly_days"] = 90
        data["data_retention_daily_days"] = 365
        data["storage_threshold_percent"] = 80
        data["storage_max_mb"] = 500
        _save_persisted(data)
        flash("Data retention settings reset to defaults.")
        return redirect(url_for("main.settings"))

    # Update settings
    data["data_retention_enabled"] = request.form.get("data_retention_enabled") == "on"

    try:
        data["data_retention_full_days"] = max(1, int(request.form.get("data_retention_full_days") or 30))
    except ValueError:
        data["data_retention_full_days"] = 30

    try:
        data["data_retention_hourly_days"] = max(1, int(request.form.get("data_retention_hourly_days") or 90))
    except ValueError:
        data["data_retention_hourly_days"] = 90

    try:
        data["data_retention_daily_days"] = max(1, int(request.form.get("data_retention_daily_days") or 365))
    except ValueError:
        data["data_retention_daily_days"] = 365

    try:
        data["storage_threshold_percent"] = max(50, min(95, int(request.form.get("storage_threshold_percent") or 80)))
    except ValueError:
        data["storage_threshold_percent"] = 80

    try:
        data["storage_max_mb"] = max(100, int(request.form.get("storage_max_mb") or 500))
    except ValueError:
        data["storage_max_mb"] = 500

    _save_persisted(data)
    flash("Data retention settings updated.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/scheduled_reboot", methods=["POST"])
def update_scheduled_reboot():
    """Update scheduled reboot settings and configure the timer."""
    import re

    data = _persisted()

    # Get form values
    enabled = request.form.get("scheduled_reboot_enabled") == "on"
    reboot_time = (request.form.get("scheduled_reboot_time") or "04:00").strip()

    # Validate time format (HH:MM)
    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', reboot_time):
        reboot_time = "04:00"

    # Normalize to HH:MM
    parts = reboot_time.split(":")
    reboot_time = f"{int(parts[0]):02d}:{parts[1]}"

    # Save settings
    data["scheduled_reboot_enabled"] = enabled
    data["scheduled_reboot_time"] = reboot_time
    _save_persisted(data)

    # Configure the timer
    configure_script = "/opt/PoolAIssistant/app/scripts/configure_scheduled_reboot.sh"
    if os.path.exists(configure_script):
        try:
            subprocess.run(
                ["sudo", "bash", configure_script],
                capture_output=True,
                timeout=30
            )
            flash(f"Scheduled reboot {'enabled at ' + reboot_time if enabled else 'disabled'}.")
        except Exception as e:
            flash(f"Settings saved but timer configuration failed: {e}")
    else:
        flash("Settings saved. Timer will be configured on next boot.")

    return redirect(url_for("main.system_page"))


@main_bp.route("/settings/scheduled_reboot_status")
def scheduled_reboot_status():
    """AJAX endpoint to get scheduled reboot timer status."""
    try:
        # Check if timer is enabled
        result = subprocess.run(
            ["systemctl", "is-enabled", "poolaissistant_scheduled_reboot.timer"],
            capture_output=True, text=True, timeout=5
        )
        enabled = result.returncode == 0

        # Check if timer is active
        result = subprocess.run(
            ["systemctl", "is-active", "poolaissistant_scheduled_reboot.timer"],
            capture_output=True, text=True, timeout=5
        )
        active = result.returncode == 0

        # Get next trigger time
        next_trigger = ""
        if active:
            result = subprocess.run(
                ["systemctl", "list-timers", "poolaissistant_scheduled_reboot.timer", "--no-pager"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    # Parse the timer output to get next trigger
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) >= 3 and "poolaissistant" in line:
                            # Format: "Mon 2026-04-14 04:00:00 BST ..."
                            next_trigger = " ".join(parts[:3])
                            break

        return {"ok": True, "enabled": enabled, "active": active, "next_trigger": next_trigger}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@main_bp.route("/settings/advanced/device_identity", methods=["POST"])
def update_device_identity():
    """Update device alias with timestamp for server sync."""
    data = _persisted()
    new_alias = (request.form.get("device_alias") or "").strip()

    # Only update timestamp if alias actually changed
    if new_alias != data.get("device_alias", ""):
        data["device_alias"] = new_alias
        data["device_alias_updated_at"] = datetime.now().isoformat()
        _save_persisted(data)
        flash(f"Device alias updated to: {new_alias or '(none)'}")
    else:
        flash("No changes to device alias.")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/portal/generate_link_code", methods=["POST"])
def generate_portal_link_code():
    """Generate a link code for pairing this device with a portal account."""
    import requests

    data = _persisted()
    backend_url = data.get("backend_url", "")
    api_key = data.get("remote_api_key", "")

    if not backend_url or not api_key:
        return {"ok": False, "error": "Device not provisioned. API key missing."}, 400

    try:
        resp = requests.post(
            f"{backend_url}/api/portal/link-code.php",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        result = resp.json()
        return result
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Server connection failed: {str(e)}"}, 500
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@main_bp.route("/settings/advanced/screen_rotation", methods=["POST"])
def update_screen_rotation():
    """Update screen rotation and apply it."""
    data = _persisted()

    try:
        rotation = int(request.form.get("screen_rotation") or 0)
    except ValueError:
        rotation = 0

    if rotation not in (0, 90, 180, 270):
        flash("Invalid rotation value. Must be 0, 90, 180, or 270.")
        return redirect(url_for("main.settings"))

    data["screen_rotation"] = rotation
    _save_persisted(data)

    # Apply the rotation using the helper script
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "set_screen_rotation.sh"
    if script_path.exists():
        try:
            result = subprocess.run(
                ["sudo", str(script_path), str(rotation)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            flash(f"Screen rotation set to {rotation}°. Please reboot for changes to take effect.")
        except subprocess.CalledProcessError as e:
            flash(f"Rotation failed: {e.stderr or e.stdout or str(e)}")
        except Exception as e:
            flash(f"Rotation error: {str(e)}")
    else:
        flash(f"Script not found at {script_path}. Please reboot for changes to take effect.")

    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/chart_performance", methods=["POST"])
def update_chart_performance():
    """Update chart performance settings."""
    data = _persisted()

    try:
        max_points = int(request.form.get("chart_max_points") or 5000)
        # Clamp between 500 and 50000
        data["chart_max_points"] = max(500, min(50000, max_points))
    except ValueError:
        data["chart_max_points"] = 5000

    _save_persisted(data)
    flash(f"Chart limit set to {data['chart_max_points']} points.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/sync_now", methods=["POST"])
def trigger_remote_sync():
    """Manually trigger a remote sync using chunked uploads."""
    # Use chunk manager for large databases (safer, resumable)
    chunk_script = Path(__file__).resolve().parents[2] / "scripts" / "chunk_manager.py"
    legacy_script = Path(__file__).resolve().parents[2] / "scripts" / "remote_sync.py"

    # Prefer chunk manager if available
    if chunk_script.exists():
        script_path = chunk_script
        script_args = []  # chunk_manager handles everything
    elif legacy_script.exists():
        script_path = legacy_script
        script_args = ["--force"]
    else:
        flash("Sync script not found.")
        return redirect(url_for("main.settings"))

    def _do_sync():
        try:
            subprocess.run(
                ["python3", str(script_path)] + script_args,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes for chunked upload
            )
        except Exception:
            pass

    threading.Thread(target=_do_sync, name="pooldash_remote_sync", daemon=True).start()
    flash("Sync started in background. Data will be uploaded in compressed weekly chunks.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/advanced/cleanup_now", methods=["POST"])
def trigger_data_cleanup():
    """Manually trigger data cleanup/thinning."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "data_cleanup.py"
    if not script_path.exists():
        flash("Data cleanup script not found.")
        return redirect(url_for("main.settings"))

    def _do_cleanup():
        try:
            subprocess.run(
                ["python3", str(script_path), "--force"],
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception:
            pass

    threading.Thread(target=_do_cleanup, name="pooldash_data_cleanup", daemon=True).start()
    flash("Data cleanup started in background.")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/device_name", methods=["POST"])
def update_device_name():
    """Update device name and system hostname (PoolAI-{name})."""
    import re
    data = _persisted()

    new_name = (request.form.get("device_name") or "").strip()

    # Validate: alphanumeric and hyphens only, max 12 chars
    if new_name and not re.match(r'^[a-zA-Z0-9-]+$', new_name):
        flash("Device name can only contain letters, numbers, and hyphens.")
        return redirect(url_for("main.settings"))

    if len(new_name) > 12:
        new_name = new_name[:12]

    # Build hostname
    if new_name:
        new_hostname = f"PoolAI-{new_name}"
    else:
        # If empty, use last 2 chars of device_id or fallback
        device_id = data.get("device_id", "")
        if device_id and len(device_id) >= 2:
            suffix = device_id[-2:]
        else:
            import random
            import string
            suffix = ''.join(random.choices(string.hexdigits.lower()[:16], k=2))
        new_hostname = f"PoolAI-{suffix}"
        new_name = suffix

    # Save to settings
    data["device_name"] = new_name
    _save_persisted(data)

    # Apply hostname change
    try:
        # Set hostname
        subprocess.run(
            ["sudo", "hostnamectl", "set-hostname", new_hostname],
            check=True,
            capture_output=True,
            timeout=10,
        )

        # Update /etc/hostname
        with subprocess.Popen(
            ["sudo", "tee", "/etc/hostname"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        ) as proc:
            proc.communicate(input=(new_hostname + "\n").encode(), timeout=10)

        # Update /etc/hosts (replace 127.0.1.1 line)
        subprocess.run(
            ["sudo", "sed", "-i", f"s/127\\.0\\.1\\.1.*/127.0.1.1\\t{new_hostname}/", "/etc/hosts"],
            check=True,
            capture_output=True,
            timeout=10,
        )

        # Restart avahi-daemon for mDNS
        subprocess.run(
            ["sudo", "systemctl", "restart", "avahi-daemon"],
            capture_output=True,
            timeout=10,
        )

        # Also update AP configuration to use the same name
        ap_ssid = new_hostname
        ap_config_path = "/etc/poolaissistant/ap_config"
        try:
            ap_config_content = f'AP_SSID="{ap_ssid}"\nAP_PASSWORD=""\nAP_ENABLED=true\n'
            with subprocess.Popen(
                ["sudo", "tee", ap_config_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            ) as proc:
                proc.communicate(input=ap_config_content.encode(), timeout=10)
        except Exception:
            pass  # AP config update is optional

        flash(f"Device name set. Hostname is now {new_hostname} ({new_hostname}.local)")
    except subprocess.CalledProcessError as e:
        flash(f"Settings saved but hostname update failed: {e.stderr if hasattr(e, 'stderr') else e}")
    except Exception as e:
        flash(f"Settings saved but hostname update error: {e}")

    return redirect(url_for("main.settings"))


# ----------------------------
# Appearance Settings
# ----------------------------

@main_bp.route("/settings/appearance", methods=["POST"])
def update_appearance():
    """Update appearance settings (theme, accent color, font size, compact mode)."""
    data = _persisted()

    # Theme
    theme = (request.form.get("appearance_theme") or "light").strip()
    if theme in ("light", "dark", "system"):
        data["appearance_theme"] = theme

    # Accent color
    accent = (request.form.get("appearance_accent_color") or "blue").strip()
    if accent in ("blue", "green", "purple", "orange", "teal"):
        data["appearance_accent_color"] = accent

    # Font size
    font_size = (request.form.get("appearance_font_size") or "medium").strip()
    if font_size in ("small", "medium", "large"):
        data["appearance_font_size"] = font_size

    # Compact mode
    data["appearance_compact_mode"] = request.form.get("appearance_compact_mode") == "on"

    _save_persisted(data)
    flash("Appearance settings updated.")
    return redirect(url_for("main.settings"))


# ----------------------------
# Language Settings
# ----------------------------

@main_bp.route("/settings/language", methods=["POST"])
def update_language():
    """Update the UI language."""
    data = _persisted()
    new_lang = request.form.get("language", "en")

    # Validate language code
    supported = ("en", "fr", "es", "de", "it", "ru")
    if new_lang not in supported:
        new_lang = "en"

    data["language"] = new_lang
    _save_persisted(data)

    # No flash message - the UI change is immediately visible
    return redirect(url_for("main.settings"))


# ----------------------------
# Eco/Sleep Mode Settings
# ----------------------------

@main_bp.route("/settings/eco-mode", methods=["POST"])
def update_eco_mode():
    """Update eco/sleep mode settings."""
    data = _persisted()

    # Get form values
    eco_enabled = request.form.get("eco_mode_enabled") == "on"
    timeout = request.form.get("eco_timeout_minutes", "5")
    brightness = request.form.get("eco_brightness_percent", "10")
    wake_on_touch = request.form.get("eco_wake_on_touch") == "on"

    # Validate and save
    try:
        timeout_val = max(1, min(60, int(timeout)))
    except (ValueError, TypeError):
        timeout_val = 5

    try:
        brightness_val = max(0, min(100, int(brightness)))
    except (ValueError, TypeError):
        brightness_val = 10

    data["eco_mode_enabled"] = eco_enabled
    data["eco_timeout_minutes"] = timeout_val
    data["eco_brightness_percent"] = brightness_val
    data["eco_wake_on_touch"] = wake_on_touch

    _save_persisted(data)
    flash("Eco mode settings saved", "success")
    return redirect(url_for("main.system_page"))


# ----------------------------
# System Page
# ----------------------------

@main_bp.route("/system")
def system_page():
    """System settings page (updates, storage, screen, protected settings)."""
    data = _persisted()

    # Get update status
    update_status_path = os.getenv("UPDATE_STATUS_PATH", "/opt/PoolAIssistant/data/update_status.json")
    update_status = {}
    if update_status_path and os.path.exists(update_status_path):
        try:
            with open(update_status_path, "r", encoding="utf-8") as f:
                update_status = json.load(f)
        except Exception:
            update_status = {}

    # Get storage info
    storage_info = _get_storage_info()

    return render_template(
        "system.html",
        active_tab="Settings",
        app_version=current_app.config.get("APP_VERSION", "Unknown"),
        update_status=update_status,
        storage_info=storage_info,
        screen_rotation=data.get("screen_rotation", 0),
        # Protected settings
        device_id=data.get("device_id", ""),
        device_alias=data.get("device_alias", ""),
        modbus_profile=current_app.config.get("MODBUS_PROFILE", "ezetrol"),
        dulcopool_channel_map=current_app.config.get("DULCOPOOL_CHANNEL_MAP", {}),
        ezetrol_channel_map=current_app.config.get("EZETROL_CHANNEL_MAP", {}),
        ezetrol_layout=current_app.config.get("EZETROL_LAYOUT", "CDAB"),
        chart_max_points=data.get("chart_max_points", 5000),
        remote_sync_enabled=data.get("remote_sync_enabled", False),
        remote_sync_url=data.get("remote_sync_url", "https://modprojects.co.uk"),
        remote_api_key=data.get("remote_api_key", ""),
        remote_sync_schedule=data.get("remote_sync_schedule", "3days"),
        remote_sync_interval_hours=data.get("remote_sync_interval_hours", 72),
        last_remote_sync_ts=data.get("last_remote_sync_ts", ""),
        data_retention_enabled=data.get("data_retention_enabled", True),
        data_retention_full_days=data.get("data_retention_full_days", 30),
        data_retention_hourly_days=data.get("data_retention_hourly_days", 90),
        data_retention_daily_days=data.get("data_retention_daily_days", 365),
        storage_threshold_percent=data.get("storage_threshold_percent", 80),
        storage_max_mb=data.get("storage_max_mb", 500),
        ap_suffix=data.get("ap_suffix", ""),
        ap_password_enabled=data.get("ap_password_enabled", False),
        ap_password=data.get("ap_password", ""),
        ap_ssid_display="PoolAI" + (f" ({data.get('ap_suffix')})" if data.get("ap_suffix") else ""),
        backend_url=current_app.config.get("BACKEND_URL", ""),
        bootstrap_secret=current_app.config.get("BOOTSTRAP_SECRET", ""),
        # Scheduled reboot settings
        scheduled_reboot_enabled=data.get("scheduled_reboot_enabled", True),
        scheduled_reboot_time=data.get("scheduled_reboot_time", "04:00"),
        # Eco mode settings
        eco_mode_enabled=data.get("eco_mode_enabled", False),
        eco_timeout_minutes=data.get("eco_timeout_minutes", 5),
        eco_brightness_percent=data.get("eco_brightness_percent", 10),
        eco_wake_on_touch=data.get("eco_wake_on_touch", True),
        # Appearance settings
        appearance_theme=data.get("appearance_theme", "light"),
        appearance_accent_color=data.get("appearance_accent_color", "blue"),
        appearance_font_size=data.get("appearance_font_size", "medium"),
        appearance_compact_mode=data.get("appearance_compact_mode", False),
    )


# ----------------------------
# Portal Link Status (AJAX)
# ----------------------------

@main_bp.route("/settings/portal/status")
def portal_link_status():
    """AJAX endpoint to check if device is linked to a portal account."""
    import requests

    data = _persisted()
    backend_url = data.get("backend_url", "")
    api_key = data.get("remote_api_key", "")

    if not backend_url or not api_key:
        return {"linked": False, "online": False, "reason": "not_provisioned"}

    try:
        resp = requests.get(
            f"{backend_url}/api/portal/link-status.php",
            headers={"X-API-Key": api_key},
            timeout=5
        )
        result = resp.json()
        result["online"] = True  # We reached the server
        return result
    except requests.exceptions.RequestException:
        return {"linked": False, "online": False, "reason": "connection_failed"}
    except Exception as e:
        return {"linked": False, "online": False, "reason": str(e)}


@main_bp.route("/settings/portal/provision", methods=["POST"])
def trigger_provision():
    """Manually trigger device provisioning to get an API key."""
    import subprocess
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "auto_provision.py"

    if not script_path.exists():
        return {"ok": False, "error": "Provisioning script not found"}

    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            # Reload settings to get new API key
            data = _persisted()
            has_key = bool(data.get("remote_api_key"))
            return {"ok": True, "provisioned": has_key, "output": result.stdout}
        else:
            return {"ok": False, "error": result.stderr or "Provisioning failed", "output": result.stdout}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Provisioning timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@main_bp.route("/settings/hostname", methods=["POST"])
def update_hostname():
    """Update the system hostname."""
    import subprocess
    import re

    new_hostname = request.form.get("hostname", "").strip()

    # Validate hostname
    if not new_hostname:
        flash("Hostname cannot be empty")
        return redirect(url_for("main.settings"))

    # Hostname rules: lowercase, alphanumeric and hyphens, max 63 chars
    if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', new_hostname.lower()):
        flash("Invalid hostname. Use lowercase letters, numbers, and hyphens only.")
        return redirect(url_for("main.settings"))

    try:
        # Use hostnamectl to set hostname
        result = subprocess.run(
            ["sudo", "hostnamectl", "set-hostname", new_hostname.lower()],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # Also update /etc/hosts
            subprocess.run(
                ["sudo", "sed", "-i", f"s/127.0.1.1.*/127.0.1.1\\t{new_hostname.lower()}/", "/etc/hosts"],
                capture_output=True,
                timeout=5
            )
            flash(f"Hostname updated to {new_hostname.lower()}. Reboot for full effect.")
        else:
            flash(f"Failed to update hostname: {result.stderr}")

    except Exception as e:
        flash(f"Error updating hostname: {e}")

    return redirect(url_for("main.settings"))


@main_bp.route("/setup/set-hostname", methods=["POST"])
def setup_set_hostname():
    """Set hostname during setup wizard (JSON API)."""
    import subprocess
    import re

    data = request.get_json() or {}
    new_hostname = data.get("hostname", "").strip().lower()

    # Validate hostname
    if not new_hostname:
        return {"ok": False, "error": "Hostname cannot be empty"}

    if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', new_hostname):
        return {"ok": False, "error": "Invalid hostname. Use lowercase letters, numbers, and hyphens only."}

    try:
        # Use hostnamectl to set hostname
        result = subprocess.run(
            ["sudo", "hostnamectl", "set-hostname", new_hostname],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # Also update /etc/hosts
            subprocess.run(
                ["sudo", "sed", "-i", f"s/127.0.1.1.*/127.0.1.1\\t{new_hostname}/", "/etc/hosts"],
                capture_output=True,
                timeout=5
            )
            return {"ok": True, "hostname": new_hostname}
        else:
            return {"ok": False, "error": result.stderr or "Failed to set hostname"}

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------
# Per-Pool Quick Log Actions
# ----------------------------

@main_bp.route("/pool/<pool>/actions", methods=["GET", "POST"])
def pool_actions(pool: str):
    """Get or update per-pool quick log actions."""
    data = _persisted()
    pool_actions_map = data.get("pool_actions", {})

    if request.method == "GET":
        # Return current actions for this pool
        actions = pool_actions_map.get(pool, [])
        return {"pool": pool, "actions": actions}

    elif request.method == "POST":
        # Update actions for this pool
        content_type = request.content_type or ""
        if "application/json" in content_type:
            json_data = request.get_json()
            actions_text = json_data.get("actions_text", "") if json_data else ""
        else:
            actions_text = request.form.get("actions_text", "")

        actions = actions_from_text(actions_text)
        pool_actions_map[pool] = actions
        data["pool_actions"] = pool_actions_map
        _save_persisted(data)

        if "application/json" in content_type:
            return {"ok": True, "pool": pool, "actions": actions}
        else:
            flash(f"Actions updated for {pool}.")
            return redirect(url_for("main.maintenance_page", pool=pool))


@main_bp.route("/pool/<pool>/actions/edit", methods=["GET", "POST"])
def pool_actions_page(pool: str):
    """Page to edit per-pool quick log actions."""
    data = _persisted()
    pool_actions_map = data.get("pool_actions", {})
    global_actions = data.get("maintenance_actions", [])

    if request.method == "POST":
        actions_text = request.form.get("actions_text", "")
        actions = actions_from_text(actions_text)
        pool_actions_map[pool] = actions
        data["pool_actions"] = pool_actions_map
        _save_persisted(data)
        flash(f"Actions updated for {pool}.")
        return redirect(url_for("main.settings"))

    # GET - render page
    current_actions = pool_actions_map.get(pool, [])
    actions_text = "\n".join(current_actions)

    return render_template(
        "pool_actions.html",
        active_tab="Settings",
        pool_name=pool,
        actions_text=actions_text,
        global_actions=global_actions,
    )


# ----------------------------
# Network Configuration API
# ----------------------------

from ..utils.net import (
    check_ethernet_cable, ping_host, calculate_pi_ip,
    check_ip_available, get_current_eth0_config, friendly_error_message,
    scan_specific_subnet, test_modbus_connection
)


@main_bp.route("/settings/network/cable-status")
def network_cable_status():
    """Check if ethernet cable is physically connected."""
    result = check_ethernet_cable()
    return result


@main_bp.route("/settings/network/ping")
def network_ping():
    """Ping a host to check reachability."""
    host = request.args.get("host", "").strip()
    if not host:
        return {"error": "No host specified", "reachable": False}

    reachable, message = ping_host(host, timeout_s=2.0)
    return {
        "host": host,
        "reachable": reachable,
        "message": friendly_error_message(message) if not reachable else message
    }


@main_bp.route("/settings/network/calculate-pi-ip")
def network_calculate_pi_ip():
    """Calculate appropriate Pi IP for connecting to a controller."""
    controller_ip = request.args.get("controller", "").strip()
    if not controller_ip:
        return {"error": "No controller IP specified"}

    pi_ip, netmask, gateway = calculate_pi_ip(controller_ip)
    if not pi_ip:
        return {"error": gateway}  # gateway contains error message in this case

    return {
        "controller_ip": controller_ip,
        "pi_ip": pi_ip,
        "netmask": netmask,
        "gateway": gateway
    }


@main_bp.route("/settings/network/check-ip")
def network_check_ip():
    """Check if an IP address is available (not in use)."""
    ip = request.args.get("ip", "").strip()
    if not ip:
        return {"error": "No IP specified", "available": False}

    available, message = check_ip_available(ip)
    return {
        "ip": ip,
        "available": available,
        "message": message
    }


@main_bp.route("/settings/network/quick-configure", methods=["POST"])
def network_quick_configure():
    """Apply quick network configuration for controller connectivity."""
    try:
        data = request.get_json()
        controller_ip = data.get("controller_ip", "").strip()
        pi_ip = data.get("pi_ip", "").strip()
        netmask = data.get("netmask", "24").strip()
        gateway = data.get("gateway", "").strip()

        if not controller_ip or not pi_ip:
            return {"success": False, "error": "Missing required parameters"}

        # Backup current config
        backup = get_current_eth0_config()

        # Apply new configuration
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "update_ethernet.sh"
        if not script_path.exists():
            script_path = Path("/usr/local/bin/update_ethernet.sh")

        cmd = ["sudo", str(script_path), "static", pi_ip, netmask]
        if gateway:
            cmd.append(gateway)

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Verify connectivity to controller
        import time
        time.sleep(2)  # Wait for network to stabilize

        reachable, ping_msg = ping_host(controller_ip, timeout_s=3.0)

        if reachable:
            # Test Modbus connection
            modbus_result = test_modbus_connection(controller_ip, 502, timeout_s=3.0)
            if modbus_result.get("modbus_ok"):
                return {
                    "success": True,
                    "message": f"Connected to controller at {controller_ip}!\nPi configured as {pi_ip}/{netmask}",
                    "controller_reachable": True,
                    "modbus_ok": True
                }
            else:
                return {
                    "success": True,
                    "message": f"Pi configured as {pi_ip}/{netmask}\nController reachable but Modbus not responding (may need to power cycle controller)",
                    "controller_reachable": True,
                    "modbus_ok": False
                }
        else:
            return {
                "success": True,
                "message": f"Pi configured as {pi_ip}/{netmask}\nController not responding yet - check it's powered on",
                "controller_reachable": False,
                "modbus_ok": False,
                "warning": friendly_error_message(ping_msg)
            }

    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to apply configuration: {e.stderr or str(e)}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Configuration timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@main_bp.route("/settings/network/scan-subnet")
def network_scan_subnet():
    """Scan a specific subnet for Modbus controllers."""
    subnet = request.args.get("subnet", "").strip()
    if not subnet:
        return {"success": False, "error": "No subnet specified"}

    result = scan_specific_subnet(subnet, port=502, timeout_s=0.5, max_workers=50)

    # Verify each device with Modbus test
    if result.get("success") and result.get("devices"):
        verified = []
        for device in result["devices"]:
            test_result = test_modbus_connection(device["ip"], device["port"], timeout_s=2.0)
            verified.append({
                "ip": device["ip"],
                "port": device["port"],
                "modbus_ok": test_result.get("modbus_ok", False),
                "error": test_result.get("error")
            })
        result["devices"] = verified

    return result


# ----------------------------
# Network Setup Wizard
# ----------------------------

@main_bp.route("/network-wizard")
def network_wizard():
    """Display the network setup wizard."""
    data = _persisted()
    controllers = data.get("controllers", [])

    # Get current network status
    cable_status = check_ethernet_cable()
    eth_config = _get_ethernet_config()
    ssid, wlan_ip, eth_ip = _get_cached_network_info()

    return render_template(
        "network_wizard.html",
        active_tab="Settings",
        step=request.args.get("step", "welcome"),
        cable_status=cable_status,
        eth_config=eth_config,
        eth_ip=eth_ip,
        wlan_ip=wlan_ip,
        controllers=controllers,
        wizard_completed=data.get("network_wizard_completed", False),
        modbus_profile=data.get("modbus_profile", "ezetrol"),
    )


@main_bp.route("/network-wizard/check")
def network_wizard_check():
    """API: Check current network status for wizard."""
    cable_status = check_ethernet_cable()
    eth_config = _get_ethernet_config()
    ssid, wlan_ip, eth_ip = _get_cached_network_info()

    return {
        "cable": cable_status,
        "eth_ip": eth_ip,
        "wlan_ip": wlan_ip,
        "eth_config": eth_config
    }


@main_bp.route("/network-wizard/configure", methods=["POST"])
def network_wizard_configure():
    """API: Apply ethernet configuration from wizard."""
    # Same as quick-configure but returns wizard-specific responses
    return network_quick_configure()


@main_bp.route("/network-wizard/scan")
def network_wizard_scan():
    """API: Scan for controllers (multi-subnet if needed)."""
    # First scan current subnet
    cable_status = check_ethernet_cable()
    if not cable_status.get("connected"):
        return {
            "success": False,
            "error": "Ethernet cable not connected",
            "devices": []
        }

    results = []
    scanned_subnets = []

    # Get current subnet from eth0
    eth_config = _get_ethernet_config()
    current_ip = eth_config.get("current_ip", "")

    if current_ip:
        # Scan current subnet first
        parts = current_ip.split(".")
        if len(parts) == 4:
            current_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            scan_result = scan_specific_subnet(current_subnet)
            if scan_result.get("success"):
                for dev in scan_result.get("devices", []):
                    test_result = test_modbus_connection(dev["ip"], dev["port"])
                    results.append({
                        "ip": dev["ip"],
                        "port": dev["port"],
                        "subnet": current_subnet,
                        "modbus_ok": test_result.get("modbus_ok", False)
                    })
                scanned_subnets.append(current_subnet)

    # Scan common pool controller subnets
    common_subnets = ["192.168.200.0/24", "192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24"]
    for subnet in common_subnets:
        if subnet in scanned_subnets:
            continue

        scan_result = scan_specific_subnet(subnet)
        if scan_result.get("success"):
            for dev in scan_result.get("devices", []):
                test_result = test_modbus_connection(dev["ip"], dev["port"])
                results.append({
                    "ip": dev["ip"],
                    "port": dev["port"],
                    "subnet": subnet,
                    "modbus_ok": test_result.get("modbus_ok", False)
                })
            scanned_subnets.append(subnet)

    return {
        "success": True,
        "devices": results,
        "subnets_scanned": scanned_subnets
    }


@main_bp.route("/network-wizard/add", methods=["POST"])
def network_wizard_add():
    """API: Add controller from wizard."""
    try:
        data = request.get_json()
        ip = data.get("ip", "").strip()
        name = data.get("name", "").strip() or f"Controller {ip.split('.')[-1]}"
        volume = data.get("volume_l")

        if not ip:
            return {"success": False, "error": "No IP provided"}

        settings = _persisted()
        controllers = list(settings.get("controllers", []))

        # Check if already exists
        existing = [c for c in controllers if c.get("host") == ip]
        if existing:
            return {"success": False, "error": "Controller already configured"}

        controllers.append({
            "host": ip,
            "name": name,
            "enabled": True,
            "port": 502,
            "volume_l": float(volume) if volume else None
        })

        settings["controllers"] = controllers
        _save_persisted(settings)
        _reload_config_from_persist()

        return {"success": True, "added": 1, "controller": {"host": ip, "name": name}}

    except Exception as e:
        return {"success": False, "error": str(e)}


@main_bp.route("/network-wizard/complete", methods=["POST"])
def network_wizard_complete():
    """API: Mark wizard as completed."""
    settings = _persisted()
    settings["network_wizard_completed"] = True
    _save_persisted(settings)
    return {"success": True}


# ============================================================================
# SETUP WIZARD (First Boot)
# ============================================================================

@main_bp.route("/setup")
def setup_wizard():
    """First boot setup wizard."""
    from ..persist import load_settings
    settings = load_settings()

    # Allow forcing wizard via query param (for restart-wizard flow)
    force = request.args.get("force", "").lower() in ("1", "true", "yes")

    # If already completed and not forced, redirect to home
    if settings.get("setup_wizard_completed", False) and not force:
        pools = current_app.config.get("POOLS") or []
        if pools:
            return redirect(url_for("main.pool_page", pool=pools[0]))
        return redirect(url_for("main.settings"))

    return render_template(
        "setup_wizard.html",
        app_version=current_app.config.get("APP_VERSION", ""),
    )


@main_bp.route("/setup/scan-wifi")
def setup_scan_wifi():
    """Scan for WiFi networks for setup wizard."""
    networks = []
    try:
        # Trigger a scan
        _run_subprocess_safe(["sudo", "nmcli", "device", "wifi", "rescan"], timeout=10)
        time.sleep(2)

        # Get results
        success, stdout, stderr = _run_subprocess_safe(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            timeout=15
        )
        if success:
            seen = set()
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 2:
                    ssid = parts[0].strip()
                    signal = parts[1].strip() if len(parts) > 1 else "0"
                    if ssid and ssid not in seen:
                        seen.add(ssid)
                        networks.append({
                            "ssid": ssid,
                            "signal": int(signal) if signal.isdigit() else 0,
                        })
            networks.sort(key=lambda x: x["signal"], reverse=True)
    except Exception as e:
        current_app.logger.error(f"WiFi scan error: {e}")

    return {"networks": networks}


@main_bp.route("/setup/scan-controllers")
def setup_scan_controllers():
    """Scan for Modbus controllers for setup wizard."""
    controllers = []
    try:
        # Quick scan of common controller subnets
        found = scan_all_subnets_for_modbus(timeout=5)
        for device in found:
            controllers.append({
                "ip": device.get("ip"),
                "modbus_ok": device.get("modbus_ok", False),
            })
    except Exception as e:
        current_app.logger.error(f"Controller scan error: {e}")

    return {"controllers": controllers}


@main_bp.route("/setup/detect-storage")
def setup_detect_storage():
    """Detect USB storage for setup wizard."""
    try:
        # Check if USB is mounted at the expected location
        usb_mount = Path("/mnt/poolaissistant_usb")
        data_dir = Path("/opt/PoolAIssistant/data")

        # Check if data dir is a symlink to USB
        if data_dir.is_symlink():
            target = data_dir.resolve()
            if "poolaissistant_usb" in str(target):
                # USB is already in use
                try:
                    result = subprocess.run(
                        ["df", "-h", str(usb_mount)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    lines = result.stdout.strip().split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        device = parts[0] if len(parts) > 0 else "USB"
                        size = parts[1] if len(parts) > 1 else "-"
                        return {
                            "found": True,
                            "device": device,
                            "size": size,
                            "status": "Active",
                        }
                except Exception:
                    pass
                return {"found": True, "device": "USB", "size": "-", "status": "Active"}

        # Check for USB block devices
        result = subprocess.run(
            ["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT", "-J"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            import json

            data = json.loads(result.stdout)
            for device in data.get("blockdevices", []):
                # Look for USB drives (typically sda, sdb, etc.)
                name = device.get("name", "")
                if name.startswith("sd"):
                    size = device.get("size", "-")
                    mountpoint = device.get("mountpoint", "")
                    # Check children (partitions)
                    children = device.get("children", [])
                    for child in children:
                        if child.get("mountpoint"):
                            mountpoint = child.get("mountpoint")
                            size = child.get("size", size)
                            break
                    return {
                        "found": True,
                        "device": f"/dev/{name}",
                        "size": size,
                        "status": "Detected" if mountpoint else "Not mounted",
                    }

    except Exception as e:
        current_app.logger.error(f"Storage detection error: {e}")

    return {"found": False}


@main_bp.route("/settings/screen-rotation", methods=["POST"])
def settings_screen_rotation_json():
    """Apply screen rotation immediately (JSON endpoint for wizard)."""
    from ..persist import load_settings, save_settings

    data = request.get_json() or {}
    rotation = data.get("rotation", 0)

    try:
        rotation = int(rotation)
    except (ValueError, TypeError):
        rotation = 0

    if rotation not in (0, 90, 180, 270):
        return {"success": False, "error": "Invalid rotation value"}

    # Save to settings
    settings = load_settings()
    settings["screen_rotation"] = rotation
    save_settings(settings)

    # Apply rotation immediately via script
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "set_screen_rotation.sh"
    if script_path.exists():
        try:
            result = subprocess.run(
                ["sudo", str(script_path), str(rotation)],
                capture_output=True,
                text=True,
                timeout=30,  # Allow time for Wayland/X11 detection
            )
            if result.returncode == 0:
                return {"success": True, "rotation": rotation}
            else:
                return {"success": True, "rotation": rotation, "warning": "Script returned error but settings saved"}
        except Exception as e:
            current_app.logger.error(f"Screen rotation script error: {e}")
            return {"success": True, "rotation": rotation, "warning": "Could not run rotation script"}
    else:
        return {"success": True, "rotation": rotation, "warning": "Rotation script not found"}


@main_bp.route("/setup/connect-wifi", methods=["POST"])
def setup_connect_wifi():
    """Connect to WiFi during setup wizard (called before moving to next step)."""
    data = request.get_json() or {}
    ssid = data.get("ssid", "").strip()
    psk = data.get("psk", "")

    if not ssid:
        return {"success": False, "error": "No SSID provided"}

    # Validate SSID - reject newlines and extremely long values
    if "\n" in ssid or "\r" in ssid:
        return {"success": False, "error": "Invalid SSID: contains newlines"}
    if len(ssid) > 32:
        return {"success": False, "error": "Invalid SSID: too long (max 32 characters)"}

    # Validate PSK - reject newlines (special chars are OK for passwords)
    if psk and ("\n" in psk or "\r" in psk):
        return {"success": False, "error": "Invalid password: contains newlines"}

    # Check if update_wifi.sh exists
    script_paths = [
        Path("/usr/local/bin/update_wifi.sh"),
        Path(__file__).resolve().parents[2] / "scripts" / "update_wifi.sh",
    ]

    script_path = None
    for p in script_paths:
        if p.exists():
            script_path = p
            break

    if not script_path:
        return {"success": False, "error": "WiFi script not found"}

    try:
        # Run the WiFi connection script
        cmd = ["sudo", str(script_path), ssid]
        if psk:
            cmd.append(psk)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,  # WiFi connection can take time
        )

        _invalidate_net_cache()

        if result.returncode == 0:
            # Extract IP address from output if available
            ip_addr = None
            for line in result.stdout.split("\n"):
                if "IP address:" in line:
                    ip_addr = line.split(":")[-1].strip()
                    break

            return {
                "success": True,
                "ssid": ssid,
                "ip_address": ip_addr,
                "message": f"Connected to {ssid}",
            }
        else:
            error_msg = result.stderr or result.stdout or "Connection failed"
            # Check for common errors
            if "FAILED" in error_msg.upper() or result.returncode != 0:
                return {"success": False, "error": f"Failed to connect to {ssid}"}
            return {"success": False, "error": error_msg}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "WiFi connection timed out"}
    except Exception as e:
        current_app.logger.error(f"WiFi connection error: {e}")
        return {"success": False, "error": str(e)}


@main_bp.route("/setup/check-updates")
def setup_check_updates():
    """Check for software updates during setup wizard."""
    from ..persist import load_settings

    settings = load_settings()
    current_version = current_app.config.get("APP_VERSION", "0.0.0")
    backend_url = settings.get("backend_url", "https://poolaissistant.modprojects.co.uk")

    try:
        # Check for updates from server
        import requests

        response = requests.get(
            f"{backend_url}/api/check_updates.php",
            params={"version": current_version},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("update_available"):
                return {
                    "update_available": True,
                    "current_version": current_version,
                    "new_version": data.get("version", ""),
                    "description": data.get("description", ""),
                    "file_size": data.get("file_size", 0),
                }
            else:
                return {
                    "update_available": False,
                    "current_version": current_version,
                }
        else:
            return {"error": "Server returned an error", "current_version": current_version}

    except Exception as e:
        current_app.logger.error(f"Update check error: {e}")
        return {"error": "Could not connect to update server", "current_version": current_version}


@main_bp.route("/setup/apply-update", methods=["POST"])
def setup_apply_update():
    """Apply software update during setup wizard."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "update_check.py"

    if not script_path.exists():
        return {"success": False, "error": "Update script not found"}

    try:
        # First download the update
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return {"success": False, "error": "Failed to download update"}

        # Then apply it
        result = subprocess.run(
            ["sudo", "python3", str(script_path), "--apply"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            # Restart services in background
            subprocess.Popen(
                ["sudo", "systemctl", "restart", "poolaissistant_ui", "poolaissistant_logger"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"success": True}
        else:
            return {"success": False, "error": result.stderr or "Update failed"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Update timed out"}
    except Exception as e:
        current_app.logger.error(f"Update apply error: {e}")
        return {"success": False, "error": str(e)}


@main_bp.route("/setup/complete", methods=["POST"])
def setup_complete():
    """Complete the setup wizard and apply settings."""
    from ..persist import load_settings, save_settings

    data = request.get_json() or {}
    settings = load_settings()

    try:
        # Apply language
        if data.get("language"):
            settings["language"] = data["language"]

        # Apply theme
        if data.get("theme") in ("light", "dark"):
            settings["appearance_theme"] = data["theme"]

        # Apply screen rotation
        if "screen_rotation" in data:
            rotation = int(data["screen_rotation"])
            if rotation in (0, 90, 180, 270):
                settings["screen_rotation"] = rotation
                # Apply rotation via script
                script_path = Path(__file__).resolve().parents[2] / "scripts" / "set_screen_rotation.sh"
                if script_path.exists():
                    try:
                        subprocess.run(
                            ["sudo", str(script_path), str(rotation)],
                            capture_output=True,
                            timeout=10,
                        )
                    except Exception as e:
                        current_app.logger.error(f"Screen rotation error: {e}")

        # Apply WiFi if provided
        if data.get("wifi_ssid") and data.get("wifi_psk"):
            try:
                result = subprocess.run(
                    ["sudo", "/usr/local/bin/update_wifi.sh", data["wifi_ssid"], data["wifi_psk"]],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                _invalidate_net_cache()
            except Exception as e:
                current_app.logger.error(f"WiFi setup error: {e}")

        # Handle controllers - support both single and multiple controllers
        controllers_data = data.get("controllers", [])

        # Legacy support: if controller_ip is provided instead of controllers array
        if not controllers_data and data.get("controller_ip"):
            controllers_data = [{
                "ip": data["controller_ip"],
                "name": data.get("pool_name", "Main Pool")
            }]

        # Add controllers
        if controllers_data:
            if "controllers" not in settings:
                settings["controllers"] = []

            for ctrl in controllers_data:
                ctrl_ip = ctrl.get("ip", "").strip()
                ctrl_name = ctrl.get("name", "Pool").strip() or "Pool"

                if not ctrl_ip:
                    continue

                # Check if already exists
                existing = next((c for c in settings["controllers"] if c.get("host") == ctrl_ip), None)
                if not existing:
                    controller = {
                        "name": ctrl_name,
                        "host": ctrl_ip,
                        "port": 502,
                        "unit_id": 1,
                        "type": "ezetrol",
                        "enabled": True,
                    }
                    settings["controllers"].append(controller)
                else:
                    # Update name if controller already exists
                    existing["name"] = ctrl_name

        # Auto IP configuration if requested
        if data.get("auto_config_ip") and data.get("auto_pi_ip"):
            auto_pi_ip = data.get("auto_pi_ip")
            try:
                # Use the quick-configure logic to set up ethernet
                result = subprocess.run(
                    ["sudo", "/usr/local/bin/set_ethernet_ip.sh", auto_pi_ip, "24"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                current_app.logger.info(f"Auto IP config applied: {auto_pi_ip}")
                _invalidate_net_cache()
            except Exception as e:
                current_app.logger.error(f"Auto IP config error: {e}")
                # Don't fail the wizard for IP config issues

        # Mark wizard as completed
        settings["setup_wizard_completed"] = True

        # Remove FIRST_BOOT marker if exists
        first_boot_marker = Path("/opt/PoolAIssistant/data/FIRST_BOOT")
        if first_boot_marker.exists():
            try:
                first_boot_marker.unlink()
            except Exception:
                pass

        save_settings(settings)

        # Reload app config
        enabled_controllers = [c for c in settings.get("controllers", []) if c.get("enabled", True)]
        current_app.config["POOLS"] = [c["name"] for c in enabled_controllers]
        current_app.config["POOL_IPS"] = {c["name"]: c["host"] for c in enabled_controllers}

        return {"success": True}

    except Exception as e:
        current_app.logger.error(f"Setup complete error: {e}")
        return {"success": False, "error": str(e)}, 500


# ============================================================================
# FACTORY RESET
# ============================================================================

@main_bp.route("/settings/factory-reset", methods=["POST"])
def factory_reset():
    """Perform a factory reset - clears all settings and data."""
    from ..persist import DEFAULTS, save_settings

    # Verify password
    password = request.form.get("password", "")
    if password != "PoolAI":
        flash("Incorrect password for factory reset.")
        return redirect(url_for("main.settings"))

    try:
        # Reset settings to defaults
        reset_settings = dict(DEFAULTS)
        reset_settings["setup_wizard_completed"] = False
        reset_settings["controllers"] = []
        save_settings(reset_settings)

        # Create FIRST_BOOT marker to trigger setup wizard
        first_boot_marker = Path("/opt/PoolAIssistant/data/FIRST_BOOT")
        try:
            first_boot_marker.touch()
        except Exception:
            pass

        # Optionally clear databases (in background to avoid timeout)
        def _clear_databases():
            try:
                db_files = [
                    "/opt/PoolAIssistant/data/pool_readings.sqlite3",
                    "/opt/PoolAIssistant/data/maintenance_logs.sqlite3",
                    "/opt/PoolAIssistant/data/alarm_log.sqlite3",
                ]
                for db_file in db_files:
                    if os.path.exists(db_file):
                        os.remove(db_file)
            except Exception:
                pass

        reset_thread = threading.Thread(target=_clear_databases, daemon=True)
        reset_thread.start()

        # Invalidate caches
        _invalidate_net_cache()

        # Clear app config
        current_app.config["POOLS"] = []

        flash("Factory reset complete. Redirecting to setup wizard...")
        return redirect(url_for("main.setup_wizard"))

    except Exception as e:
        current_app.logger.error(f"Factory reset error: {e}")
        flash(f"Factory reset failed: {e}")
        return redirect(url_for("main.settings"))


# ============================================================================
# RESTART SETUP WIZARD
# ============================================================================

@main_bp.route("/settings/restart-wizard", methods=["POST"])
def restart_wizard():
    """Mark setup wizard to run again on next load."""
    from ..persist import load_settings, save_settings

    try:
        settings = load_settings()
        settings["setup_wizard_completed"] = False
        save_settings(settings)

        # Create FIRST_BOOT marker
        first_boot_marker = Path("/opt/PoolAIssistant/data/FIRST_BOOT")
        try:
            first_boot_marker.parent.mkdir(parents=True, exist_ok=True)
            first_boot_marker.touch()
        except Exception:
            pass

        flash("Setup wizard will run now.")
        return redirect(url_for("main.setup_wizard"))

    except Exception as e:
        current_app.logger.error(f"Restart wizard error: {e}")
        flash(f"Failed to restart wizard: {e}")
        return redirect(url_for("main.settings"))
