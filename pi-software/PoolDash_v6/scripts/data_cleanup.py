#!/usr/bin/env python3
"""
Data Cleanup and Thinning Script for PoolAIssistant

Progressive data retention:
1. Keep full resolution data for N days (default 30)
2. Aggregate to hourly averages for M days (default 90)
3. Aggregate to daily averages for P days (default 365)
4. Delete data older than daily retention
5. Emergency mode: if disk/DB exceeds threshold, delete oldest data

Usage:
    python data_cleanup.py          # Normal cleanup (check thresholds)
    python data_cleanup.py --force  # Force cleanup regardless of schedule
    python data_cleanup.py --dry-run  # Show what would be done without doing it
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INSTANCE_DIR = PROJECT_DIR / "instance"
DATA_DIR = Path(os.environ.get("POOLDASH_DATA_DIR", "/opt/PoolAIssistant/data"))

# Settings and database paths
SETTINGS_PATH = Path(os.environ.get("POOLDASH_SETTINGS_PATH", INSTANCE_DIR / "pooldash_settings.json"))
POOL_DB_PATH = Path(os.environ.get("POOL_DB_PATH", DATA_DIR / "pool_readings.sqlite3"))
CLEANUP_STATE_PATH = DATA_DIR / "cleanup_state.json"

# Default settings
DEFAULTS = {
    "data_retention_enabled": True,
    "data_retention_full_days": 30,
    "data_retention_hourly_days": 90,
    "data_retention_daily_days": 365,
    "storage_threshold_percent": 80,
    "storage_max_mb": 500,
}


def load_settings():
    """Load settings from JSON file."""
    settings = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                settings.update(data)
        except Exception as e:
            print(f"Warning: Error loading settings: {e}")
    return settings


def load_cleanup_state():
    """Load cleanup state (last cleanup timestamp, etc.)."""
    if not CLEANUP_STATE_PATH.exists():
        return {"last_cleanup_ts": None}
    try:
        with open(CLEANUP_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_cleanup_ts": None}


def save_cleanup_state(state):
    """Save cleanup state."""
    try:
        CLEANUP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CLEANUP_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving cleanup state: {e}")


def get_storage_info():
    """Get current storage usage information."""
    info = {
        "db_size_mb": 0,
        "disk_total_mb": 0,
        "disk_free_mb": 0,
        "disk_used_percent": 0,
    }

    try:
        if POOL_DB_PATH.exists():
            info["db_size_mb"] = POOL_DB_PATH.stat().st_size / (1024 * 1024)

        data_dir = POOL_DB_PATH.parent if POOL_DB_PATH.exists() else DATA_DIR
        if data_dir.exists():
            total, used, free = shutil.disk_usage(str(data_dir))
            info["disk_total_mb"] = total / (1024 * 1024)
            info["disk_free_mb"] = free / (1024 * 1024)
            info["disk_used_percent"] = (used / total) * 100
    except Exception as e:
        print(f"Warning: Could not get storage info: {e}")

    return info


def get_db_stats(con):
    """Get database statistics."""
    stats = {}
    try:
        # Total rows
        stats["total_rows"] = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

        # Date range
        result = con.execute("SELECT MIN(ts), MAX(ts) FROM readings").fetchone()
        stats["oldest_ts"] = result[0]
        stats["newest_ts"] = result[1]

        # Rows per day estimate
        if stats["oldest_ts"] and stats["newest_ts"]:
            try:
                oldest = datetime.fromisoformat(stats["oldest_ts"].replace("Z", "+00:00").replace(" ", "T"))
                newest = datetime.fromisoformat(stats["newest_ts"].replace("Z", "+00:00").replace(" ", "T"))
                days = max(1, (newest - oldest).days)
                stats["rows_per_day"] = stats["total_rows"] / days
            except Exception:
                stats["rows_per_day"] = 0
    except Exception as e:
        print(f"Warning: Could not get DB stats: {e}")

    return stats


def aggregate_to_hourly(con, cutoff_date, dry_run=False):
    """
    Aggregate readings older than cutoff to hourly averages.
    Creates averaged entries and removes originals.
    """
    print(f"Aggregating data older than {cutoff_date} to hourly averages...")

    # Find rows to aggregate (not already aggregated)
    # We identify aggregated rows by checking if there are multiple rows per hour
    cursor = con.execute(
        """
        SELECT
            strftime('%Y-%m-%d %H:00:00', ts) as hour_ts,
            pool,
            host,
            point_label,
            AVG(value) as avg_value,
            COUNT(*) as cnt
        FROM readings
        WHERE ts < ?
          AND value IS NOT NULL
        GROUP BY strftime('%Y-%m-%d %H', ts), pool, host, point_label
        HAVING cnt > 1
        """,
        (cutoff_date,),
    )

    aggregations = cursor.fetchall()
    if not aggregations:
        print("  No data to aggregate to hourly.")
        return 0

    rows_affected = 0
    for row in aggregations:
        hour_ts, pool, host, point_label, avg_value, cnt = row

        if dry_run:
            print(f"  Would aggregate {cnt} rows for {pool}/{host}/{point_label} at {hour_ts}")
            rows_affected += cnt - 1
            continue

        # Delete original rows for this hour
        con.execute(
            """
            DELETE FROM readings
            WHERE strftime('%Y-%m-%d %H:00:00', ts) = ?
              AND pool = ?
              AND host = ?
              AND point_label = ?
            """,
            (hour_ts, pool, host, point_label),
        )

        # Insert single averaged row
        con.execute(
            """
            INSERT INTO readings (ts, pool, host, point_label, value, raw_type)
            VALUES (?, ?, ?, ?, ?, 'hourly_avg')
            """,
            (hour_ts, pool, host, point_label, avg_value),
        )

        rows_affected += cnt - 1

    if not dry_run:
        con.commit()

    print(f"  Aggregated {rows_affected} rows to hourly averages.")
    return rows_affected


def aggregate_to_daily(con, cutoff_date, dry_run=False):
    """
    Aggregate hourly data older than cutoff to daily averages.
    """
    print(f"Aggregating data older than {cutoff_date} to daily averages...")

    cursor = con.execute(
        """
        SELECT
            strftime('%Y-%m-%d 12:00:00', ts) as day_ts,
            pool,
            host,
            point_label,
            AVG(value) as avg_value,
            COUNT(*) as cnt
        FROM readings
        WHERE ts < ?
          AND value IS NOT NULL
        GROUP BY date(ts), pool, host, point_label
        HAVING cnt > 1
        """,
        (cutoff_date,),
    )

    aggregations = cursor.fetchall()
    if not aggregations:
        print("  No data to aggregate to daily.")
        return 0

    rows_affected = 0
    for row in aggregations:
        day_ts, pool, host, point_label, avg_value, cnt = row

        if dry_run:
            print(f"  Would aggregate {cnt} rows for {pool}/{host}/{point_label} on {day_ts[:10]}")
            rows_affected += cnt - 1
            continue

        # Delete original rows for this day
        con.execute(
            """
            DELETE FROM readings
            WHERE date(ts) = date(?)
              AND pool = ?
              AND host = ?
              AND point_label = ?
            """,
            (day_ts, pool, host, point_label),
        )

        # Insert single averaged row
        con.execute(
            """
            INSERT INTO readings (ts, pool, host, point_label, value, raw_type)
            VALUES (?, ?, ?, ?, ?, 'daily_avg')
            """,
            (day_ts, pool, host, point_label, avg_value),
        )

        rows_affected += cnt - 1

    if not dry_run:
        con.commit()

    print(f"  Aggregated {rows_affected} rows to daily averages.")
    return rows_affected


def delete_old_data(con, cutoff_date, dry_run=False):
    """Delete data older than cutoff date."""
    print(f"Deleting data older than {cutoff_date}...")

    if dry_run:
        count = con.execute(
            "SELECT COUNT(*) FROM readings WHERE ts < ?", (cutoff_date,)
        ).fetchone()[0]
        print(f"  Would delete {count} rows.")
        return count

    cursor = con.execute("DELETE FROM readings WHERE ts < ?", (cutoff_date,))
    deleted = cursor.rowcount
    con.commit()

    print(f"  Deleted {deleted} rows.")
    return deleted


def emergency_cleanup(con, target_mb, dry_run=False):
    """
    Emergency cleanup: delete oldest data until DB is under target size.
    """
    print(f"Emergency cleanup: targeting {target_mb} MB database size...")

    current_size = POOL_DB_PATH.stat().st_size / (1024 * 1024) if POOL_DB_PATH.exists() else 0
    if current_size <= target_mb:
        print(f"  Database already under target ({current_size:.2f} MB).")
        return 0

    # Get oldest date
    oldest = con.execute("SELECT MIN(ts) FROM readings").fetchone()[0]
    if not oldest:
        print("  No data to delete.")
        return 0

    total_deleted = 0
    batch_size = 10000

    while current_size > target_mb:
        if dry_run:
            print(f"  Would delete batches until DB is under {target_mb} MB")
            break

        # Delete oldest batch
        cursor = con.execute(
            """
            DELETE FROM readings
            WHERE rowid IN (
                SELECT rowid FROM readings
                ORDER BY ts ASC
                LIMIT ?
            )
            """,
            (batch_size,),
        )
        deleted = cursor.rowcount
        con.commit()

        if deleted == 0:
            break

        total_deleted += deleted

        # Check size (need to VACUUM for accurate size, but that's expensive)
        # Estimate based on rows deleted
        current_size = POOL_DB_PATH.stat().st_size / (1024 * 1024)
        print(f"  Deleted {deleted} rows, DB now ~{current_size:.2f} MB")

        if deleted < batch_size:
            break

    # VACUUM to reclaim space
    if total_deleted > 0 and not dry_run:
        print("  Running VACUUM to reclaim space...")
        con.execute("VACUUM")

    print(f"  Emergency cleanup complete. Deleted {total_deleted} rows total.")
    return total_deleted


def run_cleanup(settings, dry_run=False):
    """Run the full cleanup process."""
    if not POOL_DB_PATH.exists():
        print(f"Database not found: {POOL_DB_PATH}")
        return False

    storage_info = get_storage_info()
    print(f"Current DB size: {storage_info['db_size_mb']:.2f} MB")
    print(f"Disk usage: {storage_info['disk_used_percent']:.1f}%")

    # Connect to database
    con = sqlite3.connect(str(POOL_DB_PATH), timeout=60)

    try:
        stats = get_db_stats(con)
        print(f"Total rows: {stats.get('total_rows', 0):,}")
        print(f"Date range: {stats.get('oldest_ts', 'N/A')} to {stats.get('newest_ts', 'N/A')}")

        now = datetime.now()

        # Check for emergency cleanup first
        storage_threshold = settings.get("storage_threshold_percent", 80)
        storage_max_mb = settings.get("storage_max_mb", 500)

        if storage_info["disk_used_percent"] > storage_threshold:
            print(f"\n⚠️  Disk usage ({storage_info['disk_used_percent']:.1f}%) exceeds threshold ({storage_threshold}%)")
            emergency_cleanup(con, storage_max_mb * 0.7, dry_run)
        elif storage_info["db_size_mb"] > storage_max_mb:
            print(f"\n⚠️  DB size ({storage_info['db_size_mb']:.2f} MB) exceeds max ({storage_max_mb} MB)")
            emergency_cleanup(con, storage_max_mb * 0.8, dry_run)

        # Normal retention policy
        full_days = settings.get("data_retention_full_days", 30)
        hourly_days = settings.get("data_retention_hourly_days", 90)
        daily_days = settings.get("data_retention_daily_days", 365)

        # Aggregate to hourly (data older than full_days)
        hourly_cutoff = (now - timedelta(days=full_days)).strftime("%Y-%m-%d %H:%M:%S")
        aggregate_to_hourly(con, hourly_cutoff, dry_run)

        # Aggregate to daily (data older than hourly_days)
        daily_cutoff = (now - timedelta(days=hourly_days)).strftime("%Y-%m-%d %H:%M:%S")
        aggregate_to_daily(con, daily_cutoff, dry_run)

        # Delete old data (data older than daily_days)
        delete_cutoff = (now - timedelta(days=daily_days)).strftime("%Y-%m-%d %H:%M:%S")
        delete_old_data(con, delete_cutoff, dry_run)

        # Optimize database
        if not dry_run:
            print("\nOptimizing database...")
            con.execute("ANALYZE")
            # Only VACUUM if we deleted significant data
            if stats.get("total_rows", 0) > 100000:
                print("Running VACUUM (this may take a while)...")
                con.execute("VACUUM")

        print("\n✓ Cleanup complete!")
        return True

    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Clean up and thin pool readings data")
    parser.add_argument("--force", action="store_true", help="Force cleanup regardless of schedule")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    print(f"=== Data Cleanup - {datetime.now().isoformat()} ===")

    settings = load_settings()

    if not settings.get("data_retention_enabled", True) and not args.force:
        print("Data retention is disabled. Use --force to run anyway.")
        return 0

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    success = run_cleanup(settings, args.dry_run)

    if success and not args.dry_run:
        state = load_cleanup_state()
        state["last_cleanup_ts"] = datetime.now().isoformat()
        save_cleanup_state(state)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
