#!/usr/bin/env python3
"""
Database Optimization Script for PoolAIssistant
Adds critical indexes and optimizes database for large datasets
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta, timezone

def get_db_path():
    """Find the pool readings database"""
    paths = [
        "/opt/PoolAIssistant/data/pool_readings.sqlite3",
        os.path.join(os.getcwd(), "pool_readings.sqlite3"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def analyze_database(db_path):
    """Analyze current database state"""
    print(f"\n{'='*60}")
    print("DATABASE ANALYSIS")
    print(f"{'='*60}")

    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row

    # Get file size
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"Database size: {size_mb:.2f} MB")

    # Get row count
    try:
        row_count = con.execute("SELECT COUNT(*) as cnt FROM readings").fetchone()["cnt"]
        print(f"Total rows: {row_count:,}")
    except Exception as e:
        print(f"Could not count rows: {e}")
        row_count = 0

    # Get date range
    try:
        date_range = con.execute("""
            SELECT
                MIN(ts) as earliest,
                MAX(ts) as latest
            FROM readings
        """).fetchone()
        print(f"Date range: {date_range['earliest']} to {date_range['latest']}")
    except Exception as e:
        print(f"Could not get date range: {e}")

    # Get existing indexes
    indexes = con.execute("""
        SELECT name, sql
        FROM sqlite_master
        WHERE type='index' AND tbl_name='readings'
    """).fetchall()

    print(f"\nExisting indexes:")
    if indexes:
        for idx in indexes:
            print(f"  - {idx['name']}: {idx['sql'] or '(implicit)'}")
    else:
        print("  None")

    # Get distinct pools/hosts
    try:
        pools = con.execute("SELECT DISTINCT pool FROM readings WHERE pool IS NOT NULL").fetchall()
        print(f"\nPools: {[p['pool'] for p in pools]}")

        hosts = con.execute("SELECT DISTINCT host FROM readings WHERE host IS NOT NULL").fetchall()
        print(f"Hosts: {[h['host'] for h in hosts]}")
    except Exception as e:
        print(f"Could not get pools/hosts: {e}")

    con.close()
    print(f"{'='*60}\n")
    return size_mb, row_count

def create_optimized_indexes(db_path, force=False):
    """Create optimized indexes for performance"""
    print(f"\n{'='*60}")
    print("CREATING OPTIMIZED INDEXES")
    print(f"{'='*60}\n")

    con = sqlite3.connect(db_path, timeout=60)

    # Check existing indexes
    existing = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='readings'"
    ).fetchall()}

    indexes_to_create = [
        # Critical index for charts queries (pool + label + time range)
        ("idx_readings_pool_label_ts", "CREATE INDEX IF NOT EXISTS idx_readings_pool_label_ts ON readings(pool, point_label, ts)"),

        # Index for settings page DISTINCT host query
        ("idx_readings_host", "CREATE INDEX IF NOT EXISTS idx_readings_host ON readings(host)"),

        # Composite index for time-based filtering
        ("idx_readings_ts_pool", "CREATE INDEX IF NOT EXISTS idx_readings_ts_pool ON readings(ts, pool)"),
    ]

    created_count = 0
    for idx_name, idx_sql in indexes_to_create:
        if idx_name in existing and not force:
            print(f"✓ Index already exists: {idx_name}")
        else:
            print(f"Creating index: {idx_name}...")
            try:
                start = datetime.now()
                con.execute(idx_sql)
                con.commit()
                elapsed = (datetime.now() - start).total_seconds()
                print(f"  ✓ Created in {elapsed:.1f}s")
                created_count += 1
            except Exception as e:
                print(f"  ✗ Failed: {e}")

    # Run ANALYZE to update statistics
    print("\nUpdating query planner statistics...")
    try:
        con.execute("ANALYZE")
        con.commit()
        print("  ✓ ANALYZE complete")
    except Exception as e:
        print(f"  ✗ ANALYZE failed: {e}")

    con.close()
    print(f"\n{'='*60}")
    print(f"Created {created_count} new index(es)")
    print(f"{'='*60}\n")

def vacuum_database(db_path):
    """Vacuum and optimize database"""
    print(f"\n{'='*60}")
    print("VACUUMING DATABASE")
    print(f"{'='*60}\n")

    print("This may take several minutes for large databases...")
    print("Press Ctrl+C to skip (not recommended)\n")

    try:
        con = sqlite3.connect(db_path, timeout=300)
        start = datetime.now()
        con.execute("VACUUM")
        con.commit()
        con.close()
        elapsed = (datetime.now() - start).total_seconds()
        print(f"✓ VACUUM complete in {elapsed:.1f}s")
        print("  Database file has been optimized and compacted")
    except KeyboardInterrupt:
        print("\n✗ VACUUM cancelled by user")
    except Exception as e:
        print(f"✗ VACUUM failed: {e}")

    print(f"\n{'='*60}\n")

def cleanup_old_data(db_path, keep_days=90, dry_run=True):
    """Optional: Remove old data to reduce database size"""
    print(f"\n{'='*60}")
    print(f"DATA CLEANUP ({'DRY RUN' if dry_run else 'LIVE'})")
    print(f"{'='*60}\n")

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"Keeping data from: {cutoff_iso} onwards ({keep_days} days)")

    con = sqlite3.connect(db_path, timeout=60)

    # Count rows to delete
    try:
        old_count = con.execute(
            "SELECT COUNT(*) as cnt FROM readings WHERE ts < ?",
            (cutoff_iso,)
        ).fetchone()[0]

        total_count = con.execute("SELECT COUNT(*) as cnt FROM readings").fetchone()[0]

        print(f"\nRows older than {keep_days} days: {old_count:,} ({old_count/total_count*100:.1f}%)")
        print(f"Rows to keep: {total_count - old_count:,} ({(total_count-old_count)/total_count*100:.1f}%)")

        if old_count == 0:
            print("\n✓ No old data to clean up")
            con.close()
            return

        if dry_run:
            print("\n[DRY RUN] Would delete these rows. Run with --cleanup-data to actually delete.")
        else:
            print(f"\nDeleting {old_count:,} old rows...")
            start = datetime.now()
            con.execute("DELETE FROM readings WHERE ts < ?", (cutoff_iso,))
            con.commit()
            elapsed = (datetime.now() - start).total_seconds()
            print(f"✓ Deleted in {elapsed:.1f}s")
            print("  Run VACUUM to reclaim disk space")

    except Exception as e:
        print(f"✗ Cleanup failed: {e}")
    finally:
        con.close()

    print(f"\n{'='*60}\n")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Optimize PoolAIssistant database for performance")
    parser.add_argument("--db-path", help="Path to database (auto-detect if not specified)")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM to compact database")
    parser.add_argument("--cleanup-data", type=int, metavar="DAYS",
                       help="Delete data older than DAYS (e.g., --cleanup-data 90)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be deleted without actually deleting (use with --cleanup-data)")
    parser.add_argument("--force-reindex", action="store_true",
                       help="Drop and recreate all indexes")
    args = parser.parse_args()

    # Find database
    db_path = args.db_path or get_db_path()
    if not db_path:
        print("ERROR: Could not find database file")
        print("Searched:")
        print("  - /opt/PoolAIssistant/data/pool_readings.sqlite3")
        print("  - ./pool_readings.sqlite3")
        print("\nSpecify path with --db-path")
        sys.exit(1)

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at: {db_path}")
        sys.exit(1)

    print(f"\nOptimizing database: {db_path}")

    # Backup reminder
    print(f"\n{'='*60}")
    print("IMPORTANT: Backup your database before optimization!")
    print(f"{'='*60}")
    print("\nCreate backup:")
    print(f"  cp {db_path} {db_path}.backup")
    print()

    try:
        response = input("Continue with optimization? (yes/no): ").strip().lower()
        if response != "yes":
            print("Cancelled.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    # Analyze current state
    size_mb, row_count = analyze_database(db_path)

    # Create optimized indexes
    create_optimized_indexes(db_path, force=args.force_reindex)

    # Optional: Cleanup old data
    if args.cleanup_data:
        cleanup_old_data(db_path, keep_days=args.cleanup_data, dry_run=args.dry_run)

    # Optional: Vacuum
    if args.vacuum:
        vacuum_database(db_path)

    # Final analysis
    print("\nFinal state:")
    analyze_database(db_path)

    print(f"\n{'='*60}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'='*60}\n")

    print("Next steps:")
    print("1. Restart services: sudo systemctl restart poolaissistant_logger poolaissistant_ui")
    print("2. Test performance: Navigate to Charts and Settings pages")
    print("3. Monitor logs: journalctl -u poolaissistant_ui -f")
    print()

    if not args.vacuum:
        print("TIP: Run with --vacuum to compact database and reclaim space")

    if row_count > 1000000:
        print("TIP: Consider --cleanup-data 90 to keep only recent data (faster queries)")

    print()

if __name__ == "__main__":
    main()
