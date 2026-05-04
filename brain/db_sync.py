"""
PoolAIssistant Brain - Database Sync Tool
Downloads chunk files from the FTP server and assembles them into a local SQLite database.

Multi-device aware: auto-discovers device IDs as subdirectories under /data/chunks/
on the FTP server and syncs each into data/chunks/{device_id}/ locally.

Features:
- FTP-based chunk discovery and download (one transport, no auth-key drift)
- Per-device tracking in sync_state.json (devices.{id}.downloaded_chunks / merged_chunks)
- Incremental merging into a single output DB (rows are tagged by `host` column)
- Auto-migrates legacy flat sync_state.json + flat chunk layout to per-device subdirs

Usage:
    python db_sync.py              # Normal incremental sync
    python db_sync.py --rebuild    # Force full rebuild from all chunks
    python db_sync.py --cleanup    # Delete all chunks from server (every device)
    python db_sync.py --status     # Show sync status
    python db_sync.py --devices    # Discover devices on server and exit
"""

import os
import sys
import json
import gzip
import re
import sqlite3
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from ftplib import FTP, error_perm

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


SERVER_CHUNKS_ROOT = '/data/chunks'  # FTP path, parent of per-device subdirs


class ChunkSyncer:
    """Downloads and assembles chunk files from the FTP server, multi-device aware."""

    def __init__(self):
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
        self.staleness_hours = float(os.getenv('STALENESS_HOURS', '6'))

        # Set after sync(); read by main() to decide exit code.
        self._staleness: dict | None = None

        # Optional allowlist: DEVICE_IDS=2,5 restricts which device dirs to sync.
        # If unset, every numeric subdirectory under SERVER_CHUNKS_ROOT is synced.
        allowlist = os.getenv('DEVICE_IDS', '').strip()
        self.device_allowlist = (
            [d.strip() for d in allowlist.split(',') if d.strip()] if allowlist else None
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        self._migrate_legacy_layout()

    # ------------------------------------------------------------------
    # Legacy migration (one-shot, idempotent)
    # ------------------------------------------------------------------
    def _migrate_legacy_layout(self):
        """Move pre-multi-device flat chunks into data/chunks/2/ (historical device)."""
        flat_chunks = list(self.chunks_dir.glob('*.db.gz')) + list(self.chunks_dir.glob('*.db'))
        if not flat_chunks:
            return

        legacy_device = '2'
        target_dir = self.chunks_dir / legacy_device
        target_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for src in flat_chunks:
            dst = target_dir / src.name
            if dst.exists():
                src.unlink()  # already migrated, drop the duplicate
            else:
                src.rename(dst)
            moved += 1
        if moved:
            logger.info(f"Migrated {moved} legacy flat chunk(s) to {target_dir}")

    # ------------------------------------------------------------------
    # State (per-device)
    # ------------------------------------------------------------------
    def load_state(self) -> dict:
        """Load sync state, auto-migrating legacy flat schema to per-device."""
        if not self.state_file.exists():
            return {
                'devices': {},
                'last_sync': None,
                'last_merge': None,
                'output_row_count': 0,
            }
        with open(self.state_file) as f:
            state = json.load(f)

        # Migrate legacy flat schema to per-device under id "2".
        if 'downloaded_chunks' in state or 'merged_chunks' in state:
            legacy_device = '2'
            state.setdefault('devices', {})
            state['devices'].setdefault(legacy_device, {
                'downloaded_chunks': [],
                'merged_chunks': [],
            })
            dev = state['devices'][legacy_device]
            dev['downloaded_chunks'] = sorted(set(
                dev['downloaded_chunks'] + state.pop('downloaded_chunks', [])
            ))
            dev['merged_chunks'] = sorted(set(
                dev['merged_chunks'] + state.pop('merged_chunks', [])
            ))
            logger.info(f"Migrated legacy state to devices.{legacy_device}")

        state.setdefault('devices', {})
        return state

    def save_state(self, state: dict):
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def _device_state(state: dict, device_id: str) -> dict:
        return state['devices'].setdefault(device_id, {
            'downloaded_chunks': [],
            'merged_chunks': [],
        })

    # ------------------------------------------------------------------
    # FTP helpers
    # ------------------------------------------------------------------
    def _connect_ftp(self) -> FTP:
        ftp = FTP()
        ftp.connect(self.ftp_config['host'], self.ftp_config['port'], timeout=60)
        ftp.login(self.ftp_config['user'], self.ftp_config['password'])
        return ftp

    def discover_devices(self) -> list:
        """List numeric device-ID subdirectories under SERVER_CHUNKS_ROOT on FTP."""
        try:
            ftp = self._connect_ftp()
            ftp.cwd(SERVER_CHUNKS_ROOT)
            entries = []
            ftp.retrlines('LIST', entries.append)
            ftp.quit()
        except Exception as e:
            logger.error(f"Could not list {SERVER_CHUNKS_ROOT} on FTP: {e}")
            return []

        device_ids = []
        for line in entries:
            # Standard UNIX listing: "drwxr-xr-x ... <name>"
            if not line.startswith('d'):
                continue
            name = line.split()[-1]
            if name in ('.', '..'):
                continue
            if not re.fullmatch(r'\d+', name):
                continue  # only numeric device IDs are real devices
            device_ids.append(name)

        if self.device_allowlist:
            allowed = set(self.device_allowlist)
            device_ids = [d for d in device_ids if d in allowed]
            logger.info(f"DEVICE_IDS allowlist active; syncing only: {sorted(device_ids)}")
        else:
            logger.info(f"Discovered devices on server: {sorted(device_ids)}")
        return sorted(device_ids)

    def fetch_chunks_for_device(self, device_id: str) -> list:
        """List .db.gz chunks under /data/chunks/{device_id}/, tagged with device_id."""
        path = f"{SERVER_CHUNKS_ROOT}/{device_id}"
        try:
            ftp = self._connect_ftp()
            ftp.cwd(path)
            files = [f for f in ftp.nlst() if f.endswith('.db.gz')]
            ftp.quit()
        except Exception as e:
            logger.error(f"FTP list failed for device {device_id}: {e}")
            return []

        chunks = []
        for filename in files:
            period_start = filename.split('_to_')[0] if '_to_' in filename else 'unknown'
            period_end = (
                filename.split('_to_')[1].split('_')[0] if '_to_' in filename else 'unknown'
            )
            chunks.append({
                'device_id': device_id,
                'chunk_filename': filename,
                'ftp_path': f"{path}/{filename}",
                'period_start': period_start,
                'period_end': period_end,
            })
        if chunks:
            logger.info(f"  Device {device_id}: found {len(chunks)} chunk(s) on server")
        return chunks

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download_chunk(self, chunk: dict) -> Path:
        """Download a chunk via FTP into data/chunks/{device_id}/ and optionally delete it."""
        device_id = chunk['device_id']
        filename = chunk['chunk_filename']
        device_dir = self.chunks_dir / device_id
        device_dir.mkdir(parents=True, exist_ok=True)
        local_path = device_dir / filename
        ftp_path = chunk['ftp_path']

        if local_path.exists():
            logger.info(f"  Already local (device {device_id}): {filename}")
            if self.delete_after_download:
                self._delete_from_ftp(ftp_path, filename)
            return local_path

        try:
            ftp = self._connect_ftp()
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {ftp_path}', f.write)
            size_mb = local_path.stat().st_size / 1024 / 1024
            logger.info(f"  Downloaded (device {device_id}): {filename} ({size_mb:.1f}MB)")

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
        try:
            ftp = self._connect_ftp()
            ftp.delete(ftp_path)
            ftp.quit()
            logger.info(f"  Deleted from server: {filename}")
        except Exception as e:
            logger.warning(f"  Failed to delete from server: {filename} - {e}")

    def cleanup_server(self):
        """Delete all chunks from every device on the server (FTP only)."""
        logger.info("=" * 50)
        logger.info("Cleaning up chunks from server (all devices)")
        logger.info("=" * 50)

        devices = self.discover_devices()
        if not devices:
            logger.info("No devices discovered on server")
            return

        try:
            ftp = self._connect_ftp()
        except Exception as e:
            logger.error(f"FTP connection failed: {e}")
            return

        total_deleted = 0
        total_seen = 0
        for device_id in devices:
            try:
                ftp.cwd(f"{SERVER_CHUNKS_ROOT}/{device_id}")
            except error_perm as e:
                logger.warning(f"  Cannot cd to device {device_id}: {e}")
                continue
            files = [f for f in ftp.nlst() if f.endswith('.db.gz')]
            total_seen += len(files)
            if not files:
                logger.info(f"  Device {device_id}: no chunks")
                continue
            logger.info(f"  Device {device_id}: deleting {len(files)} chunk(s)")
            for filename in sorted(files):
                try:
                    ftp.delete(filename)
                    total_deleted += 1
                except Exception as e:
                    logger.warning(f"    failed to delete {filename}: {e}")
        ftp.quit()
        logger.info(f"Cleanup complete: {total_deleted}/{total_seen} chunks deleted across {len(devices)} device(s)")

    # ------------------------------------------------------------------
    # Decompress / merge
    # ------------------------------------------------------------------
    def decompress_chunk(self, chunk_path: Path) -> Path:
        if not chunk_path or not chunk_path.exists():
            return None
        output_path = chunk_path.with_suffix('')  # strip .gz
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

        valid_dbs = []
        for db_path in chunk_dbs:
            if '2020-01-' in db_path.name or '2020-02-' in db_path.name:
                logger.info(f"  Skipping test data: {db_path.name}")
                continue
            if db_path.name in already_merged:
                continue
            if self.is_valid_sqlite(db_path):
                valid_dbs.append(db_path)
            else:
                logger.warning(f"  Skipping invalid database: {db_path.name}")

        if not valid_dbs:
            logger.info("No new chunks to merge")
            if output_db.exists():
                try:
                    conn = sqlite3.connect(output_db)
                    count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
                    conn.close()
                    return [], count
                except Exception:
                    pass
            return [], 0

        logger.info(f"  Found {len(valid_dbs)} new chunks to merge")

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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

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
                except Exception:
                    pass

        conn.commit()
        count = cursor.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        conn.close()

        size_mb = output_db.stat().st_size / 1024 / 1024
        logger.info(f"Merged database: {count:,} rows, {size_mb:.1f}MB")
        return merged_chunks, count

    # ------------------------------------------------------------------
    # Sync orchestration
    # ------------------------------------------------------------------
    def sync(self, force_rebuild: bool = False) -> bool:
        logger.info("=" * 50)
        logger.info("PoolAIssistant Brain - Database Sync Starting")
        logger.info("=" * 50)

        state = self.load_state()

        # Discover server-side devices, plus any local-only device dirs we already have
        devices = set(self.discover_devices())
        for sub in self.chunks_dir.iterdir() if self.chunks_dir.exists() else []:
            if sub.is_dir() and re.fullmatch(r'\d+', sub.name):
                if not self.device_allowlist or sub.name in self.device_allowlist:
                    devices.add(sub.name)
        if not devices:
            logger.error("No devices found (server discovery returned nothing and no local device dirs)")
            return False

        # Per-device download phase
        any_new_downloads = False
        any_chunks_seen = False
        for device_id in sorted(devices):
            dev_state = self._device_state(state, device_id)
            downloaded = set(dev_state['downloaded_chunks'])

            chunks = self.fetch_chunks_for_device(device_id)
            if not chunks:
                # Device dir might be empty server-side but still have local chunks
                continue
            any_chunks_seen = True

            new_chunks = [c for c in chunks if c['chunk_filename'] not in downloaded]
            if not new_chunks:
                logger.info(f"  Device {device_id}: all {len(chunks)} chunk(s) already downloaded")
            else:
                logger.info(f"  Device {device_id}: downloading {len(new_chunks)} new chunk(s)")
                for chunk in new_chunks:
                    logger.info(f"    [{chunk['period_start']} -> {chunk['period_end']}]")
                    if self.download_chunk(chunk):
                        downloaded.add(chunk['chunk_filename'])
                        any_new_downloads = True
            dev_state['downloaded_chunks'] = sorted(downloaded)

        if not any_chunks_seen and not any(
            (self.chunks_dir / d).glob('*.db.gz') for d in devices
        ):
            logger.error("No chunks available on server or locally")
            self._finalize_state(state, force_rebuild)
            return False

        # Decompress phase (per device)
        logger.info("Decompressing chunks...")
        all_chunk_dbs = []
        for device_id in sorted(devices):
            device_dir = self.chunks_dir / device_id
            if not device_dir.exists():
                continue
            for gz_file in sorted(device_dir.glob('*.db.gz')):
                db_path = self.decompress_chunk(gz_file)
                if db_path:
                    all_chunk_dbs.append((device_id, db_path))

        # Merge phase: union of merged-sets across devices
        merged_union = set()
        for dev_state in state['devices'].values():
            merged_union.update(dev_state.get('merged_chunks', []))
        if force_rebuild:
            logger.info("REBUILD MODE: forcing re-merge of all chunks")
            merged_union = set()

        unmerged = [db for _, db in all_chunk_dbs if db.name not in merged_union]
        if unmerged:
            logger.info(f"Found {len(unmerged)} unmerged chunks (of {len(all_chunk_dbs)} total)")
        else:
            logger.info(f"All {len(all_chunk_dbs)} chunks already merged")

        output_db = self.output_dir / 'pool_readings.db'

        if force_rebuild and output_db.exists():
            logger.info("Removing existing database for rebuild...")
            try:
                output_db.unlink()
            except PermissionError:
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

        if all_chunk_dbs:
            chunk_db_paths = [db for _, db in all_chunk_dbs]
            newly_merged, row_count = self.merge_chunks(
                chunk_db_paths, output_db,
                already_merged=merged_union if not force_rebuild else set(),
            )
            newly_merged_set = set(newly_merged)

            # Distribute newly_merged back into per-device state
            for device_id, db_path in all_chunk_dbs:
                if db_path.name in newly_merged_set:
                    dev_state = self._device_state(state, device_id)
                    dev_state['merged_chunks'] = sorted(
                        set(dev_state['merged_chunks']) | {db_path.name}
                    )

            # Cleanup decompressed .db files
            if self.cleanup_after_merge and newly_merged_set:
                logger.info("Cleaning up decompressed chunk files...")
                for _, db_path in all_chunk_dbs:
                    if db_path.name in newly_merged_set and db_path.exists():
                        db_path.unlink()
                        logger.info(f"  Removed: {db_path.name}")

            state['output_row_count'] = row_count
            logger.info(f"Output: {output_db}")

        self._finalize_state(state, force_rebuild)

        # B1: staleness alarm — set instance attr for main() to read
        self._staleness = self._check_staleness()
        if self._staleness is not None:
            self._emit_staleness_marker(self._staleness)
            self._log_staleness(self._staleness)

        logger.info("=" * 50)
        if not any_new_downloads and not any_chunks_seen:
            logger.warning("Sync completed but no chunks were found on server. "
                           "Check Pi upload status - is the chunker still running?")
        else:
            logger.info("Sync complete!")
        logger.info("=" * 50)
        return True

    def _finalize_state(self, state: dict, force_rebuild: bool):
        state['last_sync'] = datetime.now().isoformat()
        if force_rebuild:
            state['last_merge'] = datetime.now().isoformat()
        self.save_state(state)

    # ------------------------------------------------------------------
    # Staleness check (B1) — pipeline alarm when latest reading is too old
    # ------------------------------------------------------------------
    def _check_staleness(self) -> dict | None:
        """Compare MAX(ts) in output DB to now. Return staleness dict or None."""
        output_db = self.output_dir / 'pool_readings.db'
        if not output_db.exists():
            return None
        try:
            conn = sqlite3.connect(output_db)
            row = conn.execute("SELECT MAX(ts) FROM readings").fetchone()
            conn.close()
        except Exception as e:
            logger.error(f"staleness check failed: {e}")
            return None
        latest = row[0] if row else None
        if not latest:
            return None
        try:
            latest_dt = datetime.fromisoformat(latest)
        except ValueError:
            logger.warning(f"could not parse latest ts: {latest!r}")
            return None
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600.0
        return {
            'is_stale': age_hours > self.staleness_hours,
            'latest_reading': latest,
            'age_hours': round(age_hours, 2),
            'threshold_hours': self.staleness_hours,
            'checked_at': datetime.now(timezone.utc).isoformat(),
        }

    def _emit_staleness_marker(self, info: dict):
        """Write output/staleness.json so external monitors can read state without parsing logs."""
        marker = self.output_dir / 'staleness.json'
        try:
            marker.write_text(json.dumps(info, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning(f"could not write staleness marker {marker}: {e}")

    def _log_staleness(self, info: dict):
        if info['is_stale']:
            age_h = info['age_hours']
            days = age_h / 24
            logger.warning(
                f"WARNING - newest reading is {age_h:.1f}h old "
                f"({days:.1f} days, ts={info['latest_reading']}). "
                f"Pipeline is STALE (threshold {info['threshold_hours']}h)."
            )
        else:
            logger.info(
                f"Freshness OK: newest reading {info['age_hours']:.1f}h old "
                f"(threshold {info['threshold_hours']}h)."
            )

    # ------------------------------------------------------------------
    # Status display
    # ------------------------------------------------------------------
    def show_status(self):
        state = self.load_state()
        output_db = self.output_dir / 'pool_readings.db'

        print("=" * 50)
        print("PoolAIssistant Brain - Sync Status")
        print("=" * 50)
        print(f"Last sync:  {state.get('last_sync', 'Never')}")
        print(f"Last merge: {state.get('last_merge', 'Never')}")
        print()

        devices = sorted(state.get('devices', {}).keys())
        if not devices:
            print("No device state recorded yet.")
        else:
            print(f"Devices in state: {devices}")
            for device_id in devices:
                dev = state['devices'][device_id]
                local_dir = self.chunks_dir / device_id
                local_gz = list(local_dir.glob('*.db.gz')) if local_dir.exists() else []
                local_db = list(local_dir.glob('*.db')) if local_dir.exists() else []
                print(f"  Device {device_id}:")
                print(f"    downloaded: {len(dev.get('downloaded_chunks', []))}  "
                      f"merged: {len(dev.get('merged_chunks', []))}")
                print(f"    local .gz:  {len(local_gz)}  local .db: {len(local_db)}")

        if output_db.exists():
            size_mb = output_db.stat().st_size / 1024 / 1024
            print(f"\nOutput database: {output_db}")
            print(f"Size: {size_mb:.1f} MB")
            row_count = state.get('output_row_count', 0)
            print(f"Rows: {row_count:,}" if isinstance(row_count, int) else f"Rows: {row_count}")
        else:
            print("\nOutput database: Not created yet")
        print("=" * 50)


def run_alert_check():
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

    if '--status' in sys.argv:
        syncer.show_status()
        sys.exit(0)

    if '--devices' in sys.argv:
        devices = syncer.discover_devices()
        print(f"Devices on server: {sorted(devices)}")
        sys.exit(0)

    if '--cleanup' in sys.argv:
        syncer.cleanup_server()
        sys.exit(0)

    force_rebuild = '--rebuild' in sys.argv
    if force_rebuild:
        logger.info("Rebuild mode enabled - will recreate database from scratch")

    success = syncer.sync(force_rebuild=force_rebuild)

    # Alerts run even if sync had no new data — the existing DB may still be useful
    # and we want staleness to surface as a CRITICAL alert in latest_alerts.json.
    alert_status = run_alert_check() if success else 'SKIPPED'
    logger.info(f"Alert status: {alert_status}")

    # Exit non-zero on sync failure OR pipeline staleness, so cron/wrapper can alarm.
    is_stale = bool(syncer._staleness and syncer._staleness.get('is_stale'))
    sys.exit(0 if (success and not is_stale) else 1)


if __name__ == '__main__':
    main()
