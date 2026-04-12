#!/usr/bin/env python3
"""
Migrate maintenance logs from separate database to pool_readings.sqlite3.

This script:
1. Creates maintenance_logs table in pool_readings.sqlite3
2. Copies all rows from maintenance_logs.sqlite3 (if it exists)
3. Renames old file to .sqlite3.migrated as backup

This enables:
- Automatic backup via existing sync infrastructure
- AI correlation of maintenance events with readings
- Single database for all pool data

Usage:
    python migrate_maintenance_logs.py              # Run migration
    python migrate_maintenance_logs.py --dry-run    # Preview without changes
    python migrate_maintenance_logs.py --force      # Re-run even if already done
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Default paths (matching config.py)
DATA_DIR = Path("/opt/PoolAIssistant/data")
POOL_DB_PATH = DATA_DIR / "pool_readings.sqlite3"
MAINT_DB_PATH = DATA_DIR / "maintenance_logs.sqlite3"


def get_paths():
    """Get database paths, supporting both production and development environments."""
    pool_db = os.getenv("POOL_DB_PATH") or os.getenv("POOLDB")
    if pool_db:
        pool_db = Path(pool_db)
    elif DATA_DIR.exists():
        pool_db = POOL_DB_PATH
    else:
        pool_db = Path.cwd() / "pool_readings.sqlite3"

    maint_db = os.getenv("MAINT_DB_PATH")
    if maint_db:
        maint_db = Path(maint_db)
    elif DATA_DIR.exists():
        maint_db = MAINT_DB_PATH
    else:
        maint_db = Path.cwd() / "maintenance_logs.sqlite3"

    return pool_db, maint_db


def ensure_maintenance_table(pool_db_path: Path) -> bool:
    """Create maintenance_logs table in pool_readings database."""
    print(f"Ensuring maintenance_logs table in {pool_db_path}...")

    conn = sqlite3.connect(str(pool_db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                pool TEXT NOT NULL,
                action TEXT NOT NULL,
                note TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_maint_timestamp ON maintenance_logs(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_maint_pool_action_time ON maintenance_logs(pool, action, timestamp)")
        conn.commit()
        print("  Table and indexes created/verified.")
        return True
    except Exception as e:
        print(f"  ERROR creating table: {e}")
        return False
    finally:
        conn.close()


def count_rows(db_path: Path, table: str) -> int:
    """Count rows in a table."""
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def migrate_data(pool_db_path: Path, maint_db_path: Path, dry_run: bool = False) -> tuple[int, str]:
    """
    Migrate maintenance logs from separate database to pool_readings.

    Returns: (rows_migrated, error_message or None)
    """
    if not maint_db_path.exists():
        return 0, None

    # Check if old database has any data
    old_count = count_rows(maint_db_path, "maintenance_logs")
    if old_count == 0:
        print(f"  No data in {maint_db_path}, nothing to migrate.")
        return 0, None

    print(f"  Found {old_count} rows to migrate from {maint_db_path}")

    if dry_run:
        print("  [DRY RUN] Would migrate data but not actually doing it.")
        return old_count, None

    # Connect to both databases
    try:
        old_conn = sqlite3.connect(str(maint_db_path))
        old_conn.row_factory = sqlite3.Row
        new_conn = sqlite3.connect(str(pool_db_path))

        # Check if pool_db already has maintenance data
        existing_count = count_rows(pool_db_path, "maintenance_logs")
        if existing_count > 0:
            print(f"  WARNING: Target database already has {existing_count} maintenance rows.")
            print("  Skipping duplicate entries based on timestamp+pool+action...")

        # Fetch all old rows
        rows = old_conn.execute("""
            SELECT timestamp, pool, action, note FROM maintenance_logs
            ORDER BY timestamp
        """).fetchall()

        # Insert into new database, avoiding duplicates
        inserted = 0
        for row in rows:
            # Check for existing entry with same timestamp+pool+action
            exists = new_conn.execute("""
                SELECT 1 FROM maintenance_logs
                WHERE timestamp = ? AND pool = ? AND action = ?
                LIMIT 1
            """, (row["timestamp"], row["pool"], row["action"])).fetchone()

            if not exists:
                new_conn.execute("""
                    INSERT INTO maintenance_logs (timestamp, pool, action, note)
                    VALUES (?, ?, ?, ?)
                """, (row["timestamp"], row["pool"], row["action"], row["note"]))
                inserted += 1

        new_conn.commit()
        old_conn.close()
        new_conn.close()

        print(f"  Migrated {inserted} rows (skipped {old_count - inserted} duplicates).")
        return inserted, None

    except Exception as e:
        return 0, str(e)


def backup_old_database(maint_db_path: Path, dry_run: bool = False) -> bool:
    """Rename old maintenance database to .migrated backup."""
    if not maint_db_path.exists():
        return True

    backup_path = maint_db_path.with_suffix(".sqlite3.migrated")
    print(f"  Backing up {maint_db_path.name} to {backup_path.name}...")

    if dry_run:
        print("  [DRY RUN] Would rename but not actually doing it.")
        return True

    try:
        # If backup already exists, add timestamp
        if backup_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = maint_db_path.with_suffix(f".sqlite3.migrated.{timestamp}")

        shutil.move(str(maint_db_path), str(backup_path))
        print(f"  Old database backed up to {backup_path.name}")
        return True
    except Exception as e:
        print(f"  ERROR backing up: {e}")
        return False


def check_migration_needed(pool_db_path: Path, maint_db_path: Path) -> tuple[bool, str]:
    """Check if migration is needed and return status message."""
    if not maint_db_path.exists():
        # Check for .migrated backup to indicate previous migration
        migrated_path = maint_db_path.with_suffix(".sqlite3.migrated")
        if migrated_path.exists():
            return False, "Migration already completed (backup file exists)."
        return False, "No separate maintenance database found (may be fresh install)."

    # Check if maintenance_logs table exists in pool_db
    if pool_db_path.exists():
        try:
            conn = sqlite3.connect(str(pool_db_path))
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            conn.close()
            if "maintenance_logs" in tables:
                maint_count = count_rows(maint_db_path, "maintenance_logs")
                pool_maint_count = count_rows(pool_db_path, "maintenance_logs")
                if pool_maint_count >= maint_count and maint_count > 0:
                    return False, f"Migration may be complete (pool_db has {pool_maint_count} rows, old has {maint_count})."
        except Exception:
            pass

    return True, "Migration needed."


def main():
    parser = argparse.ArgumentParser(
        description="Migrate maintenance logs to pool_readings database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run migration even if it appears complete"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Maintenance Logs Migration")
    print("=" * 60)
    print()

    pool_db, maint_db = get_paths()
    print(f"Pool readings DB: {pool_db}")
    print(f"Maintenance DB:   {maint_db}")
    print()

    # Check if migration is needed
    needed, status = check_migration_needed(pool_db, maint_db)
    print(f"Status: {status}")

    if not needed and not args.force:
        print("Migration not needed. Use --force to run anyway.")
        return 0

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    print()
    print("Step 1: Ensure maintenance_logs table exists in pool_readings...")
    if not args.dry_run:
        if not ensure_maintenance_table(pool_db):
            print("FAILED to create table. Aborting.")
            return 1
    else:
        print("  [DRY RUN] Would create table.")

    print()
    print("Step 2: Migrate data from old database...")
    rows_migrated, error = migrate_data(pool_db, maint_db, args.dry_run)
    if error:
        print(f"ERROR during migration: {error}")
        return 1

    print()
    print("Step 3: Backup old database...")
    if rows_migrated > 0 or args.force:
        if not backup_old_database(maint_db, args.dry_run):
            print("WARNING: Could not backup old database, but migration succeeded.")
    else:
        print("  Skipping backup (no data was migrated).")

    print()
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN COMPLETE - No changes made")
    else:
        print("MIGRATION COMPLETE")
        if rows_migrated > 0:
            print(f"  {rows_migrated} maintenance log entries migrated")
        print("  Maintenance logs are now stored in pool_readings.sqlite3")
        print("  They will be synced to the server for AI analysis and backup")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
