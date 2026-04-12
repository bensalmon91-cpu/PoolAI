#!/usr/bin/env python3
"""
Chunk Manager for PoolDash (Improved)
Now includes:
- Persistent failure tracking with staggered retries
- Health state integration for monitoring
- Force retry flag for on-demand uploads
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
import time
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
APP_DIR = Path("/opt/PoolAIssistant/app")
DATA_DIR = Path("/opt/PoolAIssistant/data")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
MAIN_DB = DATA_DIR / "pool_readings.sqlite3"
CHUNKS_DIR = DATA_DIR / "chunks"
CHUNK_TRACKER = CHUNKS_DIR / "chunk_status.json"
HEALTH_STATE_FILE = DATA_DIR / "health_state.json"
UPLOAD_STATE_FILE = CHUNKS_DIR / "upload_state.json"

# Chunk settings
TARGET_CHUNK_SIZE_MB = 50
MAX_CHUNK_SIZE_MB = 100
MIN_ROWS_FOR_CHUNK = 100

# Retry settings
MAX_RETRIES_PER_ATTEMPT = 3
RETRY_DELAYS = [10, 20, 40]
STAGGERED_RETRY_MINUTES = [30, 60, 120]


def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def load_settings():
    if not SETTINGS_FILE.exists():
        log(f"Settings file not found: {SETTINGS_FILE}", "ERROR")
        sys.exit(1)
    with open(SETTINGS_FILE) as f:
        data = json.load(f)
    return {
        'api_key': data.get('api_key') or data.get('remote_api_key', ''),
        'backend_url': data.get('backend_url') or data.get('remote_sync_url', ''),
        'device_id': data.get('device_id', ''),
        'device_alias': data.get('device_alias', ''),
    }


def load_upload_state():
    if UPLOAD_STATE_FILE.exists():
        try:
            with open(UPLOAD_STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {'failed_chunks': {}, 'total_failures': 0, 'last_success': None}


def save_upload_state(state):
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(UPLOAD_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def update_health_state(success, error_msg=None):
    state = {}
    if HEALTH_STATE_FILE.exists():
        try:
            with open(HEALTH_STATE_FILE) as f:
                state = json.load(f)
        except:
            pass
    now = datetime.now().isoformat()
    if success:
        state['last_upload_success'] = now
        state['last_upload_error'] = None
        state['consecutive_failures'] = 0
    else:
        state['last_upload_error'] = error_msg or "Upload failed"
        state['consecutive_failures'] = state.get('consecutive_failures', 0) + 1
        state['failed_uploads'] = state.get('failed_uploads', 0) + 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


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
    conn = sqlite3.connect(str(MAIN_DB), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def find_timestamp_column(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    for col in ['ts', 'timestamp', 'created_at', 'reading_time', 'datetime']:
        if col in columns:
            return col
    return None


def get_daily_stats(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    for table_name in tables:
        ts_col = find_timestamp_column(conn, table_name)
        if not ts_col:
            continue
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
                daily_stats.append({'date': row['day'], 'row_count': row['row_count']})
        if daily_stats:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
            sample_rows = cursor.fetchall()
            if sample_rows:
                avg_row_size = sum(len(str(col) if col else '') for row in sample_rows for col in row) / len(sample_rows)
                for stat in daily_stats:
                    stat['estimated_size'] = int(stat['row_count'] * avg_row_size)
            return table_name, ts_col, daily_stats
    return None, None, []


def calculate_chunk_periods(daily_stats, target_size_bytes):
    if not daily_stats:
        return []
    periods = []
    current_start = None
    current_size = 0
    current_rows = 0
    today = datetime.now().strftime('%Y-%m-%d')
    for stat in daily_stats:
        if stat['date'] >= today:
            continue
        if current_start is None:
            current_start = stat['date']
        current_size += stat.get('estimated_size', 0)
        current_rows += stat['row_count']
        raw_target = target_size_bytes * 5
        if current_size >= raw_target:
            periods.append({'start': current_start, 'end': stat['date'], 'estimated_rows': current_rows, 'estimated_raw_size': current_size})
            current_start = None
            current_size = 0
            current_rows = 0
    if current_start and current_rows >= MIN_ROWS_FOR_CHUNK:
        last_date = daily_stats[-1]['date'] if daily_stats[-1]['date'] < today else None
        if last_date:
            start_dt = datetime.strptime(current_start, '%Y-%m-%d')
            end_dt = datetime.strptime(last_date, '%Y-%m-%d')
            if (end_dt - start_dt).days >= 1:
                periods.append({'start': current_start, 'end': last_date, 'estimated_rows': current_rows, 'estimated_raw_size': current_size})
    return periods


def create_chunk(table_name, ts_col, start_date, end_date):
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunk_filename = f"{start_date}_to_{end_date}.db"
    chunk_path = CHUNKS_DIR / chunk_filename
    compressed_path = CHUNKS_DIR / f"{chunk_filename}.gz"
    if chunk_path.exists():
        chunk_path.unlink()
    if compressed_path.exists():
        compressed_path.unlink()
    conn_main = sqlite3.connect(str(MAIN_DB), timeout=60)
    conn_chunk = sqlite3.connect(str(chunk_path))
    try:
        cursor_main = conn_main.cursor()
        cursor_chunk = conn_chunk.cursor()
        cursor_main.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        create_sql = cursor_main.fetchone()[0]
        cursor_chunk.execute(create_sql)
        cursor_main.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor_main.fetchall()]
        cursor_main.execute(f"SELECT COUNT(*) FROM {table_name} WHERE date({ts_col}) >= ? AND date({ts_col}) <= ?", (start_date, end_date))
        total_rows = cursor_main.fetchone()[0]
        if total_rows < MIN_ROWS_FOR_CHUNK:
            conn_chunk.close()
            conn_main.close()
            if chunk_path.exists():
                chunk_path.unlink()
            return None
        BATCH_SIZE = 50000
        placeholders = ','.join(['?' for _ in columns])
        cursor_main.execute(f"SELECT * FROM {table_name} WHERE date({ts_col}) >= ? AND date({ts_col}) <= ?", (start_date, end_date))
        rows_processed = 0
        while True:
            batch = cursor_main.fetchmany(BATCH_SIZE)
            if not batch:
                break
            cursor_chunk.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", batch)
            rows_processed += len(batch)
            if rows_processed % 200000 == 0:
                log(f"  Processed {rows_processed:,}/{total_rows:,} rows...")
        conn_chunk.commit()
        conn_chunk.close()
        conn_main.close()
        original_size = chunk_path.stat().st_size
        with open(chunk_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        chunk_path.unlink()
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
        log(f"Error creating chunk: {e}", "ERROR")
        conn_main.close()
        try:
            conn_chunk.close()
        except:
            pass
        if chunk_path.exists():
            chunk_path.unlink()
        return None


def upload_chunk(chunk_info, settings, upload_state, period_key):
    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')
    if not api_key or not backend_url:
        log("Missing api_key or backend_url", "ERROR")
        return False
    upload_url = f"{backend_url}/api/upload_chunk.php"
    last_error = None
    for attempt in range(1, MAX_RETRIES_PER_ATTEMPT + 1):
        try:
            with open(chunk_info['path'], 'rb') as f:
                files = {'file': (chunk_info['filename'], f, 'application/gzip')}
                data = {'period_start': chunk_info['period_start'], 'period_end': chunk_info['period_end'], 'row_count': chunk_info['row_count'], 'original_size': chunk_info['original_size']}
                headers = {'X-API-Key': api_key}
                response = requests.post(upload_url, files=files, data=data, headers=headers, timeout=300)
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('ok'):
                        if period_key in upload_state['failed_chunks']:
                            del upload_state['failed_chunks'][period_key]
                        upload_state['last_success'] = datetime.now().isoformat()
                        save_upload_state(upload_state)
                        update_health_state(True)
                        return True
                    else:
                        last_error = result.get('error', 'Unknown error')
                        if 'api' in last_error.lower() or 'auth' in last_error.lower():
                            log(f"Auth error: {last_error}", "ERROR")
                            return False
                except json.JSONDecodeError:
                    last_error = f"Invalid JSON: {response.text[:100]}"
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:100]}"
        except requests.exceptions.Timeout:
            last_error = "Request timed out"
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {str(e)[:100]}"
        except Exception as e:
            last_error = f"Error: {str(e)[:100]}"
        log(f"Upload attempt {attempt}/{MAX_RETRIES_PER_ATTEMPT} failed: {last_error}", "WARNING")
        if attempt < MAX_RETRIES_PER_ATTEMPT:
            delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
            log(f"  Retrying in {delay}s...")
            time.sleep(delay)
    now = datetime.now()
    failed_info = upload_state['failed_chunks'].get(period_key, {'attempts': 0})
    failed_info['attempts'] = failed_info.get('attempts', 0) + 1
    failed_info['last_attempt'] = now.isoformat()
    failed_info['last_error'] = last_error
    attempt_idx = min(failed_info['attempts'] - 1, len(STAGGERED_RETRY_MINUTES) - 1)
    retry_minutes = STAGGERED_RETRY_MINUTES[attempt_idx]
    failed_info['next_retry'] = (now + timedelta(minutes=retry_minutes)).isoformat()
    upload_state['failed_chunks'][period_key] = failed_info
    upload_state['total_failures'] = upload_state.get('total_failures', 0) + 1
    save_upload_state(upload_state)
    update_health_state(False, last_error)
    log(f"Upload failed after {MAX_RETRIES_PER_ATTEMPT} attempts. Next retry in {retry_minutes}m", "ERROR")
    return False


def should_retry_chunk(upload_state, period_key):
    if period_key not in upload_state['failed_chunks']:
        return True
    failed_info = upload_state['failed_chunks'][period_key]
    next_retry = failed_info.get('next_retry')
    if not next_retry:
        return True
    try:
        next_retry_dt = datetime.fromisoformat(next_retry)
        return datetime.now() >= next_retry_dt
    except:
        return True


def get_server_chunks(settings):
    api_key = settings.get('api_key')
    backend_url = settings.get('backend_url', '').rstrip('/')
    if not api_key or not backend_url:
        return {}
    try:
        response = requests.get(f"{backend_url}/api/chunks_status.php", headers={'X-API-Key': api_key}, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result.get('chunks', {})
        return {}
    except Exception as e:
        log(f"Could not fetch server chunks: {e}", "WARNING")
        return {}


def create_all_chunks():
    log("Analyzing database...")
    if not MAIN_DB.exists():
        log(f"Database not found: {MAIN_DB}", "ERROR")
        return []
    conn = get_db_connection()
    table_name, ts_col, daily_stats = get_daily_stats(conn)
    conn.close()
    if not daily_stats:
        log("No data found")
        return []
    log(f"Found {len(daily_stats)} days of data in table '{table_name}'")
    log(f"Date range: {daily_stats[0]['date']} to {daily_stats[-1]['date']}")
    total_rows = sum(s['row_count'] for s in daily_stats)
    log(f"Total rows: {total_rows:,}")
    target_bytes = TARGET_CHUNK_SIZE_MB * 1024 * 1024
    periods = calculate_chunk_periods(daily_stats, target_bytes)
    log(f"Calculated {len(periods)} chunk periods (target: ~{TARGET_CHUNK_SIZE_MB}MB each)")
    tracker = load_chunk_tracker()
    created_chunks = []
    for period in periods:
        period_key = f"{period['start']}_{period['end']}"
        if period_key in tracker['chunks']:
            existing = tracker['chunks'][period_key]
            if Path(existing['path']).exists():
                log(f"  [{period['start']} to {period['end']}] Already exists, skipping")
                created_chunks.append(existing)
                continue
        est_rows = period['estimated_rows']
        log(f"  [{period['start']} to {period['end']}] Creating chunk (~{est_rows:,} rows)...")
        chunk_info = create_chunk(table_name, ts_col, period['start'], period['end'])
        if chunk_info:
            size_mb = chunk_info['compressed_size'] / 1024 / 1024
            log(f"    Done - {chunk_info['row_count']:,} rows, {size_mb:.1f}MB ({chunk_info['compression_ratio']}% compression)")
            tracker['chunks'][period_key] = chunk_info
            created_chunks.append(chunk_info)
        else:
            log("    Skipped (not enough data)")
    save_chunk_tracker(tracker)
    return created_chunks


def upload_pending_chunks(settings, delete_after_upload=True, force_retry=False):
    tracker = load_chunk_tracker()
    upload_state = load_upload_state()
    server_chunks = get_server_chunks(settings)
    pending = []
    skipped = 0
    for period_key, chunk_info in tracker['chunks'].items():
        if period_key in server_chunks:
            if server_chunks[period_key].get('checksum') == chunk_info.get('checksum'):
                if delete_after_upload:
                    chunk_path = Path(chunk_info['path'])
                    if chunk_path.exists():
                        chunk_path.unlink()
                        log(f"  Cleaned up already-uploaded chunk: {chunk_info['filename']}")
                continue
        if not Path(chunk_info['path']).exists():
            continue
        if not force_retry and not should_retry_chunk(upload_state, period_key):
            skipped += 1
            continue
        pending.append((period_key, chunk_info))
    if skipped > 0:
        log(f"Skipped {skipped} chunks (waiting for retry window)")
    if not pending:
        log("All chunks are already uploaded or waiting for retry!")
        return
    log(f"Uploading {len(pending)} pending chunks...")
    uploaded = 0
    for period_key, chunk_info in pending:
        period = f"{chunk_info['period_start']} to {chunk_info['period_end']}"
        size_mb = chunk_info['compressed_size'] / 1024 / 1024
        log(f"  [{period}] Uploading {size_mb:.1f}MB...")
        if upload_chunk(chunk_info, settings, upload_state, period_key):
            log(f"    Done")
            uploaded += 1
            if delete_after_upload:
                chunk_path = Path(chunk_info['path'])
                if chunk_path.exists():
                    chunk_path.unlink()
                    log(f"    -> Deleted local copy")
        else:
            log(f"    FAILED")
    log(f"Uploaded {uploaded}/{len(pending)} chunks")
    tracker['last_sync'] = datetime.now().isoformat()
    save_chunk_tracker(tracker)


def show_status():
    tracker = load_chunk_tracker()
    upload_state = load_upload_state()
    log("=== Chunk Status ===")
    if MAIN_DB.exists():
        size_gb = MAIN_DB.stat().st_size / 1024 / 1024 / 1024
        log(f"Database: {MAIN_DB} ({size_gb:.2f} GB)")
    if not tracker['chunks']:
        log("No chunks created yet.")
        return
    total_size = 0
    total_rows = 0
    log(f"Target chunk size: ~{TARGET_CHUNK_SIZE_MB}MB")
    log("")
    log("Local Chunks:")
    for period_key in sorted(tracker['chunks'].keys()):
        chunk = tracker['chunks'][period_key]
        exists = "OK" if Path(chunk['path']).exists() else "UPLOADED"
        size_mb = chunk['compressed_size'] / 1024 / 1024
        failure_info = ""
        if period_key in upload_state.get('failed_chunks', {}):
            failed = upload_state['failed_chunks'][period_key]
            failure_info = f" [FAILED x{failed['attempts']}]"
        log(f"  {chunk['period_start']} to {chunk['period_end']}: {chunk['row_count']:>12,} rows, {size_mb:>6.1f}MB [{exists}]{failure_info}")
        total_size += chunk['compressed_size']
        total_rows += chunk['row_count']
    log(f"Total: {len(tracker['chunks'])} chunks, {total_rows:,} rows, {total_size / 1024 / 1024:.1f}MB")
    if tracker.get('last_sync'):
        log(f"Last sync: {tracker['last_sync']}")
    failed_chunks = upload_state.get('failed_chunks', {})
    if failed_chunks:
        log(f"\nFailed chunks: {len(failed_chunks)}")
        for period_key, info in failed_chunks.items():
            log(f"  {period_key}: {info['attempts']} attempts, next: {info.get('next_retry', 'now')}")
    log("")
    log("Server Status:")
    settings = load_settings()
    server_chunks = get_server_chunks(settings)
    if server_chunks:
        log(f"  {len(server_chunks)} chunks on server")
        local_keys = set(tracker['chunks'].keys())
        server_keys = set(server_chunks.keys())
        not_uploaded = local_keys - server_keys
        if not_uploaded:
            log(f"  {len(not_uploaded)} chunks pending upload")
        else:
            log("  All chunks synced!")
    else:
        log("  Could not fetch server status")


def main():
    global TARGET_CHUNK_SIZE_MB
    parser = argparse.ArgumentParser(description='Manage data chunks for PoolDash')
    parser.add_argument('--create-only', action='store_true', help='Only create chunks')
    parser.add_argument('--upload-only', action='store_true', help='Only upload existing chunks')
    parser.add_argument('--status', action='store_true', help='Show chunk status')
    parser.add_argument('--keep-local', action='store_true', help='Keep local chunks after upload')
    parser.add_argument('--force-retry', action='store_true', help='Retry failed chunks immediately')
    parser.add_argument('--target-size', type=int, default=50, help='Target chunk size in MB (default: 50)')
    args = parser.parse_args()
    TARGET_CHUNK_SIZE_MB = args.target_size
    if args.status:
        show_status()
        return
    settings = load_settings()
    delete_after = not args.keep_local
    if args.upload_only:
        upload_pending_chunks(settings, delete_after_upload=delete_after, force_retry=args.force_retry)
    elif args.create_only:
        create_all_chunks()
    else:
        log("=== Creating Chunks ===")
        create_all_chunks()
        log("")
        log("=== Uploading Chunks ===")
        upload_pending_chunks(settings, delete_after_upload=delete_after, force_retry=args.force_retry)


if __name__ == '__main__':
    main()
