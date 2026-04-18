#!/usr/bin/env python3
"""
Health Reporter for PoolDash
Sends periodic heartbeats to the backend with system status,
checks for pending commands, and executes them.

Now includes:
- Controller connection status (online/offline per controller)
- Active alarms count
- Issues list for quick problem identification

Run via cron every 15 minutes:
*/15 * * * * /opt/PoolAIssistant/venv/bin/python /home/poolaissistant/health_reporter.py >> /opt/PoolAIssistant/logs/health_reporter.log 2>&1
"""

import os
import sys
import json
import subprocess
import socket
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# AI Assistant integration - optional
AI_SYNC_AVAILABLE = False
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pooldash_app"))
    from blueprints.ai_assistant import (
        sync_from_server,
        get_pending_responses,
        mark_responses_synced,
        get_suggestion_actions,
        mark_actions_synced,
        get_db_path
    )
    AI_SYNC_AVAILABLE = True
except ImportError:
    pass

# Configuration
DATA_DIR = Path("/opt/PoolAIssistant/data")
LOGS_DIR = Path("/opt/PoolAIssistant/logs")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"

# Keep this in sync with web-portal/php_deploy/includes/RemoteSettings.php.
# These are the only pooldash_settings.json keys that the admin panel may
# write via apply_settings commands, and the keys reported in the heartbeat
# snapshot. Do not add device identity, API keys, or backend URLs here.
REMOTE_SETTABLE_KEYS = {
    'cloud_upload_enabled', 'cloud_upload_interval_minutes',
    'upload_interval_minutes',
    'data_retention_enabled', 'data_retention_full_days',
    'data_retention_hourly_days', 'data_retention_daily_days',
    'storage_threshold_percent',
    'screen_rotation',
    'appearance_theme', 'appearance_font_size', 'appearance_accent_color',
    'appearance_compact_mode',
    'eco_mode_enabled', 'eco_timeout_minutes', 'eco_brightness_percent',
    'eco_wake_on_touch',
    'chart_downsample', 'chart_max_points',
    'language',
    'scheduled_reboot_enabled', 'scheduled_reboot_time',
}
POOL_DB = DATA_DIR / "pool_readings.sqlite3"
CHUNK_TRACKER = DATA_DIR / "chunks" / "chunk_status.json"
HEALTH_STATE_FILE = DATA_DIR / "health_state.json"
CHUNK_MANAGER = Path("/home/poolaissistant/chunk_manager.py")
VENV_PYTHON = Path("/opt/PoolAIssistant/venv/bin/python")

# Thresholds
CONTROLLER_OFFLINE_MINUTES = 60  # Controller considered offline after this
DISK_WARNING_PCT = 80
MEMORY_WARNING_PCT = 85
TEMP_WARNING_C = 70


def log(message, level="INFO"):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def load_settings():
    """Load backend settings."""
    if not SETTINGS_FILE.exists():
        log(f"Settings file not found: {SETTINGS_FILE}", "ERROR")
        return None
    with open(SETTINGS_FILE) as f:
        data = json.load(f)
    return {
        'api_key': data.get('api_key') or data.get('remote_api_key', ''),
        'backend_url': data.get('backend_url') or data.get('remote_sync_url', ''),
        'device_id': data.get('device_id', ''),
        'device_alias': data.get('device_alias', ''),
        'device_alias_updated_at': data.get('device_alias_updated_at', ''),
        'controllers': data.get('controllers', []),
    }


def load_full_settings():
    """Load full settings file for modification."""
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def save_full_settings(data):
    """Save full settings file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        return True
    except Exception as e:
        log(f"Failed to save settings: {e}", "ERROR")
        return False


def update_controller_setting(controller_name, setting_key, value):
    """Update a specific setting for a controller by name."""
    data = load_full_settings()
    controllers = data.get('controllers', [])

    for c in controllers:
        if c.get('name') == controller_name:
            c[setting_key] = value
            data['controllers'] = controllers
            if save_full_settings(data):
                log(f"Updated {controller_name}.{setting_key} = {value}")
                return True
            return False

    log(f"Controller not found: {controller_name}", "WARNING")
    return False


def save_settings_alias(alias, updated_at):
    """Save device alias to settings file."""
    if not SETTINGS_FILE.exists():
        return False
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        data['device_alias'] = alias
        data['device_alias_updated_at'] = updated_at
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        return True
    except Exception as e:
        log(f"Failed to save alias: {e}", "ERROR")
        return False


def load_health_state():
    """Load persistent health state."""
    if HEALTH_STATE_FILE.exists():
        try:
            with open(HEALTH_STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {
        'last_upload_success': None,
        'last_upload_error': None,
        'failed_uploads': 0,
        'consecutive_failures': 0,
    }


def save_health_state(state):
    """Save persistent health state."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_uptime_seconds():
    """Get system uptime in seconds."""
    try:
        with open('/proc/uptime') as f:
            return int(float(f.read().split()[0]))
    except:
        return None


def get_disk_usage():
    """Get disk usage percentage."""
    try:
        stat = os.statvfs('/')
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_pct = (1 - free / total) * 100
        return round(used_pct, 1)
    except:
        return None


def get_memory_usage():
    """Get memory usage percentage."""
    try:
        with open('/proc/meminfo') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
        total = meminfo.get('MemTotal', 1)
        available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
        used_pct = (1 - available / total) * 100
        return round(used_pct, 1)
    except:
        return None


def get_cpu_temp():
    """Get CPU temperature."""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            temp = int(f.read().strip()) / 1000.0
            return round(temp, 1)
    except:
        return None


def get_ip_address():
    """Get primary IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return None


def get_software_version():
    """Get software version from version file or settings."""
    version_file = Path("/opt/PoolAIssistant/VERSION")
    if version_file.exists():
        try:
            return version_file.read_text().strip()
        except:
            pass
    return "unknown"


def get_pending_chunks():
    """Get count of pending chunks to upload."""
    if not CHUNK_TRACKER.exists():
        return 0
    try:
        with open(CHUNK_TRACKER) as f:
            tracker = json.load(f)
        count = 0
        for period_key, chunk_info in tracker.get('chunks', {}).items():
            chunk_path = Path(chunk_info.get('path', ''))
            if chunk_path.exists():
                count += 1
        return count
    except:
        return 0


def get_controller_status():
    """
    Get connection status for each controller.
    Returns list of controllers with their online/offline status.
    Uses fast queries optimized for large databases.
    """
    if not POOL_DB.exists():
        return []

    controllers = []
    # modbus_logger writes ts in UTC (+00:00), so compare in UTC too.
    # Using naive datetime.now() here previously caused every controller to
    # appear offline by the local tz offset (e.g. 60 min during BST).
    now = datetime.now(timezone.utc)

    try:
        con = sqlite3.connect(str(POOL_DB), timeout=30)
        con.row_factory = sqlite3.Row

        # Get ALL known hosts from alarm_events (includes offline controllers)
        all_hosts = set()
        try:
            alarm_hosts = con.execute("""
                SELECT DISTINCT host FROM alarm_events WHERE host IS NOT NULL
            """).fetchall()
            for r in alarm_hosts:
                all_hosts.add(r['host'])
        except:
            pass

        # Also get from recent readings
        try:
            recent_hosts = con.execute("""
                SELECT DISTINCT host FROM (
                    SELECT host FROM readings ORDER BY rowid DESC LIMIT 1000
                )
            """).fetchall()
            for r in recent_hosts:
                all_hosts.add(r['host'])
        except:
            pass

        # For each host, get the last reading
        for host in all_hosts:
            row = con.execute("""
                SELECT ts FROM readings
                WHERE host = ?
                ORDER BY rowid DESC
                LIMIT 1
            """, (host,)).fetchone()

            last_ts = row['ts'] if row else None

            # Parse timestamp as tz-aware UTC (modbus_logger writes +00:00).
            last_reading = None
            if last_ts:
                try:
                    if 'T' in last_ts:
                        ts_clean = last_ts.replace('Z', '+00:00')
                        last_reading = datetime.fromisoformat(ts_clean)
                    else:
                        last_reading = datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S')
                    if last_reading.tzinfo is None:
                        last_reading = last_reading.replace(tzinfo=timezone.utc)
                except:
                    pass

            # Determine if online
            is_online = False
            minutes_ago = None
            if last_reading:
                diff = now - last_reading
                minutes_ago = int(diff.total_seconds() / 60)
                is_online = minutes_ago <= CONTROLLER_OFFLINE_MINUTES

            controllers.append({
                'host': host,
                'last_reading': last_ts,
                'minutes_ago': minutes_ago,
                'online': is_online,
            })

        con.close()

    except Exception as e:
        log(f"Error getting controller status: {e}", "WARNING")

    return controllers


def get_active_alarms():
    """Get count of active alarms per severity."""
    if not POOL_DB.exists():
        return {'total': 0, 'critical': 0, 'warning': 0}

    try:
        con = sqlite3.connect(str(POOL_DB), timeout=10)
        con.row_factory = sqlite3.Row

        # Count active alarms (ended_ts IS NULL)
        rows = con.execute("""
            SELECT source_label, bit_name, COUNT(*) as cnt
            FROM alarm_events
            WHERE ended_ts IS NULL
            GROUP BY source_label, bit_name
        """).fetchall()

        total = 0
        critical = 0
        warning = 0

        for row in rows:
            label = f"{row['source_label']}:{row['bit_name']}"
            cnt = row['cnt']
            total += cnt

            # Classify severity based on label
            if 'Fault' in label or 'Error' in label or ':b2' in label:
                critical += cnt
            elif 'Manual' in label or 'Mode' in label or 'Limit' in label:
                warning += cnt

        con.close()
        return {'total': total, 'critical': critical, 'warning': warning}

    except Exception as e:
        log(f"Error getting active alarms: {e}", "WARNING")
        return {'total': 0, 'critical': 0, 'warning': 0}


def get_issues():
    """
    Compile a list of current issues/problems for quick review.
    Returns list of issue strings.
    """
    issues = []

    # Check controllers
    controllers = get_controller_status()
    offline_controllers = [c for c in controllers if not c.get('online')]
    if offline_controllers:
        hosts = ', '.join(c['host'] for c in offline_controllers)
        issues.append(f"OFFLINE: {len(offline_controllers)} controller(s) - {hosts}")

    # Check disk
    disk_pct = get_disk_usage()
    if disk_pct and disk_pct > DISK_WARNING_PCT:
        issues.append(f"DISK: {disk_pct}% used (>{DISK_WARNING_PCT}% threshold)")

    # Check memory
    mem_pct = get_memory_usage()
    if mem_pct and mem_pct > MEMORY_WARNING_PCT:
        issues.append(f"MEMORY: {mem_pct}% used (>{MEMORY_WARNING_PCT}% threshold)")

    # Check temperature
    temp = get_cpu_temp()
    if temp and temp > TEMP_WARNING_C:
        issues.append(f"TEMP: {temp}C (>{TEMP_WARNING_C}C threshold)")

    # Check alarms
    alarms = get_active_alarms()
    if alarms.get('critical', 0) > 0:
        issues.append(f"ALARMS: {alarms['critical']} critical alarm(s)")

    return issues


def send_heartbeat(settings, health_data):
    """Send heartbeat to backend and get pending commands."""
    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')

    if not api_key or not backend_url:
        log("Missing api_key or backend_url", "ERROR")
        return None

    try:
        response = requests.post(
            f"{backend_url}/api/heartbeat.php",
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=health_data,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        else:
            log(f"Heartbeat failed with status {response.status_code}: {response.text}", "ERROR")
            return None

    except requests.exceptions.Timeout:
        log("Heartbeat timed out", "ERROR")
        return None
    except requests.exceptions.ConnectionError as e:
        log(f"Connection error: {e}", "ERROR")
        return None
    except Exception as e:
        log(f"Heartbeat error: {e}", "ERROR")
        return None


def execute_command(settings, command):
    """Execute a command from the backend."""
    command_id = command.get('id')
    command_type = command.get('command_type')
    payload = command.get('payload')

    log(f"Executing command {command_id}: {command_type}")

    success = False
    result = ""

    try:
        if command_type == 'upload':
            # Trigger chunk upload
            if CHUNK_MANAGER.exists() and VENV_PYTHON.exists():
                proc = subprocess.run(
                    [str(VENV_PYTHON), str(CHUNK_MANAGER), '--force-retry'],
                    cwd=str(DATA_DIR.parent / "app"),
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )
                success = proc.returncode == 0
                result = proc.stdout[-500:] if proc.stdout else proc.stderr[-500:]
                log(f"Upload command completed: {'success' if success else 'failed'}")
            else:
                result = "Chunk manager not found"
                log(result, "ERROR")

        elif command_type == 'restart':
            # Restart services
            subprocess.run(['sudo', 'systemctl', 'restart', 'poolaissistant_logger'], timeout=30)
            success = True
            result = "Services restarted"

        elif command_type == 'update':
            # Trigger update check
            update_script = Path("/home/poolaissistant/update_check.py")
            if update_script.exists() and VENV_PYTHON.exists():
                proc = subprocess.run(
                    [str(VENV_PYTHON), str(update_script)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                success = proc.returncode == 0
                result = proc.stdout[-500:] if proc.stdout else proc.stderr[-500:]

        elif command_type == 'apply_settings':
            # Admin pushed new setting values. Merge only allow-listed keys
            # into pooldash_settings.json; restart UI so changes take effect.
            # The allow-list on this Pi (REMOTE_SETTABLE_KEYS) is the final
            # authority - even if the server queues a key we don't recognise,
            # we ignore it.
            proposed = {}
            if isinstance(payload, dict):
                proposed = payload.get('settings') or {}
            if not isinstance(proposed, dict) or not proposed:
                success = False
                result = "No settings in payload"
            else:
                applied = {}
                rejected = {}
                for key, value in proposed.items():
                    if key not in REMOTE_SETTABLE_KEYS:
                        rejected[key] = 'not in allow-list'
                        continue
                    applied[key] = value

                if not applied:
                    success = False
                    result = f"All keys rejected: {rejected}"
                else:
                    try:
                        # Load, merge, atomic-write.
                        current = {}
                        if SETTINGS_FILE.exists():
                            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                                current = json.load(f)
                        current.update(applied)
                        tmp = SETTINGS_FILE.with_suffix('.json.tmp')
                        with open(tmp, 'w', encoding='utf-8') as f:
                            json.dump(current, f, indent=2, sort_keys=True)
                        tmp.replace(SETTINGS_FILE)

                        # Restart the web UI so the new settings take effect.
                        # Best-effort: if sudo rule isn't in place this
                        # returns non-zero but the settings are already
                        # saved - next service restart will pick them up.
                        try:
                            subprocess.run(
                                ['sudo', 'systemctl', 'restart', 'poolaissistant_ui'],
                                timeout=30, capture_output=True,
                            )
                        except Exception as e:
                            log(f"apply_settings: restart warning: {e}", "WARNING")

                        success = True
                        result = (
                            f"Applied: {list(applied.keys())}"
                            + (f"; rejected: {rejected}" if rejected else "")
                        )
                    except Exception as e:
                        success = False
                        result = f"apply_settings write failed: {e}"

        else:
            result = f"Unknown command type: {command_type}"
            log(result, "WARNING")

    except subprocess.TimeoutExpired:
        result = "Command timed out"
        log(result, "ERROR")
    except Exception as e:
        result = str(e)
        log(f"Command error: {e}", "ERROR")

    # Report completion to backend
    report_command_completion(settings, command_id, success, result)

    return success


def report_command_completion(settings, command_id, success, result):
    """Report command completion to backend."""
    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')

    if not api_key or not backend_url:
        return

    try:
        requests.post(
            f"{backend_url}/api/command_complete.php?id={command_id}",
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'success': success,
                'result': result[:1000] if result else None,
            },
            timeout=30
        )
    except Exception as e:
        log(f"Failed to report command completion: {e}", "ERROR")


def main():
    log("=" * 50)
    log("Health reporter starting")

    # Load settings
    settings = load_settings()
    if not settings:
        log("Cannot proceed without settings", "ERROR")
        return 1

    # Load persistent state
    state = load_health_state()

    # Get controller and alarm status
    controller_status = get_controller_status()
    alarms = get_active_alarms()
    issues = get_issues()

    # Merge controller config (from settings) with runtime status
    controller_config = {c.get('name'): c for c in settings.get('controllers', [])}
    controllers = []
    for status in controller_status:
        host = status.get('host')
        # Find matching config by host
        config = next((c for c in settings.get('controllers', []) if c.get('host') == host), {})
        controllers.append({
            **status,
            'name': config.get('name', host),
            'volume_l': config.get('volume_l'),
            'enabled': config.get('enabled', True),
        })

    # Count online/offline controllers
    online_count = sum(1 for c in controllers if c.get('online'))
    offline_count = len(controllers) - online_count

    # Collect health data
    health_data = {
        'uptime_seconds': get_uptime_seconds(),
        'disk_used_pct': get_disk_usage(),
        'memory_used_pct': get_memory_usage(),
        'cpu_temp': get_cpu_temp(),
        'last_upload_success': state.get('last_upload_success'),
        'last_upload_error': state.get('last_upload_error'),
        'pending_chunks': get_pending_chunks(),
        'failed_uploads': state.get('failed_uploads', 0),
        'software_version': get_software_version(),
        'ip_address': get_ip_address(),
        # NEW: Controller status
        'controllers': controllers,
        'controllers_online': online_count,
        'controllers_offline': offline_count,
        # NEW: Alarm status
        'alarms_total': alarms.get('total', 0),
        'alarms_critical': alarms.get('critical', 0),
        'alarms_warning': alarms.get('warning', 0),
        # NEW: Issues list for quick review
        'issues': issues,
        'has_issues': len(issues) > 0,
        # Device alias for bi-directional sync
        'device_alias': settings.get('device_alias', ''),
        'device_alias_updated_at': settings.get('device_alias_updated_at', ''),
        # Snapshot of admin-editable settings so the admin panel can show
        # live state and detect drift from pushed values.
        'settings_snapshot': {k: settings.get(k) for k in REMOTE_SETTABLE_KEYS if k in settings},
        # Timestamp
        'reported_at': datetime.now().isoformat(),
    }

    # Add AI data to heartbeat if available
    if AI_SYNC_AVAILABLE:
        try:
            ai_responses = get_pending_responses()
            ai_actions = get_suggestion_actions()
            if ai_responses or ai_actions:
                health_data['ai'] = {
                    'responses': ai_responses,
                    'suggestion_actions': ai_actions
                }
                log(f"AI sync: {len(ai_responses)} responses, {len(ai_actions)} actions to send")
        except Exception as e:
            log(f"AI sync prep failed: {e}", "WARNING")

    log(f"System: uptime={health_data['uptime_seconds']}s, disk={health_data['disk_used_pct']}%, "
        f"mem={health_data['memory_used_pct']}%, temp={health_data['cpu_temp']}C")
    log(f"Controllers: {online_count} online, {offline_count} offline")
    log(f"Alarms: {alarms.get('total', 0)} total ({alarms.get('critical', 0)} critical)")
    log(f"Uploads: pending={health_data['pending_chunks']}, failed={health_data['failed_uploads']}")

    if issues:
        log(f"ISSUES DETECTED ({len(issues)}):")
        for issue in issues:
            log(f"  - {issue}", "WARNING")

    # Send heartbeat
    response = send_heartbeat(settings, health_data)

    if response:
        log("Heartbeat sent successfully")

        # Handle alias sync (server may have newer alias)
        alias_sync = response.get('alias_sync')
        if alias_sync and alias_sync.get('source') == 'server':
            server_alias = alias_sync.get('alias', '')
            server_ts = alias_sync.get('updated_at', '')
            if server_alias != settings.get('device_alias', ''):
                log(f"Alias sync: updating to '{server_alias}' from server")
                if save_settings_alias(server_alias, server_ts):
                    log("Alias saved successfully")

        # Process any pending commands
        commands = response.get('commands', [])
        if commands:
            log(f"Received {len(commands)} command(s)")
            for cmd in commands:
                execute_command(settings, cmd)

                # Update state after upload command
                if cmd.get('command_type') == 'upload':
                    # Re-check pending chunks after upload
                    state['last_upload_success'] = datetime.now().isoformat()
                    state['consecutive_failures'] = 0
                    save_health_state(state)

        # Process AI data from response
        if AI_SYNC_AVAILABLE:
            try:
                ai_data = response.get('ai', {})
                questions = ai_data.get('questions', [])
                suggestions = ai_data.get('suggestions', [])

                if questions or suggestions:
                    sync_from_server(questions, suggestions)
                    log(f"AI sync: received {len(questions)} questions, {len(suggestions)} suggestions")

                # Mark synced items
                ai_sent = health_data.get('ai', {})
                if ai_sent.get('responses'):
                    synced_ids = [r['local_id'] for r in ai_sent['responses']]
                    mark_responses_synced(synced_ids)
                    log(f"AI sync: marked {len(synced_ids)} responses as synced")

                if ai_sent.get('suggestion_actions'):
                    synced_ids = [a['local_id'] for a in ai_sent['suggestion_actions']]
                    mark_actions_synced(synced_ids)
                    log(f"AI sync: marked {len(synced_ids)} actions as synced")

                # Process AI setting actions (e.g., set pool volume)
                ai_actions = ai_data.get('actions', [])
                for action in ai_actions:
                    action_type = action.get('action')
                    if action_type == 'set_controller_setting':
                        controller = action.get('controller')
                        setting = action.get('setting')
                        value = action.get('value')
                        if controller and setting and value is not None:
                            update_controller_setting(controller, setting, value)
                            log(f"AI action: set {controller}.{setting} = {value}")

            except Exception as e:
                log(f"AI sync processing failed: {e}", "WARNING")
    else:
        state['consecutive_failures'] = state.get('consecutive_failures', 0) + 1
        save_health_state(state)
        log(f"Heartbeat failed (consecutive failures: {state['consecutive_failures']})")

    log("Health reporter complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
