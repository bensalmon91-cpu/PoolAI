import json
import os
import sqlite3
from flask import Blueprint, current_app, render_template, jsonify, request

alarms_bp = Blueprint("alarms", __name__, url_prefix="/alarms")

def _get_db_path() -> str:
    # Match charts blueprint behavior and fall back to the default pool readings DB.
    path = current_app.config.get("POOL_DB_PATH") or os.getenv("POOL_DB_PATH") or os.getenv("POOLDB")
    if path:
        return path
    preferred = "/opt/PoolAIssistant/data/pool_readings.sqlite3"
    if os.path.isdir("/opt/PoolAIssistant"):
        return preferred
    return os.path.join(os.getcwd(), "pool_readings.sqlite3")

def _connect():
    con = sqlite3.connect(_get_db_path(), timeout=5)
    con.row_factory = sqlite3.Row
    return con

@alarms_bp.get("/<pool>")
def alarms_page(pool: str):
    return render_template("alarms_improved.html", pool=pool)

@alarms_bp.get("/api/<pool>")
def alarms_api(pool: str):
    """
    Uses alarm_events table.
    - Active now = rows with ended_ts IS NULL.
    - Recent changes = most recent start/end events.
    - Connection status = last reading time per host.
    """
    limit = int(request.args.get("limit", "120"))

    with _connect() as con:
        active = con.execute(
            """
            SELECT pool, host, system_name, serial_number, source_label, bit_name, started_ts
            FROM alarm_events
            WHERE pool = ? AND ended_ts IS NULL
            ORDER BY started_ts DESC;
            """,
            (pool,),
        ).fetchall()

        recent = con.execute(
            """
            SELECT pool, host, system_name, serial_number, source_label, bit_name, started_ts, ended_ts
            FROM alarm_events
            WHERE pool = ?
            ORDER BY COALESCE(ended_ts, started_ts) DESC
            LIMIT ?;
            """,
            (pool, limit),
        ).fetchall()

        # Get connection status - last reading per host for this pool
        # Use a fast query that doesn't scan the whole table
        connection_status = []
        try:
            # Get the host for this pool from settings or alarm_events
            hosts = con.execute(
                """
                SELECT DISTINCT host FROM alarm_events WHERE pool = ? LIMIT 10;
                """,
                (pool,),
            ).fetchall()

            for h in hosts:
                host = h["host"]
                # Get last reading timestamp for this host (fast: use rowid desc)
                last_reading = con.execute(
                    """
                    SELECT ts FROM readings
                    WHERE host = ?
                    ORDER BY rowid DESC
                    LIMIT 1;
                    """,
                    (host,),
                ).fetchone()

                connection_status.append({
                    "host": host,
                    "last_reading": last_reading["ts"] if last_reading else None,
                })
        except Exception:
            # readings table might not exist or other issue
            pass

    def _label(r) -> str:
        source = r['source_label'] or 'Unknown'
        bit = r['bit_name'] or 'b0'
        return f"{source}:{bit}"

    active_list = []
    for r in active:
        active_list.append({
            "pool": r["pool"],
            "host": r["host"],
            "system_name": r["system_name"] or "",
            "serial_number": r["serial_number"] or "",
            "label": _label(r),
            "value": 1,
            "ts": r["started_ts"],
        })

    recent_list = []
    for r in recent:
        ended = r["ended_ts"]
        recent_list.append({
            "ts": ended or r["started_ts"],
            "label": _label(r),
            "value": 0 if ended else 1,
        })

    return jsonify({
        "pool": pool,
        "active": active_list,
        "latest": active_list,
        "recent": recent_list,
        "connection_status": connection_status,
    })


# ----------------------------
# Controller States API
# ----------------------------

# Controller operation mode bit definitions (Ezetrol docs v4.4.2)
# Registers 400304 (Cl), 400305 (pH), 400307 (Ch4)
CONTROLLER_MODE_BITS = {
    0:  {"name": "Manual", "color": "#ff9800", "priority": 2},
    1:  {"name": "Automatic", "color": "#4caf50", "priority": 1},
    2:  {"name": "Off", "color": "#9e9e9e", "priority": 3},
    3:  {"name": "AutoTune", "color": "#2196f3", "priority": 2},
    5:  {"name": "Stopped", "color": "#f44336", "priority": 4},
    6:  {"name": "Frozen", "color": "#9c27b0", "priority": 3},
    7:  {"name": "100%", "color": "#ff5722", "priority": 4},
    11: {"name": "Eco", "color": "#8bc34a", "priority": 2},
    13: {"name": "Standby", "color": "#607d8b", "priority": 3},
}

CONTROLLER_REGISTERS = {
    "Status_Mode_Controller1_Chlorine": "Chlorine",
    "Status_Mode_Controller2_pH": "pH",
    "Status_Mode_Controller4_Ch4": "Ch4",
}


@alarms_bp.get("/api/<pool>/controller-states")
def controller_states_api(pool: str):
    """
    Get current controller operation modes for display in status banner.
    Returns the active mode for each controller (Chlorine, pH, Ch4).
    Based on Ezetrol Modbus Register Documentation v4.4.2
    """
    controllers = []

    with _connect() as con:
        # Get hosts from readings table (more reliable than alarm_events)
        hosts = con.execute(
            """
            SELECT DISTINCT host FROM readings
            WHERE pool = ? AND point_label LIKE 'Status_Mode_%'
            ORDER BY host
            LIMIT 10;
            """,
            (pool,),
        ).fetchall()

        if not hosts:
            # Fallback: try to get hosts from any readings
            hosts = con.execute(
                """
                SELECT DISTINCT host FROM readings WHERE pool = ? LIMIT 10;
                """,
                (pool,),
            ).fetchall()

        for h in hosts:
            host = h["host"]

            for register, channel_name in CONTROLLER_REGISTERS.items():
                row = con.execute(
                    """
                    SELECT value, ts, system_name FROM readings
                    WHERE host = ? AND point_label = ?
                    ORDER BY rowid DESC
                    LIMIT 1;
                    """,
                    (host, register),
                ).fetchone()

                if row and row["value"] is not None:
                    value = int(row["value"])
                    ts = row["ts"]
                    system_name = row["system_name"] or ""

                    # Find active modes (multiple can be active)
                    active_modes = []
                    for bit_num, mode_info in CONTROLLER_MODE_BITS.items():
                        if value & (1 << bit_num):
                            active_modes.append({
                                "bit": bit_num,
                                "name": mode_info["name"],
                                "color": mode_info["color"],
                                "priority": mode_info["priority"],
                            })

                    # Sort by priority (lower = more important to show)
                    active_modes.sort(key=lambda x: x["priority"])

                    # Determine primary mode to display
                    if active_modes:
                        primary_mode = active_modes[0]
                    else:
                        primary_mode = {"name": "Unknown", "color": "#9e9e9e"}

                    controllers.append({
                        "host": host,
                        "system_name": system_name,
                        "channel": channel_name,
                        "register": register,
                        "raw_value": value,
                        "primary_mode": primary_mode["name"],
                        "color": primary_mode["color"],
                        "all_modes": [m["name"] for m in active_modes],
                        "ts": ts,
                    })

    return jsonify({
        "pool": pool,
        "controllers": controllers,
    })


@alarms_bp.get("/api/<pool>/states")
def states_api(pool: str):
    """
    Legacy endpoint - redirects to controller-states for backwards compatibility.
    """
    return controller_states_api(pool)


@alarms_bp.get("/<pool>/history")
def alarm_history(pool: str):
    """View alarm history with filtering and notes"""
    import os
    from ..db import alarm_log
    
    # Initialize alarm log database if needed
    alarm_log_path = os.path.join(current_app.config.get("DATA_DIR", "/opt/PoolAIssistant/data"), "alarm_log.sqlite3")
    if not os.path.exists(alarm_log_path):
        alarm_log.init_alarm_log_db(alarm_log_path)
    
    # Get filters from query params
    filter_severity = request.args.get("severity", "")
    filter_acknowledged = request.args.get("acknowledged", "")
    filter_since_date = request.args.get("since_date", "")
    
    # Build filter params
    acknowledged_filter = None
    if filter_acknowledged == "1":
        acknowledged_filter = True
    elif filter_acknowledged == "0":
        acknowledged_filter = False
    
    # Get alarm history
    alarms = alarm_log.get_alarm_history(
        alarm_log_path,
        pool=pool,
        severity=filter_severity or None,
        acknowledged=acknowledged_filter,
        since_date=filter_since_date or None,
        limit=500
    )
    
    # Get statistics
    stats = alarm_log.get_alarm_stats(alarm_log_path, pool=pool)
    
    return render_template(
        "alarm_history.html",
        pool=pool,
        alarms=alarms,
        stats=stats,
        filter_severity=filter_severity,
        filter_acknowledged=filter_acknowledged,
        filter_since_date=filter_since_date,
    )


@alarms_bp.post("/acknowledge/<int:alarm_id>")
def acknowledge_alarm(alarm_id: int):
    """Acknowledge an alarm with notes"""
    import os
    from ..db import alarm_log
    
    alarm_log_path = os.path.join(current_app.config.get("DATA_DIR", "/opt/PoolAIssistant/data"), "alarm_log.sqlite3")
    
    data = request.get_json()
    alarm_log.acknowledge_alarm(
        alarm_log_path,
        alarm_id,
        acknowledged_by=data.get("acknowledged_by", ""),
        notes=data.get("notes"),
        action_taken=data.get("action_taken")
    )
    
    return jsonify({"success": True})


@alarms_bp.post("/<pool>/sync")
def sync_alarm_history(pool: str):
    """Sync alarms from alarm_events table to alarm_log"""
    import os
    from ..db import alarm_log
    from flask import flash, redirect, url_for
    
    pool_db_path = _get_db_path()
    alarm_log_path = os.path.join(current_app.config.get("DATA_DIR", "/opt/PoolAIssistant/data"), "alarm_log.sqlite3")
    
    # Initialize if needed
    if not os.path.exists(alarm_log_path):
        alarm_log.init_alarm_log_db(alarm_log_path)
    
    # Sync
    synced_count = alarm_log.sync_from_alarm_events(pool_db_path, alarm_log_path, pool)
    
    flash(f"Synced {synced_count} alarm(s) from events database")
    return redirect(url_for("alarms.alarm_history", pool=pool))


@alarms_bp.get("/<pool>/export")
def export_alarm_history(pool: str):
    """Export alarm history to CSV"""
    import os
    import csv
    from io import StringIO
    from flask import Response
    from ..db import alarm_log
    
    alarm_log_path = os.path.join(current_app.config.get("DATA_DIR", "/opt/PoolAIssistant/data"), "alarm_log.sqlite3")
    
    # Get filters
    filter_severity = request.args.get("severity", "")
    filter_acknowledged = request.args.get("acknowledged", "")
    filter_since_date = request.args.get("since_date", "")
    
    acknowledged_filter = None
    if filter_acknowledged == "1":
        acknowledged_filter = True
    elif filter_acknowledged == "0":
        acknowledged_filter = False
    
    # Get data
    alarms = alarm_log.get_alarm_history(
        alarm_log_path,
        pool=pool,
        severity=filter_severity or None,
        acknowledged=acknowledged_filter,
        since_date=filter_since_date or None,
        limit=10000  # Higher limit for export
    )
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Pool", "Host", "Alarm Name", "Alarm Label", "Severity",
        "Started", "Ended", "Duration (seconds)", 
        "Acknowledged", "Acknowledged By", "Acknowledged At",
        "Action Taken", "Notes"
    ])
    
    # Data rows
    for alarm in alarms:
        writer.writerow([
            alarm.get("pool", ""),
            alarm.get("host", ""),
            alarm.get("alarm_name", ""),
            alarm.get("alarm_label", ""),
            alarm.get("severity", ""),
            alarm.get("started_ts", ""),
            alarm.get("ended_ts", ""),
            alarm.get("duration_seconds", ""),
            "Yes" if alarm.get("acknowledged") else "No",
            alarm.get("acknowledged_by", ""),
            alarm.get("acknowledged_ts", ""),
            alarm.get("action_taken", ""),
            alarm.get("notes", ""),
        ])
    
    # Create response
    output.seek(0)
    from datetime import datetime
    filename = f"alarm_history_{pool}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )
