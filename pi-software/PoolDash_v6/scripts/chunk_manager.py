#!/usr/bin/env python3
"""
Chunk Manager for PoolDash
Creates compressed time-period archives from the pool readings database
and uploads them to the backend server.

Chunks by FILE SIZE (not time period) to handle varying data density.
Each chunk targets ~50MB compressed, rounded to whole days.
"""

import os
import sys
import json
import gzip
import shutil
import sqlite3
import hashlib
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
APP_DIR = Path("/opt/PoolAIssistant/app")
DATA_DIR = Path("/opt/PoolAIssistant/data")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
MAIN_DB = DATA_DIR / "pool_readings.sqlite3"
CHUNKS_DIR = DATA_DIR / "chunks"
CHUNK_TRACKER = CHUNKS_DIR / "chunk_status.json"

# Chunk settings
TARGET_CHUNK_SIZE_MB = 50  # Target compressed size per chunk
MAX_CHUNK_SIZE_MB = 100    # Maximum chunk size before forcing split
MIN_ROWS_FOR_CHUNK = 100


def load_settings():
    if not SETTINGS_FILE.exists():
        print(f"ERROR: Settings file not found: {SETTINGS_FILE}")
        sys.exit(1)
    with open(SETTINGS_FILE) as f:
        data = json.load(f)
    return {
        'api_key': data.get('api_key') or data.get('remote_api_key', ''),
        'backend_url': data.get('backend_url') or data.get('remote_sync_url', ''),
        'device_id': data.get('device_id', ''),
        'device_alias': data.get('device_alias', ''),
    }


def save_chunk_tracker(tracker):
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHUNK_TRACKER, 'w') as f:
        json.dump(tracker, f, indent=2)


def load_chunk_tracker():
    if CHUNK_TRACKER.exists():
        with open(CHUNK_TRACKER) as f:
            return json.load(f)
    return {"chunks": {}, "last_sync": None}


def get_db_connection():
    """Get database connection with proper settings."""
    conn = sqlite3.connect(str(MAIN_DB), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def find_timestamp_column(conn, table_name):
    """Find the timestamp column in a table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    for col in ['ts', 'timestamp', 'created_at', 'reading_time', 'datetime']:
        if col in columns:
            return col
    return None


def get_daily_stats(conn):
    """Get row counts and estimated sizes per day."""
    cursor = conn.cursor()

    # Find main readings table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]

    for table_name in tables:
        ts_col = find_timestamp_column(conn, table_name)
        if not ts_col:
            continue

        # Get daily stats
        cursor.execute(f"""
            SELECT date({ts_col}) as day, COUNT(*) as row_count
            FROM {table_name}
            WHERE {ts_col} IS NOT NULL
            GROUP BY date({ts_col})
            ORDER BY day
        """)

        daily_stats = []
        for row in cursor.fetchall():
            if row['day']:
                daily_stats.append({
                    'date': row['day'],
                    'row_count': row['row_count']
                })

        if daily_stats:
            # Estimate bytes per row (sample a few rows)
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
            sample_rows = cursor.fetchall()
            if sample_rows:
                # Rough estimate of row size
                avg_row_size = sum(len(str(col) if col else '') for row in sample_rows for col in row) / len(sample_rows)
                for stat in daily_stats:
                    stat['estimated_size'] = int(stat['row_count'] * avg_row_size)

            return table_name, ts_col, daily_stats

    return None, None, []


def calculate_chunk_periods(daily_stats, target_size_bytes):
    """Calculate chunk periods based on target size, rounded to whole days."""
    if not daily_stats:
        return []

    periods = []
    current_start = None
    current_size = 0
    current_rows = 0

    # Don't include today (still being written)
    today = datetime.now().strftime('%Y-%m-%d')

    for stat in daily_stats:
        if stat['date'] >= today:
            continue

        if current_start is None:
            current_start = stat['date']

        current_size += stat.get('estimated_size', 0)
        current_rows += stat['row_count']

        # Check if we've hit target size
        # Compression typically gives 80-90% reduction, so target raw size is larger
        raw_target = target_size_bytes * 5  # Assume ~80% compression

        if current_size >= raw_target:
            periods.append({
                'start': current_start,
                'end': stat['date'],
                'estimated_rows': current_rows,
                'estimated_raw_size': current_size
            })
            current_start = None
            current_size = 0
            current_rows = 0

    # Don't create a final partial period - wait for more data
    # Unless it's been more than 7 days
    if current_start and current_rows >= MIN_ROWS_FOR_CHUNK:
        last_date = daily_stats[-1]['date'] if daily_stats[-1]['date'] < today else None
        if last_date:
            start_dt = datetime.strptime(current_start, '%Y-%m-%d')
            end_dt = datetime.strptime(last_date, '%Y-%m-%d')
            if (end_dt - start_dt).days >= 1:  # At least 1 full day
                periods.append({
                    'start': current_start,
                    'end': last_date,
                    'estimated_rows': current_rows,
                    'estimated_raw_size': current_size
                })

    return periods


def create_chunk(table_name, ts_col, start_date, end_date):
    """Create a compressed chunk for the given date range."""
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    chunk_filename = f"{start_date}_to_{end_date}.db"
    chunk_path = CHUNKS_DIR / chunk_filename
    compressed_path = CHUNKS_DIR / f"{chunk_filename}.gz"

    # Remove old files if exist
    if chunk_path.exists():
        chunk_path.unlink()
    if compressed_path.exists():
        compressed_path.unlink()

    conn_main = sqlite3.connect(str(MAIN_DB), timeout=60)
    conn_chunk = sqlite3.connect(str(chunk_path))

    try:
        cursor_main = conn_main.cursor()
        cursor_chunk = conn_chunk.cursor()

        # Get table schema
        cursor_main.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        create_sql = cursor_main.fetchone()[0]
        cursor_chunk.execute(create_sql)

        # Get column names
        cursor_main.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor_main.fetchall()]

        # Copy rows in date range using streaming to avoid memory issues
        # First get count to check if we have enough data
        cursor_main.execute(f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE date({ts_col}) >= ? AND date({ts_col}) <= ?
        """, (start_date, end_date))
        total_rows = cursor_main.fetchone()[0]

        if total_rows < MIN_ROWS_FOR_CHUNK:
            conn_chunk.close()
            conn_main.close()
            if chunk_path.exists():
                chunk_path.unlink()
            return None

        # Stream data in batches to avoid memory exhaustion on Pi
        BATCH_SIZE = 50000  # Process 50K rows at a time
        placeholders = ','.join(['?' for _ in columns])

        cursor_main.execute(f"""
            SELECT * FROM {table_name}
            WHERE date({ts_col}) >= ? AND date({ts_col}) <= ?
        """, (start_date, end_date))

        rows_processed = 0
        while True:
            batch = cursor_main.fetchmany(BATCH_SIZE)
            if not batch:
                break
            cursor_chunk.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", batch)
            rows_processed += len(batch)
            if rows_processed % 200000 == 0:
                print(f"    Processed {rows_processed:,}/{total_rows:,} rows...", flush=True)

        # Verify we got all rows
        if rows_processed != total_rows:
            print(f"Warning: Expected {total_rows} rows but processed {rows_processed}")

        conn_chunk.commit()
        conn_chunk.close()
        conn_main.close()

        original_size = chunk_path.stat().st_size

        # Compress
        with open(chunk_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        chunk_path.unlink()

        # Calculate checksum in chunks to avoid memory issues
        sha256 = hashlib.sha256()
        with open(compressed_path, 'rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                sha256.update(block)
        checksum = sha256.hexdigest()

        compressed_size = compressed_path.stat().st_size

        return {
            'path': str(compressed_path),
            'filename': f"{chunk_filename}.gz",
            'period_start': start_date,
            'period_end': end_date,
            'row_count': total_rows,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'checksum': checksum,
            'compression_ratio': round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0
        }

    except Exception as e:
        print(f"Error creating chunk: {e}")
        conn_main.close()
        try:
            conn_chunk.close()
        except:
            pass
        if chunk_path.exists():
            chunk_path.unlink()
        return None


def upload_chunk(chunk_info, settings, max_retries=3, retry_delay=10):
    """Upload a chunk to the backend server with retry logic."""
    import time

    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')

    if not api_key or not backend_url:
        print("ERROR: Missing api_key or backend_url in settings")
        return False

    upload_url = f"{backend_url}/api/upload_chunk.php"

    for attempt in range(1, max_retries + 1):
        try:
            with open(chunk_info['path'], 'rb') as f:
                files = {'file': (chunk_info['filename'], f, 'application/gzip')}
                data = {
                    'period_start': chunk_info['period_start'],
                    'period_end': chunk_info['period_end'],
                    'row_count': chunk_info['row_count'],
                    'original_size': chunk_info['original_size']
                }
                headers = {'X-API-Key': api_key}

                response = requests.post(upload_url, files=files, data=data, headers=headers, timeout=300)

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return True
                else:
                    error_msg = result.get('error', 'Unknown error')
                    # Don't retry for client errors like invalid API key
                    if 'api' in error_msg.lower() or 'auth' in error_msg.lower():
                        print(f"Upload failed (auth): {error_msg}")
                        return False
                    print(f"Upload failed: {error_msg}")
            else:
                print(f"Upload failed with status {response.status_code}")

        except requests.exceptions.Timeout:
            print(f"Upload timed out (attempt {attempt}/{max_retries})")
        except requests.exceptions.ConnectionError:
            print(f"Connection error (attempt {attempt}/{max_retries})")
        except Exception as e:
            print(f"Upload error: {e} (attempt {attempt}/{max_retries})")

        # Retry if not last attempt
        if attempt < max_retries:
            wait = retry_delay * attempt  # Exponential backoff
            print(f"    Retrying in {wait}s...")
            time.sleep(wait)

    print(f"Upload failed after {max_retries} attempts")
    return False


def get_server_chunks(settings):
    """Get list of chunks already on server."""
    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')

    if not api_key or not backend_url:
        return {}

    try:
        response = requests.get(
            f"{backend_url}/api/chunks_status.php",
            headers={'X-API-Key': api_key},
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result.get('chunks', {})
        return {}
    except Exception as e:
        print(f"Warning: Could not fetch server chunks: {e}")
        return {}


def create_all_chunks():
    """Create chunks based on file size targets."""
    print("Analyzing database...")

    if not MAIN_DB.exists():
        print(f"Database not found: {MAIN_DB}")
        return []

    conn = get_db_connection()
    table_name, ts_col, daily_stats = get_daily_stats(conn)
    conn.close()

    if not daily_stats:
        print("No data found in database")
        return []

    print(f"Found {len(daily_stats)} days of data in table '{table_name}'")
    print(f"Date range: {daily_stats[0]['date']} to {daily_stats[-1]['date']}")

    total_rows = sum(s['row_count'] for s in daily_stats)
    print(f"Total rows: {total_rows:,}")

    # Calculate chunk periods based on target size
    target_bytes = TARGET_CHUNK_SIZE_MB * 1024 * 1024
    periods = calculate_chunk_periods(daily_stats, target_bytes)

    print(f"Calculated {len(periods)} chunk periods (target: ~{TARGET_CHUNK_SIZE_MB}MB each)")

    tracker = load_chunk_tracker()
    created_chunks = []

    for period in periods:
        period_key = f"{period['start']}_{period['end']}"

        # Check if already exists
        if period_key in tracker['chunks']:
            existing = tracker['chunks'][period_key]
            if Path(existing['path']).exists():
                print(f"  [{period['start']} to {period['end']}] Already exists, skipping")
                created_chunks.append(existing)
                continue

        est_rows = period['estimated_rows']
        print(f"  [{period['start']} to {period['end']}] Creating chunk (~{est_rows:,} rows)...", end=" ", flush=True)

        chunk_info = create_chunk(table_name, ts_col, period['start'], period['end'])

        if chunk_info:
            size_mb = chunk_info['compressed_size'] / 1024 / 1024
            print(f"Done - {chunk_info['row_count']:,} rows, {size_mb:.1f}MB ({chunk_info['compression_ratio']}% compression)")
            tracker['chunks'][period_key] = chunk_info
            created_chunks.append(chunk_info)
        else:
            print("Skipped (not enough data)")

    save_chunk_tracker(tracker)
    return created_chunks


def upload_pending_chunks(settings, delete_after_upload=True):
    """Upload chunks that haven't been uploaded yet."""
    tracker = load_chunk_tracker()
    server_chunks = get_server_chunks(settings)

    pending = []
    for period_key, chunk_info in tracker['chunks'].items():
        if period_key in server_chunks:
            if server_chunks[period_key].get('checksum') == chunk_info.get('checksum'):
                # Already uploaded - delete local copy if exists
                if delete_after_upload:
                    chunk_path = Path(chunk_info['path'])
                    if chunk_path.exists():
                        chunk_path.unlink()
                        print(f"  Cleaned up already-uploaded chunk: {chunk_info['filename']}")
                continue
        if Path(chunk_info['path']).exists():
            pending.append((period_key, chunk_info))

    if not pending:
        print("All chunks are already uploaded!")
        return

    print(f"Uploading {len(pending)} pending chunks...")

    uploaded = 0
    for period_key, chunk_info in pending:
        period = f"{chunk_info['period_start']} to {chunk_info['period_end']}"
        size_mb = chunk_info['compressed_size'] / 1024 / 1024
        print(f"  [{period}] Uploading {size_mb:.1f}MB...", end=" ", flush=True)

        if upload_chunk(chunk_info, settings):
            print("Done")
            uploaded += 1
            # Delete local chunk after successful upload
            if delete_after_upload:
                chunk_path = Path(chunk_info['path'])
                if chunk_path.exists():
                    chunk_path.unlink()
                    print(f"    -> Deleted local copy")
        else:
            print("FAILED")

    print(f"\nUploaded {uploaded}/{len(pending)} chunks")

    tracker['last_sync'] = datetime.now().isoformat()
    save_chunk_tracker(tracker)


def show_status():
    """Show current chunk status."""
    tracker = load_chunk_tracker()

    print("=== Chunk Status ===\n")

    # Show database info
    if MAIN_DB.exists():
        size_gb = MAIN_DB.stat().st_size / 1024 / 1024 / 1024
        print(f"Database: {MAIN_DB}")
        print(f"Size: {size_gb:.2f} GB\n")

    if not tracker['chunks']:
        print("No chunks created yet.")
        print(f"\nRun 'python3 {__file__}' to create and upload chunks.")
        return

    total_size = 0
    total_rows = 0

    print(f"Target chunk size: ~{TARGET_CHUNK_SIZE_MB}MB compressed")
    print("\nLocal Chunks:")
    print("-" * 90)

    for period_key in sorted(tracker['chunks'].keys()):
        chunk = tracker['chunks'][period_key]
        exists = "OK" if Path(chunk['path']).exists() else "MISSING"
        size_mb = chunk['compressed_size'] / 1024 / 1024
        print(f"  {chunk['period_start']} to {chunk['period_end']}: "
              f"{chunk['row_count']:>12,} rows, {size_mb:>6.1f}MB [{exists}]")
        total_size += chunk['compressed_size']
        total_rows += chunk['row_count']

    print("-" * 90)
    print(f"Total: {len(tracker['chunks'])} chunks, {total_rows:,} rows, {total_size / 1024 / 1024:.1f}MB compressed")

    if tracker.get('last_sync'):
        print(f"Last sync: {tracker['last_sync']}")

    # Check server
    print("\nServer Status:")
    settings = load_settings()
    server_chunks = get_server_chunks(settings)

    if server_chunks:
        print(f"  {len(server_chunks)} chunks on server")
        local_keys = set(tracker['chunks'].keys())
        server_keys = set(server_chunks.keys())
        not_uploaded = local_keys - server_keys
        if not_uploaded:
            print(f"  {len(not_uploaded)} chunks pending upload")
        else:
            print("  All chunks synced!")
    else:
        print("  Could not fetch server status (check API key/URL)")


def main():
    global TARGET_CHUNK_SIZE_MB

    parser = argparse.ArgumentParser(description='Manage data chunks for PoolDash')
    parser.add_argument('--create-only', action='store_true', help='Only create chunks')
    parser.add_argument('--upload-only', action='store_true', help='Only upload existing chunks')
    parser.add_argument('--status', action='store_true', help='Show chunk status')
    parser.add_argument('--keep-local', action='store_true', help='Keep local chunks after upload')
    parser.add_argument('--target-size', type=int, default=50,
                        help='Target chunk size in MB (default: 50)')
    args = parser.parse_args()

    TARGET_CHUNK_SIZE_MB = args.target_size

    if args.status:
        show_status()
        return

    settings = load_settings()
    delete_after = not args.keep_local

    if args.upload_only:
        upload_pending_chunks(settings, delete_after_upload=delete_after)
    elif args.create_only:
        create_all_chunks()
    else:
        print("=== Creating Chunks ===")
        create_all_chunks()
        print("\n=== Uploading Chunks ===")
        upload_pending_chunks(settings, delete_after_upload=delete_after)


if __name__ == '__main__':
    main()
