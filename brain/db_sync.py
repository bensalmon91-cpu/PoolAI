"""
PoolAIssistant Brain - Database Sync Tool
Downloads chunk files from the server and assembles them into a local SQLite database.

Features:
- Downloads chunks via HTTP API (primary) or FTP (fallback)
- Incremental merging: only new chunks are merged, not rebuilt from scratch
- Tracks both downloaded AND merged chunks separately
- Cleans up decompressed .db files after merge (keeps .gz for backup)

Usage:
    python db_sync.py              # Normal incremental sync
    python db_sync.py --rebuild    # Force full rebuild from all chunks
    python db_sync.py --cleanup    # Delete chunks from server
    python db_sync.py --status     # Show sync status
"""

import os
import sys
import json
import gzip
import sqlite3
import logging
import tempfile
import shutil
import requests
from datetime import datetime
from pathlib import Path
from ftplib import FTP

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ChunkSyncer:
    """Downloads and assembles chunk files from the server."""

    def __init__(self):
        self.api_url = os.getenv('API_URL', 'https://poolaissistant.modprojects.co.uk')
        self.api_key = os.getenv('API_KEY', '')
        self.ftp_config = {
            'host': os.getenv('SFTP_HOST', 'ftp.modprojects.co.uk'),
            'port': int(os.getenv('SFTP_PORT', 21)),
            'user': os.getenv('SFTP_USER', ''),
            'password': os.getenv('SFTP_PASSWORD', '')
        }
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './output'))
        self.chunks_dir = Path(os.getenv('LOCAL_CHUNKS_DIR', './data/chunks'))
        self.state_file = self.chunks_dir / 'sync_state.json'
        self.delete_after_download = os.getenv('DELETE_AFTER_DOWNLOAD', 'true').lower() == 'true'
        self.cleanup_after_merge = os.getenv('CLEANUP_AFTER_MERGE', 'true').lower() == 'true'

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict:
        """Load sync state from file."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return {
            'downloaded_chunks': [],  # Chunks downloaded from server
            'merged_chunks': [],      # Chunks already merged into output DB
            'last_sync': None,
            'last_merge': None,
            'output_row_count': 0
        }

    def save_state(self, state: dict):
        """Save sync state to file."""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def fetch_chunk_list(self) -> list:
        """Fetch list of available chunks from API, falling back to FTP if API fails."""
        # Try API first
        try:
            response = requests.get(
                f"{self.api_url}/api/list_chunks.php",
                headers={'X-API-Key': self.api_key},
                timeout=30
            )
            data = response.json()
            if data.get('ok'):
                logger.info(f"Found {data['chunk_count']} chunks for {data['device_name']}")
                return data['chunks']
            else:
                logger.warning(f"API error: {data.get('error')}, falling back to FTP")
        except Exception as e:
            logger.warning(f"API failed: {e}, falling back to FTP")

        # Fallback: list chunks directly via FTP
        return self._fetch_chunk_list_ftp()

    def _fetch_chunk_list_ftp(self) -> list:
        """Fetch chunk list directly from FTP server."""
        try:
            ftp = FTP()
            ftp.connect(self.ftp_config['host'], self.ftp_config['port'], timeout=60)
            ftp.login(self.ftp_config['user'], self.ftp_config['password'])

            # Navigate to chunks directory
            ftp.cwd('/data/chunks/2')

            # Get all chunk files
            files = [f for f in ftp.nlst() if f.endswith('.db.gz')]
            ftp.quit()

            if not files:
                logger.info("No chunks found on FTP server")
                return []

            # Build chunk info from filenames
            chunks = []
            for filename in files:
                chunks.append({
                    'chunk_filename': filename,
                    'ftp_path': f'/data/chunks/2/{filename}',
                    'period_start': filename.split('_to_')[0] if '_to_' in filename else 'unknown',
                    'period_end': filename.split('_to_')[1].split('_')[0] if '_to_' in filename else 'unknown'
                })

            logger.info(f"Found {len(chunks)} chunks via FTP")
            return chunks

        except Exception as e:
            logger.error(f"FTP chunk list failed: {e}")
            return []

    def download_chunk(self, chunk: dict) -> Path:
        """Download a chunk file via HTTP API (primary) or FTP (fallback)."""
        filename = chunk['chunk_filename']
        local_path = self.chunks_dir / filename

        if local_path.exists():
            logger.info(f"  Chunk already exists locally: {filename}")
            return local_path

        # Try HTTP API download first (if download_url available)
        if chunk.get('download_url'):
            result = self._download_chunk_http(chunk, local_path)
            if result:
                return result

        # Fallback to FTP
        return self._download_chunk_ftp(chunk, local_path)

    def _download_chunk_http(self, chunk: dict, local_path: Path) -> Path:
        """Download chunk via HTTP API."""
        filename = chunk['chunk_filename']
        download_url = chunk.get('download_url', '')

        if not download_url:
            return None

        try:
            url = f"{self.api_url}{download_url}"
            response = requests.get(
                url,
                headers={'X-API-Key': self.api_key},
                timeout=300,
                stream=True
            )

            if response.status_code != 200:
                logger.warning(f"  HTTP download failed ({response.status_code}): {filename}")
                return None

            # Save to file
            with open(local_path, 'wb') as f:
                for chunk_data in response.iter_content(chunk_size=65536):
                    f.write(chunk_data)

            size_mb = local_path.stat().st_size / 1024 / 1024
            logger.info(f"  Downloaded (HTTP): {filename} ({size_mb:.1f}MB)")
            return local_path

        except Exception as e:
            logger.warning(f"  HTTP download failed for {filename}: {e}")
            if local_path.exists():
                local_path.unlink()
            return None

    def _download_chunk_ftp(self, chunk: dict, local_path: Path) -> Path:
        """Download chunk via FTP (fallback method)."""
        filename = chunk['chunk_filename']
        ftp_path = chunk.get('ftp_path', '')

        if not ftp_path:
            logger.error(f"  No FTP path for {filename}")
            return None

        try:
            ftp = FTP()
            ftp.connect(self.ftp_config['host'], self.ftp_config['port'], timeout=60)
            ftp.login(self.ftp_config['user'], self.ftp_config['password'])

            # Download file
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {ftp_path}', f.write)

            size_mb = local_path.stat().st_size / 1024 / 1024
            logger.info(f"  Downloaded (FTP): {filename} ({size_mb:.1f}MB)")

            # Delete from server after successful download
            if self.delete_after_download:
                try:
                    ftp.delete(ftp_path)
                    logger.info(f"  Deleted from server: {filename}")
                except Exception as e:
                    logger.warning(f"  Failed to delete from server: {filename} - {e}")

            ftp.quit()
            return local_path

        except Exception as e:
            logger.error(f"  FTP download failed for {filename}: {e}")
            if local_path.exists():
                local_path.unlink()
            return None

    def _delete_from_ftp(self, ftp_path: str, filename: str):
        """Delete a file from the FTP server."""
        try:
            ftp = FTP()
            ftp.connect(self.ftp_config['host'], self.ftp_config['port'], timeout=60)
            ftp.login(self.ftp_config['user'], self.ftp_config['password'])
            ftp.delete(ftp_path)
            ftp.quit()
            logger.info(f"  Deleted from server: {filename}")
        except Exception as e:
            logger.warning(f"  Failed to delete from server: {filename} - {e}")

    def cleanup_server(self):
        """Delete all chunks from the server to free up space (FTP method)."""
        logger.info("=" * 50)
        logger.info("Cleaning up chunks from server")
        logger.info("=" * 50)

        try:
            ftp = FTP()
            ftp.connect(self.ftp_config['host'], self.ftp_config['port'], timeout=60)
            ftp.login(self.ftp_config['user'], self.ftp_config['password'])

            # Navigate to chunks directory (device ID 2)
            ftp.cwd('/data/chunks/2')

            # Get all chunk files
            files = [f for f in ftp.nlst() if f.endswith('.db.gz')]

            if not files:
                logger.info("No chunks on server")
                ftp.quit()
                return

            logger.info(f"Found {len(files)} chunks to delete from server")

            deleted = 0
            for filename in sorted(files):
                try:
                    ftp.delete(filename)
                    logger.info(f"  Deleted: {filename}")
                    deleted += 1
                except Exception as e:
                    logger.warning(f"  Failed to delete {filename}: {e}")

            ftp.quit()
            logger.info(f"Cleanup complete: {deleted}/{len(files)} chunks deleted")

        except Exception as e:
            logger.error(f"FTP connection failed: {e}")

    def cleanup_server_api(self, chunk_filenames: list):
        """Delete merged chunks from server via API to free up space."""
        if not chunk_filenames:
            return

        # Convert .db names to .db.gz for server
        gz_filenames = []
        for name in chunk_filenames:
            if name.endswith('.db'):
                gz_filenames.append(name + '.gz')
            elif name.endswith('.db.gz'):
                gz_filenames.append(name)

        if not gz_filenames:
            return

        logger.info(f"Requesting server cleanup for {len(gz_filenames)} chunks...")

        try:
            response = requests.post(
                f"{self.api_url}/api/delete_chunks.php",
                headers={
                    'X-API-Key': self.api_key,
                    'Content-Type': 'application/json'
                },
                json={'chunks': gz_filenames},
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    logger.info(f"  Server cleanup: {data.get('files_deleted', 0)} files, "
                              f"{data.get('records_deleted', 0)} records deleted")
                    if data.get('errors'):
                        for err in data['errors']:
                            logger.warning(f"  Server cleanup error: {err}")
                else:
                    logger.warning(f"  Server cleanup failed: {data.get('error', 'Unknown')}")
            else:
                logger.warning(f"  Server cleanup request failed: HTTP {response.status_code}")

        except Exception as e:
            logger.warning(f"  Server cleanup failed: {e}")

    def decompress_chunk(self, chunk_path: Path) -> Path:
        """Decompress a gzipped chunk file."""
        if not chunk_path or not chunk_path.exists():
            return None

        output_path = chunk_path.with_suffix('')  # Remove .gz

        if output_path.exists():
            return output_path

        try:
            with gzip.open(chunk_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"  Decompressed: {output_path.name}")
            return output_path
        except Exception as e:
            logger.error(f"  Failed to decompress {chunk_path.name}: {e}")
            return None

    def is_valid_sqlite(self, db_path: Path) -> bool:
        """Check if a file is a valid SQLite database."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            conn.close()
            return len(tables) > 0
        except Exception:
            return False

    def merge_chunks(self, chunk_dbs: list, output_db: Path, already_merged: set = None):
        """Merge chunk databases into output - incrementally if output exists."""
        if not chunk_dbs:
            logger.warning("No chunks to merge")
            return [], 0

        already_merged = already_merged or set()

        # Filter to valid SQLite databases only
        valid_dbs = []
        for db_path in chunk_dbs:
            # Skip test data from 2020 (before real system started)
            if '2020-01-' in db_path.name or '2020-02-' in db_path.name:
                logger.info(f"  Skipping test data: {db_path.name}")
                continue
            # Skip already merged chunks
            if db_path.name in already_merged:
                continue
            if self.is_valid_sqlite(db_path):
                valid_dbs.append(db_path)
            else:
                logger.warning(f"  Skipping invalid database: {db_path.name}")

        if not valid_dbs:
            logger.info("No new chunks to merge")
            # Return current row count if output exists
            if output_db.exists():
                try:
                    conn = sqlite3.connect(output_db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM readings")
                    count = cursor.fetchone()[0]
                    conn.close()
                    return [], count
                except:
                    pass
            return [], 0

        logger.info(f"  Found {len(valid_dbs)} new chunks to merge")

        # If output doesn't exist, create from first chunk
        if not output_db.exists():
            logger.info(f"  Creating new database from: {valid_dbs[0].name}")
            shutil.copy(valid_dbs[0], output_db)
            merged_chunks = [valid_dbs[0].name]
            chunks_to_merge = valid_dbs[1:]
        else:
            logger.info(f"  Merging into existing database: {output_db.name}")
            merged_chunks = []
            chunks_to_merge = valid_dbs

        conn = sqlite3.connect(output_db)
        cursor = conn.cursor()

        # Get table names from output db
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Merge chunks one at a time (avoiding attachment limit issues)
        for db_path in chunks_to_merge:
            try:
                cursor.execute("ATTACH DATABASE ? AS src", (str(db_path),))

                for table in tables:
                    cursor.execute(f"INSERT OR IGNORE INTO main.{table} SELECT * FROM src.{table}")

                conn.commit()
                cursor.execute("DETACH DATABASE src")
                merged_chunks.append(db_path.name)
                logger.info(f"  Merged: {db_path.name}")
            except Exception as e:
                logger.error(f"  Failed to merge {db_path.name}: {e}")
                try:
                    cursor.execute("DETACH DATABASE src")
                except:
                    pass

        conn.commit()

        # Get final stats
        cursor.execute("SELECT COUNT(*) FROM readings")
        count = cursor.fetchone()[0]
        conn.close()

        size_mb = output_db.stat().st_size / 1024 / 1024
        logger.info(f"Merged database: {count:,} rows, {size_mb:.1f}MB")
        return merged_chunks, count

    def sync(self, force_rebuild: bool = False):
        """Main sync process with incremental merge support."""
        logger.info("=" * 50)
        logger.info("PoolAIssistant Brain - Database Sync Starting")
        logger.info("=" * 50)

        # Load state
        state = self.load_state()
        downloaded = set(state.get('downloaded_chunks', []))
        merged = set(state.get('merged_chunks', []))

        if force_rebuild:
            logger.info("REBUILD MODE: Will rebuild database from all chunks")
            merged = set()  # Clear merged tracking to force re-merge

        # Fetch chunk list from server
        chunks = self.fetch_chunk_list()

        if chunks:
            # Download new chunks
            new_chunks = [c for c in chunks if c['chunk_filename'] not in downloaded]

            if not new_chunks:
                logger.info("All chunks already downloaded")
            else:
                logger.info(f"Downloading {len(new_chunks)} new chunks...")
                for chunk in new_chunks:
                    logger.info(f"  [{chunk['period_start']} to {chunk['period_end']}]")
                    path = self.download_chunk(chunk)
                    if path:
                        downloaded.add(chunk['chunk_filename'])
        else:
            # Check local chunks
            local_gz = list(self.chunks_dir.glob('*.db.gz'))
            if local_gz:
                logger.info(f"No server chunks, using {len(local_gz)} local chunks")
            else:
                logger.error("No chunks available")
                return False

        # Decompress chunks that need it
        logger.info("Decompressing chunks...")
        chunk_dbs = []
        for gz_file in sorted(self.chunks_dir.glob('*.db.gz')):
            db_path = self.decompress_chunk(gz_file)
            if db_path:
                chunk_dbs.append(db_path)

        # Count how many need merging
        unmerged = [db for db in chunk_dbs if db.name not in merged]
        if unmerged:
            logger.info(f"Found {len(unmerged)} unmerged chunks (of {len(chunk_dbs)} total)")
        else:
            logger.info(f"All {len(chunk_dbs)} chunks already merged")

        # Merge into output database (incrementally)
        output_db = self.output_dir / 'pool_readings.db'

        if force_rebuild and output_db.exists():
            logger.info("Removing existing database for rebuild...")
            try:
                output_db.unlink()
            except PermissionError:
                # File is locked - rename it instead
                backup_path = output_db.with_suffix('.db.old')
                logger.warning(f"Database locked, renaming to {backup_path.name}")
                try:
                    if backup_path.exists():
                        backup_path.unlink()
                    output_db.rename(backup_path)
                except Exception as e:
                    logger.error(f"Cannot remove or rename database: {e}")
                    logger.error("Close any applications using pool_readings.db and try again")
                    return False

        if chunk_dbs:
            newly_merged, row_count = self.merge_chunks(
                chunk_dbs, output_db,
                already_merged=merged if not force_rebuild else set()
            )

            # Update merged tracking
            merged.update(newly_merged)

            # Cleanup decompressed .db files (keep .gz for backup)
            if self.cleanup_after_merge and newly_merged:
                logger.info("Cleaning up decompressed chunk files...")
                for db_path in chunk_dbs:
                    if db_path.name in merged and db_path.exists():
                        db_path.unlink()
                        logger.info(f"  Removed: {db_path.name}")

                # Also delete from server to free up space
                self.cleanup_server_api(newly_merged)

            logger.info(f"Output: {output_db}")

            # Update state
            state['merged_chunks'] = list(merged)
            state['output_row_count'] = row_count

        # Save state
        state['downloaded_chunks'] = list(downloaded)
        state['last_sync'] = datetime.now().isoformat()
        if unmerged or force_rebuild:
            state['last_merge'] = datetime.now().isoformat()
        self.save_state(state)

        logger.info("=" * 50)
        logger.info("Sync complete!")
        logger.info("=" * 50)
        return True

    def show_status(self):
        """Display sync status."""
        state = self.load_state()
        output_db = self.output_dir / 'pool_readings.db'

        print("=" * 50)
        print("PoolAIssistant Brain - Sync Status")
        print("=" * 50)
        print(f"Last sync: {state.get('last_sync', 'Never')}")
        print(f"Last merge: {state.get('last_merge', 'Never')}")
        print()

        downloaded = state.get('downloaded_chunks', [])
        merged = state.get('merged_chunks', [])
        print(f"Downloaded chunks: {len(downloaded)}")
        print(f"Merged chunks: {len(merged)}")

        local_gz = list(self.chunks_dir.glob('*.db.gz'))
        local_db = list(self.chunks_dir.glob('*.db'))
        print(f"Local .gz files: {len(local_gz)}")
        print(f"Local .db files: {len(local_db)}")

        if output_db.exists():
            size_mb = output_db.stat().st_size / 1024 / 1024
            print(f"\nOutput database: {output_db}")
            print(f"Size: {size_mb:.1f} MB")
            print(f"Rows: {state.get('output_row_count', 'Unknown'):,}")
        else:
            print("\nOutput database: Not created yet")

        # Show unmerged chunks
        merged_set = set(merged)
        unmerged = [gz.stem for gz in local_gz if gz.stem not in merged_set]
        if unmerged:
            print(f"\nUnmerged chunks ({len(unmerged)}):")
            for name in sorted(unmerged)[:10]:
                print(f"  - {name}")
            if len(unmerged) > 10:
                print(f"  ... and {len(unmerged) - 10} more")

        print("=" * 50)


def run_alert_check():
    """Run alert checker after sync."""
    try:
        from alert_checker import AlertChecker
        logger.info("")
        checker = AlertChecker()
        results = checker.run_check()
        return results.get('status', 'UNKNOWN')
    except Exception as e:
        logger.error(f"Alert check failed: {e}")
        return 'ERROR'


def main():
    syncer = ChunkSyncer()

    # Check for --status flag (no API key needed)
    if '--status' in sys.argv:
        syncer.show_status()
        sys.exit(0)

    if not syncer.api_key:
        logger.error("API_KEY not configured in .env file")
        sys.exit(1)

    # Check for --cleanup flag
    if '--cleanup' in sys.argv:
        syncer.cleanup_server()
        sys.exit(0)

    # Check for --rebuild flag
    force_rebuild = '--rebuild' in sys.argv
    if force_rebuild:
        logger.info("Rebuild mode enabled - will recreate database from scratch")

    success = syncer.sync(force_rebuild=force_rebuild)

    if success:
        # Run alert check after successful sync
        alert_status = run_alert_check()
        logger.info(f"Alert status: {alert_status}")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
