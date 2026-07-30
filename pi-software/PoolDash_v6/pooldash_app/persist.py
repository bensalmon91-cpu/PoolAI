import json
import os
import tempfile
import fcntl
from pathlib import Path
from typing import Dict, Any, List, Tuple
from contextlib import contextmanager


def _load_bootstrap_secret() -> str:
    """Load the server bootstrap secret without baking it into source.

    Precedence:
      1. POOLAI_BOOTSTRAP_SECRET env var
      2. /etc/poolai/bootstrap.secret  (file owned by root, mode 600)

    Returns empty string if neither is present; the caller is responsible
    for surfacing a clear error in that case. This keeps the shared secret
    out of git while preserving the "permanent, tamper-revert" behaviour -
    the loaded value is still re-applied at midnight, we just source it
    from the filesystem rather than from source code.
    """
    env_val = os.environ.get("POOLAI_BOOTSTRAP_SECRET", "").strip()
    if env_val:
        return env_val
    try:
        secret_path = Path("/etc/poolai/bootstrap.secret")
        if secret_path.is_file():
            return secret_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


_BOOTSTRAP_SECRET = _load_bootstrap_secret()

# File locking to prevent concurrent access corruption
@contextmanager
def file_lock(path: Path, timeout: float = 5.0):
    """Acquire an exclusive file lock for safe concurrent access."""
    lock_path = path.with_suffix(path.suffix + '.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

DEFAULTS = {
    "maintenance_actions": [
        "Backwash Filter 1","Backwash Filter 2","Change over pumps","Clean pump strainers",
        "Clean Dispenser strainers","Clean Cl Probe","Clean pH Probe","Clean ORP Probe",
        "Clean sensor bowl","Cleaned injectors","TDS","Custom note",
    ],
    # host(ip) -> friendly name
    "host_names": {},

    # Controller configuration (authoritative for what to show + what to poll)
    # List of dicts: {"host":"controller-1","name":"Pool 1","enabled":true,"port":502,"volume_l":12345}
    "controllers": [],
    "modbus_profile": "ezetrol",
    "dulcopool_channel_map": {
        "ph": "E1",
        "chlorine": "E2",
        "orp": "E3",
        "temp": "E4",
    },
    "ezetrol_channel_map": {
        "ch1": "Chlorine",
        "ch2": "pH",
        "ch3": "ORP",
        "ch4": "",
    },
    "ezetrol_layout": "CDAB",
    "ezetrol_layout_migrated": False,
    "chart_downsample": True,
    "chart_max_points": 5000,         # Limit data points in Plotly charts for UI performance
    # Server connection (PERMANENT - do not change)
    "backend_url": "https://poolaissistant.modprojects.co.uk",
    "bootstrap_secret": _BOOTSTRAP_SECRET,

    # Device identification (unique per Pi installation)
    "device_id": "",              # Auto-generated unique ID (UUID)
    "device_name": "",            # Hostname suffix (PoolAI-{name}.local)
    "device_alias": "",           # Human-friendly name (e.g., "Leisure Centre Pool")
    "device_alias_updated_at": "",  # ISO timestamp of last alias change (for sync)

    # Device API key (set by auto-provisioning, used by all cloud uploads).
    # The legacy remote_sync_* keys were retired 2026-06-12 — old settings
    # files may still contain them; they are ignored and dropped on save.
    "remote_api_key": "",

    # Data retention / thinning settings
    "data_retention_enabled": True,
    "data_retention_full_days": 30,      # keep full resolution for this many days
    "data_retention_hourly_days": 90,    # keep hourly averages for this many days
    "data_retention_daily_days": 365,    # keep daily averages for this many days
    "storage_threshold_percent": 80,     # start aggressive cleanup at this % of storage
    "storage_max_mb": 20000,             # far backstop for emergency cleanup; disk-% is the real guard (was 500, which purged GBs of history)

    # Display settings
    "screen_rotation": 0,                # 0, 90, 180, or 270 degrees
    "chromium_scale_factor": 1.0,         # kiosk browser device-scale-factor; compensates for
                                          # high-DPI panels (e.g. the 10" official touchscreen,
                                          # ~226dpi vs the 7" screen's ~132dpi) so touch targets
                                          # keep a comparable physical size. 1.0 = no scaling.

    # Access Point settings
    "ap_suffix": "",                     # Suffix in brackets, e.g., "Pool 1" -> "PoolAI (Pool 1)"
    "ap_password_enabled": False,        # False = open network (no password)
    "ap_password": "",                   # WPA2 password (min 8 chars if enabled)

    # Appearance settings
    "appearance_theme": "light",         # "light", "dark", "system"
    "appearance_accent_color": "blue",   # "blue", "green", "purple", "orange", "teal"
    "appearance_font_size": "medium",    # "small", "medium", "large"
    "appearance_compact_mode": False,

    # Language setting
    "language": "en",                    # "en", "fr", "es", "de", "it", "ru"

    # Per-pool quick log actions
    "pool_actions": {},                  # {"Pool Name": ["Action1", "Action2", ...]}

    # Network wizard
    "network_wizard_completed": False,   # True after wizard has been run

    # Setup wizard (first boot)
    "setup_wizard_completed": False,     # True after initial setup wizard has been completed

    # Cloud connection master switch (local-only mode). When False, every
    # telemetry script (heartbeat, snapshot, chunk/device/remote sync) exits
    # early and the unit runs as a standalone appliance. Software updates
    # are deliberately NOT gated - update_check.py is the delivery path for
    # fixes and must keep working.
    "cloud_enabled": True,

    # Modbus logging cadence. The logger re-reads these each cycle (no restart
    # needed). Default raised from 5s to 30s in v6.11.15 - pool chemistry moves
    # slowly, so 5s was needless SD-card I/O and wear. "Intensive monitoring"
    # is a temporary fault-finding window: while intensive_monitoring_until
    # (epoch seconds) is in the future the logger polls at the intensive
    # interval, then auto-reverts. 0 = off.
    "logger_poll_interval_seconds": 30,
    "intensive_poll_interval_seconds": 5,
    "intensive_monitoring_until": 0,

    # Cloud Upload Settings (Portal Data Sync)
    "cloud_upload_enabled": True,           # Enable automatic snapshot uploads to portal
    "cloud_upload_interval_minutes": 6,     # Upload interval (default 6 minutes)
    "cloud_upload_last_ts": "",             # ISO timestamp of last successful upload
    "cloud_upload_last_status": "",         # "ok", "warning", or "error"
    "cloud_upload_last_error": "",          # Last error message if any

    # Scheduled Daily Reboot
    "scheduled_reboot_enabled": True,        # Enable daily scheduled reboot (default: on)
    "scheduled_reboot_time": "04:00",        # Time for daily reboot in 24h format (HH:MM)

    # RS485 Water Tester devices
    # List of RS485 serial devices for water testing (TDS, conductivity, etc.)
    "rs485_devices": [
        # Example device configuration:
        # {
        #     "port": "/dev/ttyUSB0",        # Serial port path
        #     "baud": 9600,                   # Baud rate
        #     "name": "Water Tester",         # Device display name
        #     "unit_id": 1,                   # Modbus unit/slave ID
        #     "mode": "standalone",           # "standalone" or "merged"
        #     "merged_with_pool": "",         # Pool name when mode="merged"
        #     "enabled": True                 # Enable/disable this device
        # }
    ],
}

# =============================================================================
# HARDCODED SYSTEM URLS - These are PERMANENT and cannot be changed by users.
# They can ONLY be updated via software update (by changing this file).
# The system will revert to these values at midnight if tampered with.
# =============================================================================
SYSTEM_URLS = {
    "update_server": "https://poolaissistant.modprojects.co.uk",
    "backend_url": "https://poolaissistant.modprojects.co.uk",
    "bootstrap_secret": _BOOTSTRAP_SECRET,
}

def settings_path(app_instance_path: str) -> Path:
    # Allow override via env
    p = os.environ.get("POOLDASH_SETTINGS_PATH")
    if p:
        return Path(p).expanduser()
    return Path(app_instance_path) / "pooldash_settings.json"

def load(app_instance_path: str) -> Dict[str, Any]:
    path = settings_path(app_instance_path)
    if not path.exists():
        return dict(DEFAULTS)
    try:
        with file_lock(path):
            data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULTS)
        merged.update(data if isinstance(data, dict) else {})

        # normalize
        if not isinstance(merged.get("maintenance_actions"), list):
            merged["maintenance_actions"] = list(DEFAULTS["maintenance_actions"])
        if not isinstance(merged.get("host_names"), dict):
            merged["host_names"] = {}
        if not isinstance(merged.get("controllers"), list):
            merged["controllers"] = []
        if not isinstance(merged.get("modbus_profile"), str):
            merged["modbus_profile"] = DEFAULTS["modbus_profile"]
        if not isinstance(merged.get("dulcopool_channel_map"), dict):
            merged["dulcopool_channel_map"] = dict(DEFAULTS["dulcopool_channel_map"])
        if not isinstance(merged.get("ezetrol_channel_map"), dict):
            merged["ezetrol_channel_map"] = dict(DEFAULTS["ezetrol_channel_map"])
        if not isinstance(merged.get("ezetrol_layout"), str):
            merged["ezetrol_layout"] = DEFAULTS["ezetrol_layout"]
        if not isinstance(merged.get("ezetrol_layout_migrated"), bool):
            merged["ezetrol_layout_migrated"] = False
        if not isinstance(merged.get("chart_downsample"), bool):
            merged["chart_downsample"] = DEFAULTS["chart_downsample"]
        if not isinstance(merged.get("chart_max_points"), int):
            merged["chart_max_points"] = DEFAULTS["chart_max_points"]
        # upload_interval_minutes removed v6.11.22 - dead legacy key, superseded
        # by cloud_upload_interval_minutes; drop it from any settings file that
        # still carries it forward (same pattern as retired remote_sync_* keys).
        merged.pop("upload_interval_minutes", None)
        # Server connection - always use defaults (permanent values)
        merged["backend_url"] = DEFAULTS["backend_url"]
        merged["bootstrap_secret"] = DEFAULTS["bootstrap_secret"]

        # Device identification
        if not isinstance(merged.get("device_id"), str) or not merged.get("device_id"):
            import uuid
            merged["device_id"] = str(uuid.uuid4())
        if not isinstance(merged.get("device_name"), str):
            merged["device_name"] = ""
        if not isinstance(merged.get("device_alias"), str):
            merged["device_alias"] = ""
        if not isinstance(merged.get("device_alias_updated_at"), str):
            merged["device_alias_updated_at"] = ""

        # Device API key
        if not isinstance(merged.get("remote_api_key"), str):
            merged["remote_api_key"] = ""

        # Data retention settings
        if not isinstance(merged.get("data_retention_enabled"), bool):
            merged["data_retention_enabled"] = DEFAULTS["data_retention_enabled"]
        if not isinstance(merged.get("data_retention_full_days"), int):
            merged["data_retention_full_days"] = DEFAULTS["data_retention_full_days"]
        if not isinstance(merged.get("data_retention_hourly_days"), int):
            merged["data_retention_hourly_days"] = DEFAULTS["data_retention_hourly_days"]
        if not isinstance(merged.get("data_retention_daily_days"), int):
            merged["data_retention_daily_days"] = DEFAULTS["data_retention_daily_days"]
        if not isinstance(merged.get("storage_threshold_percent"), int):
            merged["storage_threshold_percent"] = DEFAULTS["storage_threshold_percent"]
        if not isinstance(merged.get("storage_max_mb"), int):
            merged["storage_max_mb"] = DEFAULTS["storage_max_mb"]

        # Display settings
        if merged.get("screen_rotation") not in (0, 90, 180, 270):
            merged["screen_rotation"] = DEFAULTS["screen_rotation"]
        scale = merged.get("chromium_scale_factor")
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not (0.5 <= scale <= 4):
            merged["chromium_scale_factor"] = DEFAULTS["chromium_scale_factor"]

        # Access Point settings
        if not isinstance(merged.get("ap_suffix"), str):
            merged["ap_suffix"] = DEFAULTS["ap_suffix"]
        if not isinstance(merged.get("ap_password_enabled"), bool):
            merged["ap_password_enabled"] = DEFAULTS["ap_password_enabled"]
        if not isinstance(merged.get("ap_password"), str):
            merged["ap_password"] = DEFAULTS["ap_password"]
        # Validate password length if enabled - disable password if too short
        if merged["ap_password_enabled"] and len(merged["ap_password"]) < 8:
            # WPA2 requires min 8 chars - disable password protection if invalid
            merged["ap_password_enabled"] = False
            merged["ap_password"] = ""

        # Appearance settings
        if merged.get("appearance_theme") not in ("light", "dark", "system"):
            merged["appearance_theme"] = DEFAULTS["appearance_theme"]
        if merged.get("appearance_accent_color") not in ("blue", "green", "purple", "orange", "teal"):
            merged["appearance_accent_color"] = DEFAULTS["appearance_accent_color"]
        if merged.get("appearance_font_size") not in ("small", "medium", "large"):
            merged["appearance_font_size"] = DEFAULTS["appearance_font_size"]
        if not isinstance(merged.get("appearance_compact_mode"), bool):
            merged["appearance_compact_mode"] = DEFAULTS["appearance_compact_mode"]

        # Language setting
        if merged.get("language") not in ("en", "fr", "es", "de", "it", "ru"):
            merged["language"] = DEFAULTS["language"]

        # Per-pool quick log actions
        if not isinstance(merged.get("pool_actions"), dict):
            merged["pool_actions"] = {}

        # Network wizard
        if not isinstance(merged.get("network_wizard_completed"), bool):
            merged["network_wizard_completed"] = DEFAULTS["network_wizard_completed"]

        # Setup wizard (first boot)
        if not isinstance(merged.get("setup_wizard_completed"), bool):
            merged["setup_wizard_completed"] = DEFAULTS["setup_wizard_completed"]

        # Cloud connection master switch
        if not isinstance(merged.get("cloud_enabled"), bool):
            merged["cloud_enabled"] = DEFAULTS["cloud_enabled"]

        # Modbus logging cadence
        if not isinstance(merged.get("logger_poll_interval_seconds"), int):
            merged["logger_poll_interval_seconds"] = DEFAULTS["logger_poll_interval_seconds"]
        merged["logger_poll_interval_seconds"] = max(5, min(3600, merged["logger_poll_interval_seconds"]))
        if not isinstance(merged.get("intensive_poll_interval_seconds"), int):
            merged["intensive_poll_interval_seconds"] = DEFAULTS["intensive_poll_interval_seconds"]
        merged["intensive_poll_interval_seconds"] = max(1, min(60, merged["intensive_poll_interval_seconds"]))
        if not isinstance(merged.get("intensive_monitoring_until"), (int, float)) or isinstance(merged.get("intensive_monitoring_until"), bool):
            merged["intensive_monitoring_until"] = 0

        # Cloud upload settings
        if not isinstance(merged.get("cloud_upload_enabled"), bool):
            merged["cloud_upload_enabled"] = DEFAULTS["cloud_upload_enabled"]
        if not isinstance(merged.get("cloud_upload_interval_minutes"), int):
            merged["cloud_upload_interval_minutes"] = DEFAULTS["cloud_upload_interval_minutes"]
        # Clamp interval to reasonable values (1-60 minutes)
        if merged["cloud_upload_interval_minutes"] < 1:
            merged["cloud_upload_interval_minutes"] = 1
        if merged["cloud_upload_interval_minutes"] > 60:
            merged["cloud_upload_interval_minutes"] = 60
        if not isinstance(merged.get("cloud_upload_last_ts"), str):
            merged["cloud_upload_last_ts"] = ""
        if not isinstance(merged.get("cloud_upload_last_status"), str):
            merged["cloud_upload_last_status"] = ""
        if not isinstance(merged.get("cloud_upload_last_error"), str):
            merged["cloud_upload_last_error"] = ""

        # Scheduled reboot settings
        if not isinstance(merged.get("scheduled_reboot_enabled"), bool):
            merged["scheduled_reboot_enabled"] = DEFAULTS["scheduled_reboot_enabled"]
        # validate_reboot_time() is the single authority for the HH:MM
        # format check - this used to re-implement the same regex inline,
        # which meant the two copies had to be kept in sync by hand.
        merged["scheduled_reboot_time"] = validate_reboot_time(
            merged.get("scheduled_reboot_time", DEFAULTS["scheduled_reboot_time"])
        )

        # RS485 devices - sanitize_rs485_devices() is the single authority
        # for this (see its docstring); this used to reimplement the same
        # loop inline.
        merged["rs485_devices"] = sanitize_rs485_devices(merged.get("rs485_devices"))

        # ALWAYS enforce system URLs from SYSTEM_URLS (cannot be overridden)
        merged["backend_url"] = SYSTEM_URLS["backend_url"]
        merged["bootstrap_secret"] = SYSTEM_URLS["bootstrap_secret"]

        # Back-compat: if controllers not present but host_names is, derive controllers from it.
        # This allows older installs to upgrade without breaking tabs.
        if not merged["controllers"] and merged.get("host_names"):
            merged["controllers"] = [
                {"host": host, "name": name, "enabled": True, "port": 502}
                for host, name in merged["host_names"].items()
                if host and name
            ]

        # sanitize each controller
        clean = []
        for c in merged.get("controllers") or []:
            if not isinstance(c, dict):
                continue
            host = (c.get("host") or "").strip()
            name = (c.get("name") or host).strip() or host
            if not host:
                continue
            enabled = bool(c.get("enabled", True))
            try:
                port = int(c.get("port", 502))
            except Exception:
                port = 502
            volume_l = None
            if c.get("volume_l") is not None:
                try:
                    volume_l = float(c.get("volume_l"))
                except Exception:
                    volume_l = None
            clean.append({"host": host, "name": name, "enabled": enabled, "port": port, "volume_l": volume_l})
        merged["controllers"] = clean

        # Keep host_names in sync (used in a couple places)
        merged["host_names"] = {c["host"]: c["name"] for c in merged["controllers"]}

        # One-time migration: shift ABCD default to CDAB for Ezetrol only
        if (
            merged.get("modbus_profile") == "ezetrol"
            and merged.get("ezetrol_layout") == "ABCD"
            and not merged.get("ezetrol_layout_migrated")
        ):
            merged["ezetrol_layout"] = "CDAB"
            merged["ezetrol_layout_migrated"] = True
            try:
                save(app_instance_path, merged)
            except Exception:
                pass

        return merged
    except Exception:
        # If file is corrupt, fall back to defaults but keep file untouched
        return dict(DEFAULTS)

def save(app_instance_path: str, data: Dict[str, Any]) -> Path:
    path = settings_path(app_instance_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # only persist known keys
    controllers = data.get("controllers") or []
    if not isinstance(controllers, list):
        controllers = []
    # sanitize controller list before writing
    clean = []
    for c in controllers:
        if not isinstance(c, dict):
            continue
        host = (c.get("host") or "").strip()
        if not host:
            continue
        name = (c.get("name") or host).strip() or host
        enabled = bool(c.get("enabled", True))
        try:
            port = int(c.get("port", 502))
        except Exception:
            port = 502
        volume_l = None
        if c.get("volume_l") is not None:
            try:
                volume_l = float(c.get("volume_l"))
            except Exception:
                volume_l = None
        clean.append({"host": host, "name": name, "enabled": enabled, "port": port, "volume_l": volume_l})

    out = {
        "maintenance_actions": list(data.get("maintenance_actions") or DEFAULTS["maintenance_actions"]),
        "controllers": clean,
        # keep host_names for backward compatibility / convenience
        "host_names": {c["host"]: c["name"] for c in clean},
        "modbus_profile": (data.get("modbus_profile") or DEFAULTS["modbus_profile"]).strip().lower(),
        "dulcopool_channel_map": data.get("dulcopool_channel_map") or dict(DEFAULTS["dulcopool_channel_map"]),
        "ezetrol_channel_map": data.get("ezetrol_channel_map") or dict(DEFAULTS["ezetrol_channel_map"]),
        "ezetrol_layout": (data.get("ezetrol_layout") or DEFAULTS["ezetrol_layout"]).strip().upper(),
        "ezetrol_layout_migrated": bool(data.get("ezetrol_layout_migrated", False)),
        "chart_downsample": bool(data.get("chart_downsample", DEFAULTS["chart_downsample"])),
        "chart_max_points": int(data.get("chart_max_points") or DEFAULTS["chart_max_points"]),
        # Server connection - always use SYSTEM_URLS (permanent, not user-editable)
        "backend_url": SYSTEM_URLS["backend_url"],
        "bootstrap_secret": SYSTEM_URLS["bootstrap_secret"],
        # Device identification
        "device_id": (data.get("device_id") or "").strip(),
        "device_name": (data.get("device_name") or "").strip()[:12],  # Hostname suffix, max 12 chars
        "device_alias": (data.get("device_alias") or "").strip(),
        "device_alias_updated_at": (data.get("device_alias_updated_at") or "").strip(),
        # Device API key
        "remote_api_key": (data.get("remote_api_key") or "").strip(),
        # Data retention settings
        "data_retention_enabled": bool(data.get("data_retention_enabled", DEFAULTS["data_retention_enabled"])),
        "data_retention_full_days": int(data.get("data_retention_full_days") or DEFAULTS["data_retention_full_days"]),
        "data_retention_hourly_days": int(data.get("data_retention_hourly_days") or DEFAULTS["data_retention_hourly_days"]),
        "data_retention_daily_days": int(data.get("data_retention_daily_days") or DEFAULTS["data_retention_daily_days"]),
        "storage_threshold_percent": int(data.get("storage_threshold_percent") or DEFAULTS["storage_threshold_percent"]),
        "storage_max_mb": int(data.get("storage_max_mb") or DEFAULTS["storage_max_mb"]),
        # Display settings
        "screen_rotation": data.get("screen_rotation") if data.get("screen_rotation") in (0, 90, 180, 270) else DEFAULTS["screen_rotation"],
        # Access Point settings
        "ap_suffix": (data.get("ap_suffix") or "").strip()[:20],  # Max 20 chars
        "ap_password_enabled": bool(data.get("ap_password_enabled", DEFAULTS["ap_password_enabled"])),
        "ap_password": (data.get("ap_password") or DEFAULTS["ap_password"]).strip(),
        # Appearance settings
        "appearance_theme": data.get("appearance_theme") if data.get("appearance_theme") in ("light", "dark", "system") else DEFAULTS["appearance_theme"],
        "appearance_accent_color": data.get("appearance_accent_color") if data.get("appearance_accent_color") in ("blue", "green", "purple", "orange", "teal") else DEFAULTS["appearance_accent_color"],
        "appearance_font_size": data.get("appearance_font_size") if data.get("appearance_font_size") in ("small", "medium", "large") else DEFAULTS["appearance_font_size"],
        "appearance_compact_mode": bool(data.get("appearance_compact_mode", DEFAULTS["appearance_compact_mode"])),
        # Language setting
        "language": data.get("language") if data.get("language") in ("en", "fr", "es", "de", "it", "ru") else DEFAULTS["language"],
        # Per-pool quick log actions
        "pool_actions": data.get("pool_actions") if isinstance(data.get("pool_actions"), dict) else {},
        # Network wizard
        "network_wizard_completed": bool(data.get("network_wizard_completed", DEFAULTS["network_wizard_completed"])),
        # Setup wizard (first boot)
        "setup_wizard_completed": bool(data.get("setup_wizard_completed", DEFAULTS["setup_wizard_completed"])),
        # Cloud connection master switch
        "cloud_enabled": bool(data.get("cloud_enabled", DEFAULTS["cloud_enabled"])),
        # Modbus logging cadence (clamped; intensive window is epoch seconds)
        "logger_poll_interval_seconds": max(5, min(3600, int(data.get("logger_poll_interval_seconds") or DEFAULTS["logger_poll_interval_seconds"]))),
        "intensive_poll_interval_seconds": max(1, min(60, int(data.get("intensive_poll_interval_seconds") or DEFAULTS["intensive_poll_interval_seconds"]))),
        "intensive_monitoring_until": int(data.get("intensive_monitoring_until") or 0),
        # Cloud upload settings
        "cloud_upload_enabled": bool(data.get("cloud_upload_enabled", DEFAULTS["cloud_upload_enabled"])),
        "cloud_upload_interval_minutes": max(1, min(60, int(data.get("cloud_upload_interval_minutes") or DEFAULTS["cloud_upload_interval_minutes"]))),
        "cloud_upload_last_ts": (data.get("cloud_upload_last_ts") or "").strip(),
        "cloud_upload_last_status": (data.get("cloud_upload_last_status") or "").strip(),
        "cloud_upload_last_error": (data.get("cloud_upload_last_error") or "").strip(),
        # RS485 devices
        "rs485_devices": sanitize_rs485_devices(data.get("rs485_devices")),
        # Scheduled reboot settings
        "scheduled_reboot_enabled": bool(data.get("scheduled_reboot_enabled", DEFAULTS["scheduled_reboot_enabled"])),
        "scheduled_reboot_time": validate_reboot_time(data.get("scheduled_reboot_time", DEFAULTS["scheduled_reboot_time"])),
    }
    # Validate AP password - disable if too short (WPA2 requires min 8 chars)
    if out["ap_password_enabled"] and len(out["ap_password"]) < 8:
        out["ap_password_enabled"] = False
        out["ap_password"] = ""

    # Atomic write with file locking to prevent corruption
    with file_lock(path):
        # Write to temp file first, then rename (atomic on POSIX)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2, sort_keys=True)
            os.replace(tmp_path, path)  # Atomic rename
        except Exception:
            # Clean up temp file if rename failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    return path

def validate_reboot_time(time_str) -> str:
    """Validate and normalize reboot time to HH:MM format.

    The single authority for this check - route handlers should call this
    (not re-implement the regex) and use the return value to decide what to
    tell the user, e.g. flash a warning when the result differs from what
    they submitted.
    """
    import re
    if not isinstance(time_str, str):
        return DEFAULTS["scheduled_reboot_time"]
    time_str = time_str.strip()
    if re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        # Normalize to HH:MM (e.g., "4:00" -> "04:00")
        parts = time_str.split(':')
        return f"{int(parts[0]):02d}:{parts[1]}"
    return DEFAULTS["scheduled_reboot_time"]


def sanitize_rs485_devices(devices) -> List[Dict[str, Any]]:
    """Sanitize an RS485 device list (port/baud/unit_id/mode/enabled).

    The single authority for this - previously reimplemented separately in
    load(), in save(), and again in main_ui.py's update_rs485_devices route,
    with all three copies needing to be kept in sync by hand.
    """
    if not isinstance(devices, list):
        return []
    clean = []
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        port = (dev.get("port") or "").strip()
        if not port:
            continue
        name = (dev.get("name") or "Water Tester").strip()
        try:
            baud = int(dev.get("baud", 9600))
        except Exception:
            baud = 9600
        try:
            unit_id = int(dev.get("unit_id", 1))
        except Exception:
            unit_id = 1
        mode = dev.get("mode", "standalone")
        if mode not in ("standalone", "merged"):
            mode = "standalone"
        merged_with_pool = (dev.get("merged_with_pool") or "").strip()
        enabled = bool(dev.get("enabled", True))
        clean.append({
            "port": port,
            "baud": baud,
            "name": name,
            "unit_id": unit_id,
            "mode": mode,
            "merged_with_pool": merged_with_pool,
            "enabled": enabled,
        })
    return clean


def actions_from_text(text: str) -> List[str]:
    # split by newline or comma; drop empties; keep order; de-dupe
    raw = []
    for line in (text or "").replace(",", "\n").splitlines():
        line = (line or "").strip()
        if line:
            raw.append(line)
    seen=set()
    out=[]
    for a in raw:
        if a not in seen:
            seen.add(a); out.append(a)
    return out

def unique_names(hosts: List[str], host_names: Dict[str, str]) -> Dict[str, str]:
    # Ensure names are unique (tabs use pool name)
    used=set()
    out={}
    for h in hosts:
        name=(host_names.get(h) or h).strip() or h
        base=name
        i=2
        while name in used:
            name=f"{base} ({i})"
            i+=1
        used.add(name)
        out[h]=name
    return out


# Flask convenience wrappers (use current_app.instance_path automatically)
def load_settings() -> Dict[str, Any]:
    """Load settings using Flask's current_app.instance_path."""
    from flask import current_app
    return load(current_app.instance_path)


def save_settings(data: Dict[str, Any]) -> Path:
    """Save settings using Flask's current_app.instance_path."""
    from flask import current_app
    return save(current_app.instance_path, data)
