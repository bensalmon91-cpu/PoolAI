# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Database Optimization

"""
Database optimization script - adds indexes and runs maintenance.
Run periodically or after large data imports.
"""

import sqlite3
import os
from pathlib import Path

DATA_DIR = Path("/opt/PoolAIssistant/data")
MAIN_DB = DATA_DIR / "pool_readings.sqlite3"


def optimize_database():
    """Add indexes and optimize the database."""
    if not MAIN_DB.exists():
        print(f"Database not found: {MAIN_DB}")
        return False

    print(f"Optimizing database: {MAIN_DB}")
    original_size = MAIN_DB.stat().st_size / 1024 / 1024

    conn = sqlite3.connect(str(MAIN_DB), timeout=60)
    cursor = conn.cursor()

    # Find main table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]

        # Add timestamp index
        for ts_col in ['ts', 'timestamp', 'created_at', 'reading_time']:
            if ts_col in columns:
                idx_name = f"idx_{table}_{ts_col}"
                try:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({ts_col})")
                    print(f"  Created index: {idx_name}")
                except sqlite3.Error as e:
                    print(f"  Index {idx_name} skipped: {e}")
                break

        # Add host index if exists
        if 'host' in columns:
            idx_name = f"idx_{table}_host"
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(host)")
                print(f"  Created index: {idx_name}")
            except sqlite3.Error as e:
                print(f"  Index {idx_name} skipped: {e}")

        # Compound index for common query pattern
        if 'host' in columns:
            for ts_col in ['ts', 'timestamp', 'created_at']:
                if ts_col in columns:
                    idx_name = f"idx_{table}_host_{ts_col}"
                    try:
                        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(host, {ts_col})")
                        print(f"  Created compound index: {idx_name}")
                    except sqlite3.Error as e:
                        print(f"  Index {idx_name} skipped: {e}")
                    break

    conn.commit()

    # Run analyze for query optimizer
    print("Running ANALYZE...")
    cursor.execute("ANALYZE")

    # Vacuum to reclaim space and defragment
    print("Running VACUUM...")
    conn.execute("VACUUM")

    conn.close()

    new_size = MAIN_DB.stat().st_size / 1024 / 1024
    print(f"\nOptimization complete!")
    print(f"  Before: {original_size:.1f} MB")
    print(f"  After:  {new_size:.1f} MB")
    print(f"  Saved:  {original_size - new_size:.1f} MB")

    return True


if __name__ == "__main__":
    optimize_database()
