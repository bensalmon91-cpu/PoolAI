#!/usr/bin/env python3
"""
Data Retention Script for PoolAIssistant

Implements the data retention policy:
- Keep full resolution data for N days (default: 30)
- Downsample older data to hourly averages
- Delete data older than max retention days (default: 365)

This script should be run AFTER chunk_manager has uploaded the full-res data,
so we preserve the original data in the cloud before downsampling locally.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configuration
DATA_DIR = Path(os.environ.get("POOLDASH_DATA_DIR", "/opt/PoolAIssistant/data"))
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
MAIN_DB = DATA_DIR / "pool_readings.sqlite3"
CHUNK_TRACKER = DATA_DIR / "chunks" / "chunk_status.json"


def load_settings():
    """Load retention settings from config."""
    defaults = {
        "data_retention_enabled": True,
        "data_retention_full_days": 30,
        "data_retention_hourly_days": 90,
        "data_retention_daily_days": 365,
    }

    if not SETTINGS_FILE.exists():
        return defaults

    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
        return {**defaults, **settings}
    except Exception as e:
        print(f"Warning: Could not load settings: {e}")
        return defaults


def load_chunk_tracker():
    """Load chunk upload status."""
    if not CHUNK_TRACKER.exists():
        return {"chunks": {}}
    try:
        with open(CHUNK_TRACKER) as f:
            return json.load(f)
    except Exception:
        return {"chunks": {}}


def get_uploaded_date_ranges(tracker):
    """Get date ranges that have been successfully uploaded."""
    uploaded_ranges = []
    for period_key, chunk_info in tracker.get("chunks", {}).items():
        start = chunk_info.get("period_start")
        end = chunk_info.get("period_end")
        if start and end:
            uploaded_ranges.append((start, end))
    return sorted(uploaded_ranges)


def downsample_to_hourly(conn, start_date, end_date, dry_run=False):
    """
    Downsample data from start_date to end_date to hourly averages.

    Creates hourly averages grouped by (pool, host, point_label, hour).
    Original rows are deleted after averages are computed.
    """
    cursor = conn.cursor()

    # Count rows to process
    cursor.execute("""
        SELECT COUNT(*) FROM readings
        WHERE date(ts) >= ? AND date(ts) <= ?
    """, (start_date, end_date))
    row_count = cursor.fetchone()[0]

    if row_count == 0:
        return 0, 0

    print(f"  Processing {row_count:,} rows from {start_date} to {end_date}")

    if dry_run:
        # Estimate hourly rows
        cursor.execute("""
            SELECT COUNT(DISTINCT strftime('%Y-%m-%d %H', ts) || pool || host || point_label)
            FROM readings
            WHERE date(ts) >= ? AND date(ts) <= ?
        """, (start_date, end_date))
        hourly_count = cursor.fetchone()[0]
        return row_count, hourly_count

    # Create temporary table with hourly averages
    cursor.execute("""
        CREATE TEMPORARY TABLE hourly_avg AS
        SELECT
            strftime('%Y-%m-%dT%H:00:00+00:00', ts) as ts,
            pool,
            host,
            MAX(system_name) as system_name,
            MAX(serial_number) as serial_number,
            point_label,
            AVG(value) as value,
            MAX(raw_type) as raw_type
        FROM readings
        WHERE date(ts) >= ? AND date(ts) <= ?
        GROUP BY strftime('%Y-%m-%d %H', ts), pool, host, point_label
    """, (start_date, end_date))

    # Get count of hourly rows
    cursor.execute("SELECT COUNT(*) FROM hourly_avg")
    hourly_count = cursor.fetchone()[0]

    # Delete original rows
    cursor.execute("""
        DELETE FROM readings
        WHERE date(ts) >= ? AND date(ts) <= ?
    """, (start_date, end_date))

    # Insert hourly averages
    cursor.execute("""
        INSERT INTO readings (ts, pool, host, system_name, serial_number, point_label, value, raw_type)
        SELECT ts, pool, host, system_name, serial_number, point_label, value, raw_type
        FROM hourly_avg
    """)

    # Cleanup
    cursor.execute("DROP TABLE hourly_avg")

    conn.commit()

    print(f"    Reduced {row_count:,} rows to {hourly_count:,} hourly averages")
    return row_count, hourly_count


def delete_old_data(conn, cutoff_date, dry_run=False):
    """Delete data older than cutoff_date."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM readings
        WHERE date(ts) < ?
    """, (cutoff_date,))
    count = cursor.fetchone()[0]

    if count == 0:
        return 0

    print(f"  Found {count:,} rows older than {cutoff_date}")

    if dry_run:
        return count

    cursor.execute("""
        DELETE FROM readings
        WHERE date(ts) < ?
    """, (cutoff_date,))

    conn.commit()
    print(f"    Deleted {count:,} rows")
    return count


def get_date_stats(conn):
    """Get quick stats about date ranges in the database."""
    cursor = conn.cursor()

    # Use the date index for fast min/max
    cursor.execute("""
        SELECT MIN(date(ts)) as min_date, MAX(date(ts)) as max_date
        FROM readings
    """)
    row = cursor.fetchone()

    return row[0], row[1]


def run_retention(dry_run=False, force=False):
    """Run the data retention policy."""
    print("=" * 60)
    print("DATA RETENTION")
    print("=" * 60)

    settings = load_settings()

    if not settings.get("data_retention_enabled") and not force:
        print("Data retention is disabled in settings.")
        print("Use --force to run anyway.")
        return

    full_days = settings.get("data_retention_full_days", 30)
    hourly_days = settings.get("data_retention_hourly_days", 90)
    max_days = settings.get("data_retention_daily_days", 365)

    print(f"\nRetention policy:")
    print(f"  - Full resolution: {full_days} days")
    print(f"  - Hourly averages: {hourly_days} days")
    print(f"  - Maximum retention: {max_days} days")

    if dry_run:
        print("\n[DRY RUN - no changes will be made]\n")

    # Calculate cutoff dates
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    downsample_cutoff = (now - timedelta(days=full_days)).strftime("%Y-%m-%d")
    delete_cutoff = (now - timedelta(days=max_days)).strftime("%Y-%m-%d")

    print(f"\nCutoff dates (based on today = {today}):")
    print(f"  - Downsample data before: {downsample_cutoff}")
    print(f"  - Delete data before: {delete_cutoff}")

    # Check uploaded chunks
    tracker = load_chunk_tracker()
    uploaded_ranges = get_uploaded_date_ranges(tracker)

    if uploaded_ranges:
        print(f"\nUploaded data ranges: {len(uploaded_ranges)} chunks")
        for start, end in uploaded_ranges[:5]:
            print(f"  - {start} to {end}")
        if len(uploaded_ranges) > 5:
            print(f"  ... and {len(uploaded_ranges) - 5} more")
    else:
        print("\nWARNING: No chunks have been uploaded yet!")
        print("Run chunk_manager.py first to preserve full-resolution data in the cloud.")
        if not force:
            print("Use --force to proceed anyway (data will be lost!).")
            return

    # Connect to database
    if not MAIN_DB.exists():
        print(f"ERROR: Database not found: {MAIN_DB}")
        return

    conn = sqlite3.connect(str(MAIN_DB), timeout=120)

    try:
        # Get current date range
        min_date, max_date = get_date_stats(conn)
        print(f"\nDatabase date range: {min_date} to {max_date}")

        # Phase 1: Delete very old data (> max_days)
        print(f"\n--- Phase 1: Delete data older than {max_days} days ---")
        deleted = delete_old_data(conn, delete_cutoff, dry_run=dry_run)

        # Phase 2: Downsample data between full_days and max_days
        print(f"\n--- Phase 2: Downsample data older than {full_days} days ---")

        # Find date ranges to downsample
        # We process day by day to avoid huge transactions
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT date(ts) as day
            FROM readings
            WHERE date(ts) < ? AND date(ts) >= ?
            ORDER BY day
        """, (downsample_cutoff, delete_cutoff))

        days_to_process = [row[0] for row in cursor.fetchall()]

        if not days_to_process:
            print("  No data to downsample.")
        else:
            print(f"  Found {len(days_to_process)} days to downsample")

            total_original = 0
            total_hourly = 0

            # Process in weekly batches for efficiency
            batch_size = 7
            for i in range(0, len(days_to_process), batch_size):
                batch = days_to_process[i:i + batch_size]
                start = batch[0]
                end = batch[-1]

                original, hourly = downsample_to_hourly(conn, start, end, dry_run=dry_run)
                total_original += original
                total_hourly += hourly

            reduction = (1 - total_hourly / total_original) * 100 if total_original > 0 else 0
            print(f"\n  Total: {total_original:,} rows → {total_hourly:,} rows ({reduction:.1f}% reduction)")

        # Phase 3: Vacuum to reclaim space (if not dry run)
        if not dry_run and (deleted > 0 or len(days_to_process) > 0):
            print("\n--- Phase 3: Compacting database ---")
            print("  Running VACUUM (this may take a while)...")
            conn.execute("VACUUM")
            print("  Done!")

    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("RETENTION COMPLETE")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run data retention policy")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("--force", action="store_true",
                        help="Run even if retention is disabled or chunks not uploaded")
    args = parser.parse_args()

    run_retention(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
