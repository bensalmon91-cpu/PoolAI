#!/usr/bin/env python3
"""
Data Cleanup and Thinning Script for PoolAIssistant

Progressive data retention:
1. Keep full resolution data for N days (default 30)
2. Aggregate to hourly averages for M days (default 90)
3. Aggregate to daily averages for P days (default 365)
4. Delete data older than daily retention
5. Emergency mode: if disk/DB exceeds threshold, delete oldest data

Thinning is set-based and resumable: each run processes whole-day slices
(one GROUP BY into a temp table + one indexed range DELETE + one bulk INSERT
per day) and records progress in cleanup_state.json, stopping when the
wall-clock budget runs out. The previous implementation issued one
non-indexable strftime()-matched DELETE per hour-group - a full table scan
per group - so on a multi-GB DB it never finished before the systemd
TimeoutStartSec killed it, and retention silently never ran.

Usage:
    python data_cleanup.py          # Normal cleanup (check thresholds)
    python data_cleanup.py --force  # Force cleanup regardless of schedule
    python data_cleanup.py --dry-run  # Show what would be done without doing it
    python data_cleanup.py --budget-seconds 1200  # Wall-clock cap for thinning
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
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
    # Far backstop only. The real emergency guard is the disk-percent threshold
    # above; this size cap used to default to 500MB, which on a unit that had
    # accumulated GBs would trigger emergency_cleanup and purge ~92% of history
    # down to 400MB. Raised to 20000MB so it only fires if the SD is genuinely
    # filling - routine thinning is time-based (full/hourly/daily days).
    "storage_max_mb": 20000,
}

# Stop thinning when this much wall-clock time has elapsed; progress persists
# in cleanup_state.json so the next nightly run resumes where this one left
# off. Must stay comfortably under the systemd unit's TimeoutStartSec (1800s).
BUDGET_SECONDS_DEFAULT = 1200

# Aggregated rows carry these raw_type markers (raw logger rows are e.g. 'f32')
HOURLY_MARK = "hourly_avg"
DAILY_MARK = "daily_avg"


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
    """Load cleanup state (last cleanup timestamp, thinning cursors)."""
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


def ensure_ts_index(con):
    """Range scans over ts drive every thinning slice; Swanwood already has
    this index (add_performance_indexes.sql), fresh installs get it here."""
    con.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts_pool ON readings(ts, pool)")


def _day_bounds(day):
    """Half-open string bounds for one day, matching both stored ts formats.

    Logger rows look like '2026-04-15T09:12:31+00:00', aggregated rows like
    '2026-04-15 12:00:00'. Bare 'YYYY-MM-DD' bounds compare correctly against
    both ('2026-04-15' < '2026-04-15 ...' < '2026-04-15T...' < '2026-04-16').
    """
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def aggregate_day(con, day, bucket_fmt, mark, dry_run=False):
    """Collapse one day of readings to per-bucket averages, set-based.

    bucket_fmt is a strftime format producing the bucket timestamp (hour or
    day). Returns the net number of rows removed. Idempotent: a day already
    at this granularity has one row per bucket and is skipped.
    """
    start, end = _day_bounds(day)

    total, groups = con.execute(
        """
        SELECT COALESCE(SUM(c), 0), COUNT(*) FROM (
            SELECT COUNT(*) AS c
            FROM readings
            WHERE ts >= ? AND ts < ? AND value IS NOT NULL
            GROUP BY strftime(?, ts), pool, host, point_label
        )
        """,
        (start, end, bucket_fmt),
    ).fetchone()

    if total == 0 or total == groups:
        return 0

    if dry_run:
        print(f"  {day}: would collapse {total} rows into {groups} {mark} rows")
        return total - groups

    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute(
            """
            CREATE TEMP TABLE _agg AS
            SELECT strftime(?, ts) AS bts, pool, host, point_label,
                   AVG(value) AS avg_value
            FROM readings
            WHERE ts >= ? AND ts < ? AND value IS NOT NULL
            GROUP BY bts, pool, host, point_label
            """,
            (bucket_fmt, start, end),
        )
        con.execute(
            "DELETE FROM readings WHERE ts >= ? AND ts < ? AND value IS NOT NULL",
            (start, end),
        )
        con.execute(
            """
            INSERT INTO readings (ts, pool, host, point_label, value, raw_type)
            SELECT bts, pool, host, point_label, avg_value, ? FROM _agg
            """,
            (mark,),
        )
        con.execute("DROP TABLE _agg")
        con.commit()
    except Exception:
        con.rollback()
        con.execute("DROP TABLE IF EXISTS _agg")
        raise

    removed = total - groups
    print(f"  {day}: collapsed {total} rows into {groups} {mark} rows")
    return removed


def thin_readings(con, settings, state, deadline, dry_run=False):
    """Walk day slices oldest-first, thinning per the retention policy.

    Days older than hourly_days go straight to daily averages (single pass);
    days between full_days and hourly_days go to hourly. Cursors in the state
    dict make each run resume where the previous one stopped.
    """
    today = date.today()
    hourly_cutoff = today - timedelta(days=settings.get("data_retention_full_days", 30))
    daily_cutoff = today - timedelta(days=settings.get("data_retention_hourly_days", 90))

    oldest_ts = con.execute("SELECT MIN(ts) FROM readings").fetchone()[0]
    if not oldest_ts:
        print("No readings to thin.")
        return 0
    oldest_day = date.fromisoformat(oldest_ts[:10])

    removed = 0
    budget_hit = False

    passes = [
        # (state cursor key, first day if no cursor, stop before, bucket, mark)
        ("daily_thinned_until", oldest_day, daily_cutoff, "%Y-%m-%d 12:00:00", DAILY_MARK),
        ("hourly_thinned_until", max(oldest_day, daily_cutoff), hourly_cutoff, "%Y-%m-%d %H:00:00", HOURLY_MARK),
    ]

    for key, first_day, stop_day, fmt, mark in passes:
        day = first_day
        if state.get(key):
            try:
                day = max(day, date.fromisoformat(state[key]))
            except ValueError:
                pass

        while day < stop_day:
            if time.monotonic() > deadline:
                print(f"  Time budget reached; resuming at {day} next run.")
                budget_hit = True
                break
            removed += aggregate_day(con, day, fmt, mark, dry_run)
            day += timedelta(days=1)
            if not dry_run:
                state[key] = day.isoformat()
                save_cleanup_state(state)
        if budget_hit:
            break

    print(f"Thinning removed {removed} rows this run{' (dry run)' if dry_run else ''}.")
    return removed


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


def run_cleanup(settings, dry_run=False, vacuum=False, budget_seconds=BUDGET_SECONDS_DEFAULT):
    """Run the full cleanup process."""
    if not POOL_DB_PATH.exists():
        print(f"Database not found: {POOL_DB_PATH}")
        return False

    deadline = time.monotonic() + budget_seconds

    storage_info = get_storage_info()
    print(f"Current DB size: {storage_info['db_size_mb']:.2f} MB")
    print(f"Disk usage: {storage_info['disk_used_percent']:.1f}%")

    # Connect to database. isolation_level=None -> autocommit, so the
    # per-day thinning transactions are managed explicitly (BEGIN IMMEDIATE)
    # and stay short - the logger writes every poll cycle and WAL mode only
    # parallelizes readers, not writers.
    con = sqlite3.connect(str(POOL_DB_PATH), timeout=60, isolation_level=None)

    try:
        stats = get_db_stats(con)
        print(f"Total rows: {stats.get('total_rows', 0):,}")
        print(f"Date range: {stats.get('oldest_ts', 'N/A')} to {stats.get('newest_ts', 'N/A')}")

        now = datetime.now()

        if not dry_run:
            ensure_ts_index(con)

        # Check for emergency cleanup first
        storage_threshold = settings.get("storage_threshold_percent", 80)
        storage_max_mb = settings.get("storage_max_mb", DEFAULTS["storage_max_mb"])

        if storage_info["disk_used_percent"] > storage_threshold:
            print(f"\n⚠️  Disk usage ({storage_info['disk_used_percent']:.1f}%) exceeds threshold ({storage_threshold}%)")
            emergency_cleanup(con, storage_max_mb * 0.7, dry_run)
        elif storage_info["db_size_mb"] > storage_max_mb:
            print(f"\n⚠️  DB size ({storage_info['db_size_mb']:.2f} MB) exceeds max ({storage_max_mb} MB)")
            emergency_cleanup(con, storage_max_mb * 0.8, dry_run)

        # Normal retention policy: day-sliced, budgeted, resumable thinning
        state = load_cleanup_state()
        thin_readings(con, settings, state, deadline, dry_run)

        # Delete data older than daily retention (sargable range, uses ts index)
        daily_days = settings.get("data_retention_daily_days", 365)
        delete_cutoff = (now - timedelta(days=daily_days)).strftime("%Y-%m-%d %H:%M:%S")
        delete_old_data(con, delete_cutoff, dry_run)

        # Optimize database
        if not dry_run:
            print("\nOptimizing database...")
            con.execute("ANALYZE")
            # VACUUM only on explicit request (--vacuum). It takes an EXCLUSIVE
            # lock for minutes on a multi-GB DB, which blocks the logger's
            # writes and trips its 120s systemd watchdog (kill+restart loop).
            # The nightly timer therefore never VACUUMs - SQLite reuses freed
            # pages in place, so the DB stops growing without the lock. Reclaim
            # disk space manually with --vacuum, run with the logger stopped.
            if vacuum:
                print("Running VACUUM (exclusive lock; this may take a while)...")
                con.execute("VACUUM")

        print("\n✓ Cleanup complete!")
        return True

    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Clean up and thin pool readings data")
    parser.add_argument("--force", action="store_true", help="Force cleanup regardless of schedule")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--vacuum", action="store_true", help="Reclaim freed space (exclusive lock - run with the logger stopped)")
    parser.add_argument("--budget-seconds", type=int, default=BUDGET_SECONDS_DEFAULT,
                        help="Wall-clock budget for thinning; progress resumes next run (default %(default)s)")
    args = parser.parse_args()

    print(f"=== Data Cleanup - {datetime.now().isoformat()} ===")

    settings = load_settings()

    if not settings.get("data_retention_enabled", True) and not args.force:
        print("Data retention is disabled. Use --force to run anyway.")
        return 0

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    success = run_cleanup(settings, args.dry_run, vacuum=args.vacuum,
                          budget_seconds=args.budget_seconds)

    if success and not args.dry_run:
        state = load_cleanup_state()
        state["last_cleanup_ts"] = datetime.now().isoformat()
        save_cleanup_state(state)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
