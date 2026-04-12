"""
LSI (Langelier Saturation Index) history storage and retrieval.
Stores LSI calculations over time for trend analysis.
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os


def get_db_path() -> str:
    """Get the path to the pool readings database."""
    return os.environ.get("POOL_DB_PATH", "/opt/PoolAIssistant/data/pool_readings.sqlite3")


def init_lsi_table(db_path: Optional[str] = None) -> None:
    """Create the LSI readings table if it doesn't exist."""
    if db_path is None:
        db_path = get_db_path()

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lsi_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                pool TEXT NOT NULL,
                ph REAL,
                temperature_c REAL,
                calcium_hardness REAL,
                total_alkalinity REAL,
                tds REAL,
                lsi_value REAL NOT NULL,
                ph_saturation REAL,
                source TEXT DEFAULT 'manual'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lsi_pool_time
            ON lsi_readings(pool, timestamp)
        """)
        conn.commit()


def store_lsi_reading(
    pool: str,
    lsi_value: float,
    ph: Optional[float] = None,
    temperature_c: Optional[float] = None,
    calcium_hardness: Optional[float] = None,
    total_alkalinity: Optional[float] = None,
    tds: Optional[float] = None,
    ph_saturation: Optional[float] = None,
    source: str = "manual",
    db_path: Optional[str] = None
) -> int:
    """
    Store an LSI reading in the database.

    Args:
        pool: Pool name/identifier
        lsi_value: Calculated LSI value
        ph: pH reading used in calculation
        temperature_c: Temperature in Celsius
        calcium_hardness: Calcium hardness in ppm
        total_alkalinity: Total alkalinity in ppm
        tds: Total dissolved solids in ppm
        ph_saturation: Calculated pH saturation value
        source: 'manual' or 'sensor' to track data source
        db_path: Optional custom database path

    Returns:
        The ID of the inserted row
    """
    if db_path is None:
        db_path = get_db_path()

    # Ensure table exists
    init_lsi_table(db_path)

    timestamp = datetime.now().isoformat()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("""
            INSERT INTO lsi_readings
            (timestamp, pool, ph, temperature_c, calcium_hardness,
             total_alkalinity, tds, lsi_value, ph_saturation, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, pool, ph, temperature_c, calcium_hardness,
            total_alkalinity, tds, lsi_value, ph_saturation, source
        ))
        conn.commit()
        return cursor.lastrowid


def get_lsi_history(
    pool: str,
    limit: int = 100,
    since_days: Optional[int] = None,
    db_path: Optional[str] = None
) -> List[Dict]:
    """
    Get LSI history for a pool.

    Args:
        pool: Pool name/identifier
        limit: Maximum number of readings to return
        since_days: Only return readings from the last N days
        db_path: Optional custom database path

    Returns:
        List of LSI readings as dictionaries
    """
    if db_path is None:
        db_path = get_db_path()

    # Ensure table exists
    init_lsi_table(db_path)

    query = """
        SELECT id, timestamp, pool, ph, temperature_c, calcium_hardness,
               total_alkalinity, tds, lsi_value, ph_saturation, source
        FROM lsi_readings
        WHERE pool = ?
    """
    params = [pool]

    if since_days is not None:
        query += " AND timestamp >= datetime('now', ?)"
        params.append(f"-{since_days} days")

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_lsi_chart_data(
    pool: str,
    since_days: int = 30,
    db_path: Optional[str] = None
) -> Tuple[List[str], List[float]]:
    """
    Get LSI data formatted for charting.

    Args:
        pool: Pool name/identifier
        since_days: Number of days to include
        db_path: Optional custom database path

    Returns:
        Tuple of (timestamps, lsi_values) lists
    """
    if db_path is None:
        db_path = get_db_path()

    # Ensure table exists
    init_lsi_table(db_path)

    query = """
        SELECT timestamp, lsi_value
        FROM lsi_readings
        WHERE pool = ? AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(query, [pool, f"-{since_days} days"])
        rows = cursor.fetchall()

    timestamps = [row[0] for row in rows]
    values = [row[1] for row in rows]

    return timestamps, values


def get_latest_lsi(pool: str, db_path: Optional[str] = None) -> Optional[Dict]:
    """
    Get the most recent LSI reading for a pool.

    Args:
        pool: Pool name/identifier
        db_path: Optional custom database path

    Returns:
        Latest LSI reading as dictionary, or None if no readings exist
    """
    history = get_lsi_history(pool, limit=1, db_path=db_path)
    return history[0] if history else None


def delete_lsi_reading(reading_id: int, db_path: Optional[str] = None) -> bool:
    """
    Delete an LSI reading by ID.

    Args:
        reading_id: ID of the reading to delete
        db_path: Optional custom database path

    Returns:
        True if deleted, False if not found
    """
    if db_path is None:
        db_path = get_db_path()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM lsi_readings WHERE id = ?",
            [reading_id]
        )
        conn.commit()
        return cursor.rowcount > 0
