import json
import os
import tempfile
import fcntl
from pathlib import Path
from typing import Dict, Any, List, Tuple
from contextlib import contextmanager

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
    "upload_interval_minutes": 10,
    # Server connection (PERMANENT - do not change)
    "backend_url": "https://poolaissistant.modprojects.co.uk",
    "bootstrap_secret": "e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9",

    # Device identification (unique per Pi installation)
    "device_id": "",              # Auto-generated unique ID (UUID)
    "device_name": "",            # Hostname suffix (PoolAI-{name}.local)
    "device_alias": "",           # Human-friendly name (e.g., "Leisure Centre Pool")
    "device_alias_updated_at": "",  # ISO timestamp of last alias change (for sync)

    # Remote sync settings (MOD Projects backend)
    "remote_sync_enabled": False,
    "remote_sync_url": "https://poolaissistant.modprojects.co.uk",
    "remote_api_key": "",
    "remote_sync_schedule": "3days",  # "daily", "3days", "weekly", "custom"
    "remote_sync_interval_hours": 72,  # used when schedule is "custom"
    "last_remote_sync_ts": "",

    # Data retention / thinning settings
    "data_retention_enabled": True,
    "data_retention_full_days": 30,      # keep full resolution for this many days
    "data_retention_hourly_days": 90,    # keep hourly averages for this many days
    "data_retention_daily_days": 365,    # keep daily averages for this many days
    "storage_threshold_percent": 80,     # start aggressive cleanup at this % of storage
    "storage_max_mb": 500,               # target max DB size in MB

    # Display settings
    "screen_rotation": 0,                # 0, 90, 180, or 270 degrees

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

    # Eco/Sleep Mode settings
    "eco_mode_enabled": False,           # Enable screen dimming after inactivity
    "eco_timeout_minutes": 5,            # Minutes of inactivity before dimming (1-60)
    "eco_brightness_percent": 10,        # Dimmed screen brightness (0-100)
    "eco_wake_on_touch": True,           # Wake screen on touch/click

    # Per-pool quick log actions
    "pool_actions": {},                  # {"Pool Name": ["Action1", "Action2", ...]}

    # Network wizard
    "network_wizard_completed": False,   # True after wizard has been run

    # Setup wizard (first boot)
    "setup_wizard_completed": False,     # True after initial setup wizard has been completed

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
    "bootstrap_secret": "e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9",
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
        if not isinstance(merged.get("upload_interval_minutes"), int):
            merged["upload_interval_minutes"] = DEFAULTS["upload_interval_minutes"]
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

        # Remote sync settings
        if not isinstance(merged.get("remote_sync_enabled"), bool):
            merged["remote_sync_enabled"] = DEFAULTS["remote_sync_enabled"]
        if not isinstance(merged.get("remote_sync_url"), str):
            merged["remote_sync_url"] = DEFAULTS["remote_sync_url"]
        if not isinstance(merged.get("remote_api_key"), str):
            merged["remote_api_key"] = ""
        if merged.get("remote_sync_schedule") not in ("daily", "3days", "weekly", "custom"):
            merged["remote_sync_schedule"] = DEFAULTS["remote_sync_schedule"]
        if not isinstance(merged.get("remote_sync_interval_hours"), int):
            merged["remote_sync_interval_hours"] = DEFAULTS["remote_sync_interval_hours"]
        if not isinstance(merged.get("last_remote_sync_ts"), str):
            merged["last_remote_sync_ts"] = ""

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

        # Eco/Sleep Mode settings
        if not isinstance(merged.get("eco_mode_enabled"), bool):
            merged["eco_mode_enabled"] = DEFAULTS["eco_mode_enabled"]
        if not isinstance(merged.get("eco_timeout_minutes"), int) or not (1 <= merged.get("eco_timeout_minutes", 5) <= 60):
            merged["eco_timeout_minutes"] = DEFAULTS["eco_timeout_minutes"]
        if not isinstance(merged.get("eco_brightness_percent"), int) or not (0 <= merged.get("eco_brightness_percent", 10) <= 100):
            merged["eco_brightness_percent"] = DEFAULTS["eco_brightness_percent"]
        if not isinstance(merged.get("eco_wake_on_touch"), bool):
            merged["eco_wake_on_touch"] = DEFAULTS["eco_wake_on_touch"]

        # Per-pool quick log actions
        if not isinstance(merged.get("pool_actions"), dict):
            merged["pool_actions"] = {}

        # Network wizard
        if not isinstance(merged.get("network_wizard_completed"), bool):
            merged["network_wizard_completed"] = DEFAULTS["network_wizard_completed"]

        # Setup wizard (first boot)
        if not isinstance(merged.get("setup_wizard_completed"), bool):
            merged["setup_wizard_completed"] = DEFAULTS["setup_wizard_completed"]

        # RS485 devices
        if not isinstance(merged.get("rs485_devices"), list):
            merged["rs485_devices"] = []

        # Sanitize RS485 devices
        clean_rs485 = []
        for dev in merged.get("rs485_devices") or []:
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
            clean_rs485.append({
                "port": port,
                "baud": baud,
                "name": name,
                "unit_id": unit_id,
                "mode": mode,
                "merged_with_pool": merged_with_pool,
                "enabled": enabled,
            })
        merged["rs485_devices"] = clean_rs485

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

        # Clamp upload interval to supported values
        allowed = {1, 3, 6, 12, 20, 30, 40, 60}
        if merged.get("upload_interval_minutes") not in allowed:
            merged["upload_interval_minutes"] = DEFAULTS["upload_interval_minutes"]
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
        "upload_interval_minutes": int(data.get("upload_interval_minutes") or DEFAULTS["upload_interval_minutes"]),
        # Server connection - always use SYSTEM_URLS (permanent, not user-editable)
        "backend_url": SYSTEM_URLS["backend_url"],
        "bootstrap_secret": SYSTEM_URLS["bootstrap_secret"],
        # Device identification
        "device_id": (data.get("device_id") or "").strip(),
        "device_name": (data.get("device_name") or "").strip()[:12],  # Hostname suffix, max 12 chars
        "device_alias": (data.get("device_alias") or "").strip(),
        "device_alias_updated_at": (data.get("device_alias_updated_at") or "").strip(),
        # Remote sync settings
        "remote_sync_enabled": bool(data.get("remote_sync_enabled", DEFAULTS["remote_sync_enabled"])),
        "remote_sync_url": (data.get("remote_sync_url") or DEFAULTS["remote_sync_url"]).strip(),
        "remote_api_key": (data.get("remote_api_key") or "").strip(),
        "remote_sync_schedule": data.get("remote_sync_schedule") or DEFAULTS["remote_sync_schedule"],
        "remote_sync_interval_hours": int(data.get("remote_sync_interval_hours") or DEFAULTS["remote_sync_interval_hours"]),
        "last_remote_sync_ts": (data.get("last_remote_sync_ts") or "").strip(),
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
        # Eco/Sleep Mode settings
        "eco_mode_enabled": bool(data.get("eco_mode_enabled", DEFAULTS["eco_mode_enabled"])),
        "eco_timeout_minutes": max(1, min(60, int(data.get("eco_timeout_minutes") or DEFAULTS["eco_timeout_minutes"]))),
        "eco_brightness_percent": max(0, min(100, int(data.get("eco_brightness_percent") or DEFAULTS["eco_brightness_percent"]))),
        "eco_wake_on_touch": bool(data.get("eco_wake_on_touch", DEFAULTS["eco_wake_on_touch"])),
        # Per-pool quick log actions
        "pool_actions": data.get("pool_actions") if isinstance(data.get("pool_actions"), dict) else {},
        # Network wizard
        "network_wizard_completed": bool(data.get("network_wizard_completed", DEFAULTS["network_wizard_completed"])),
        # Setup wizard (first boot)
        "setup_wizard_completed": bool(data.get("setup_wizard_completed", DEFAULTS["setup_wizard_completed"])),
        # RS485 devices
        "rs485_devices": _sanitize_rs485_devices(data.get("rs485_devices")),
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

def _sanitize_rs485_devices(devices) -> List[Dict[str, Any]]:
    """Sanitize RS485 device list for saving."""
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
