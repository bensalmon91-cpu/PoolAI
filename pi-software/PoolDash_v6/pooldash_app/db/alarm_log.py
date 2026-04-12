"""
Alarm Log Database Module
Stores alarm acknowledgments, notes, and historical tracking
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


def init_alarm_log_db(db_path: str):
    """Initialize the alarm log database with required tables"""
    with sqlite3.connect(db_path, timeout=10) as con:
        # Alarm acknowledgments and notes table
        con.execute("""
            CREATE TABLE IF NOT EXISTS alarm_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool TEXT NOT NULL,
                host TEXT,
                alarm_label TEXT NOT NULL,
                alarm_name TEXT,
                severity TEXT,
                started_ts TEXT NOT NULL,
                ended_ts TEXT,
                duration_seconds INTEGER,
                acknowledged BOOLEAN DEFAULT 0,
                acknowledged_by TEXT,
                acknowledged_ts TEXT,
                notes TEXT,
                action_taken TEXT,
                created_ts TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index for faster queries
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_alarm_log_pool_ts
            ON alarm_log(pool, started_ts DESC)
        """)

        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_alarm_log_severity
            ON alarm_log(severity, started_ts DESC)
        """)

        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_alarm_log_ack
            ON alarm_log(acknowledged, started_ts DESC)
        """)

        con.commit()


def log_alarm(
    db_path: str,
    pool: str,
    host: str,
    alarm_label: str,
    alarm_name: str,
    severity: str,
    started_ts: str,
    ended_ts: Optional[str] = None,
    duration_seconds: Optional[int] = None
):
    """Log an alarm event"""
    with sqlite3.connect(db_path, timeout=10) as con:
        con.execute("""
            INSERT INTO alarm_log
            (pool, host, alarm_label, alarm_name, severity, started_ts, ended_ts, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (pool, host, alarm_label, alarm_name, severity, started_ts, ended_ts, duration_seconds))

        con.commit()
        return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def acknowledge_alarm(
    db_path: str,
    alarm_id: int,
    acknowledged_by: str,
    notes: Optional[str] = None,
    action_taken: Optional[str] = None
):
    """Acknowledge an alarm with optional notes"""
    with sqlite3.connect(db_path, timeout=10) as con:
        con.execute("""
            UPDATE alarm_log
            SET acknowledged = 1,
                acknowledged_by = ?,
                acknowledged_ts = ?,
                notes = COALESCE(?, notes),
                action_taken = COALESCE(?, action_taken)
            WHERE id = ?
        """, (acknowledged_by, datetime.utcnow().isoformat(), notes, action_taken, alarm_id))

        con.commit()


def add_alarm_note(db_path: str, alarm_id: int, note: str):
    """Add a note to an alarm"""
    with sqlite3.connect(db_path, timeout=10) as con:
        # Append to existing notes
        con.execute("""
            UPDATE alarm_log
            SET notes = CASE
                WHEN notes IS NULL OR notes = '' THEN ?
                ELSE notes || '\n---\n' || ?
            END
            WHERE id = ?
        """, (note, note, alarm_id))

        con.commit()


def get_alarm_history(
    db_path: str,
    pool: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    since_date: Optional[str] = None,
    limit: int = 500
) -> List[Dict]:
    """Get alarm history with optional filtering"""
    with sqlite3.connect(db_path, timeout=10) as con:
        con.row_factory = sqlite3.Row

        query = "SELECT * FROM alarm_log WHERE 1=1"
        params = []

        if pool:
            query += " AND pool = ?"
            params.append(pool)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        if acknowledged is not None:
            query += " AND acknowledged = ?"
            params.append(1 if acknowledged else 0)

        if since_date:
            query += " AND started_ts >= ?"
            params.append(since_date)

        query += " ORDER BY started_ts DESC LIMIT ?"
        params.append(limit)

        rows = con.execute(query, params).fetchall()

        return [dict(row) for row in rows]


def get_alarm_stats(db_path: str, pool: Optional[str] = None) -> Dict:
    """Get alarm statistics"""
    with sqlite3.connect(db_path, timeout=10) as con:
        con.row_factory = sqlite3.Row

        where_clause = "WHERE pool = ?" if pool else ""
        params = [pool] if pool else []

        stats = {}

        # Total alarms
        stats['total'] = con.execute(
            f"SELECT COUNT(*) as cnt FROM alarm_log {where_clause}",
            params
        ).fetchone()['cnt']

        # By severity
        severity_rows = con.execute(
            f"SELECT severity, COUNT(*) as cnt FROM alarm_log {where_clause} GROUP BY severity",
            params
        ).fetchall()
        stats['by_severity'] = {row['severity']: row['cnt'] for row in severity_rows}

        # Acknowledged vs unacknowledged
        ack_stats = con.execute(
            f"SELECT acknowledged, COUNT(*) as cnt FROM alarm_log {where_clause} GROUP BY acknowledged",
            params
        ).fetchall()
        stats['acknowledged'] = sum(row['cnt'] for row in ack_stats if row['acknowledged'])
        stats['unacknowledged'] = sum(row['cnt'] for row in ack_stats if not row['acknowledged'])

        # Average duration (for alarms that have ended)
        avg_duration = con.execute(
            f"""SELECT AVG(duration_seconds) as avg_dur
                FROM alarm_log
                {where_clause}
                {"AND" if where_clause else "WHERE"} duration_seconds IS NOT NULL""",
            params
        ).fetchone()['avg_dur']
        stats['avg_duration_seconds'] = int(avg_duration) if avg_duration else 0

        return stats


def sync_from_alarm_events(
    pool_db_path: str,
    alarm_log_db_path: str,
    pool: Optional[str] = None
):
    """
    Sync alarms from the alarm_events table to the alarm_log
    This creates a more detailed historical record
    """
    from ..alarm_descriptions import get_alarm_info

    # Read from alarm_events
    with sqlite3.connect(pool_db_path, timeout=10) as pool_con:
        pool_con.row_factory = sqlite3.Row

        where = "WHERE pool = ?" if pool else ""
        params = [pool] if pool else []

        # Get all alarm events
        events = pool_con.execute(f"""
            SELECT pool, host, source_label as label, started_ts, ended_ts
            FROM alarm_events
            {where}
            ORDER BY started_ts DESC
        """, params).fetchall()

    # Write to alarm_log
    synced = 0
    with sqlite3.connect(alarm_log_db_path, timeout=10) as log_con:
        for event in events:
            # Get alarm info
            info = get_alarm_info(event['label'])

            # Calculate duration if alarm has ended
            duration = None
            if event['ended_ts']:
                try:
                    start = datetime.fromisoformat(event['started_ts'].replace('+00:00', ''))
                    end = datetime.fromisoformat(event['ended_ts'].replace('+00:00', ''))
                    duration = int((end - start).total_seconds())
                except ValueError as e:
                    logger.warning(f"Failed to parse alarm timestamps: {e}")

            # Check if already logged
            existing = log_con.execute("""
                SELECT id FROM alarm_log
                WHERE pool = ? AND alarm_label = ? AND started_ts = ?
            """, (event['pool'], event['label'], event['started_ts'])).fetchone()

            if not existing:
                log_con.execute("""
                    INSERT INTO alarm_log
                    (pool, host, alarm_label, alarm_name, severity, started_ts, ended_ts, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event['pool'],
                    event['host'],
                    event['label'],
                    info['name'],
                    info['severity'],
                    event['started_ts'],
                    event['ended_ts'],
                    duration
                ))
                synced += 1

        log_con.commit()

    return synced
