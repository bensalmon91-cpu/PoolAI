import sqlite3
import logging
from datetime import datetime
from .connection import get_connection, init_database

logger = logging.getLogger(__name__)

# Maximum length for text fields to prevent bloat
MAX_POOL_LENGTH = 100
MAX_ACTION_LENGTH = 200
MAX_NOTE_LENGTH = 10000


def _validate_input(pool: str, action: str, note: str = "") -> tuple:
    """Validate and sanitize input parameters."""
    pool = str(pool)[:MAX_POOL_LENGTH] if pool else ""
    action = str(action)[:MAX_ACTION_LENGTH] if action else ""
    note = str(note)[:MAX_NOTE_LENGTH] if note else ""
    return pool, action, note


def ensure_db(path: str):
    """Ensure the maintenance_logs table exists in the given database.

    This function is idempotent and can be safely called multiple times.
    The table is now stored in pool_readings.sqlite3 alongside readings data,
    enabling automatic backup via existing sync infrastructure.
    """
    try:
        with get_connection(path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS maintenance_logs (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       timestamp TEXT NOT NULL,
                       pool TEXT NOT NULL,
                       action TEXT NOT NULL,
                       note TEXT
                     )"""
            )
            # Index for efficient queries by pool+action+timestamp
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pool_action_time ON maintenance_logs(pool, action, timestamp)")
            # Index for timestamp-based queries (AI analysis, sync)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_maint_timestamp ON maintenance_logs(timestamp)")
    except sqlite3.Error as e:
        logger.exception(f"Failed to ensure maintenance_logs table: {e}")
        raise


def ensure_maintenance_table_in_pool_db(pool_db_path: str):
    """Create maintenance_logs table in pool_readings database.

    This is an alias for ensure_db() but makes the intent clear:
    we're adding the maintenance table to the pool readings DB
    so it gets synced to the server for AI analysis and backup.
    """
    ensure_db(pool_db_path)


def log_action(db_path: str, pool: str, action: str, note: str = ""):
    """Log a maintenance action with input validation."""
    pool, action, note = _validate_input(pool, action, note)

    if not pool or not action:
        logger.warning(f"Invalid log_action call: pool={pool!r}, action={action!r}")
        return

    ensure_db(db_path)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO maintenance_logs (timestamp, pool, action, note) VALUES (?,?,?,?)",
                (ts, pool, action, note.strip() or None)
            )
    except sqlite3.Error as e:
        logger.exception(f"Failed to log maintenance action: {e}")
        raise


def last_entry(db_path: str, pool: str, action: str) -> tuple:
    """Get the last maintenance entry for a pool/action."""
    pool, action, _ = _validate_input(pool, action)
    ensure_db(db_path)

    try:
        with get_connection(db_path, readonly=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT timestamp, note FROM maintenance_logs
                   WHERE pool=? AND action=? ORDER BY timestamp DESC LIMIT 1""",
                (pool, action)
            )
            row = cur.fetchone()
            if not row:
                return "—", ""
            ts, note = row
            return ts or "—", note or ""
    except sqlite3.Error as e:
        logger.exception(f"Failed to fetch last entry: {e}")
        return "—", ""


def fetch_all(db_path: str, pool: str, limit: int = 1000):
    """Fetch all maintenance logs for a pool with validated limit."""
    pool, _, _ = _validate_input(pool, "")

    # Validate limit to prevent excessive queries
    limit = max(1, min(limit, 10000))

    ensure_db(db_path)

    try:
        with get_connection(db_path, readonly=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT timestamp, pool, action, note
                   FROM maintenance_logs
                   WHERE pool = ? ORDER BY timestamp DESC LIMIT ?""",
                (pool, limit)
            )
            return cur.fetchall()
    except sqlite3.Error as e:
        logger.exception(f"Failed to fetch maintenance logs: {e}")
        return []
