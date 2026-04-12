#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoolAIssistant — Configuration Backup Utility

Provides automatic backup of configuration files before changes.
Maintains a rotating set of backups to allow rollback if needed.
"""

import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default backup directory
BACKUP_DIR = Path("/opt/PoolAIssistant/backups")

# Maximum number of backups to keep per config file
MAX_BACKUPS = 10


def backup_config(config_path: str, backup_dir: Optional[str] = None) -> Optional[str]:
    """
    Create a timestamped backup of a configuration file.

    Args:
        config_path: Path to the config file to backup
        backup_dir: Optional custom backup directory

    Returns:
        Path to the backup file, or None if backup failed
    """
    src = Path(config_path)
    if not src.exists():
        logging.warning(f"[BACKUP] Config file does not exist: {config_path}")
        return None

    dest_dir = Path(backup_dir) if backup_dir else BACKUP_DIR

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"[BACKUP] Failed to create backup directory: {e}")
        return None

    # Create timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{src.name}.{timestamp}.bak"
    backup_path = dest_dir / backup_name

    try:
        shutil.copy2(config_path, backup_path)
        logging.info(f"[BACKUP] Created backup: {backup_path}")
    except Exception as e:
        logging.error(f"[BACKUP] Failed to create backup: {e}")
        return None

    # Rotate old backups - keep only MAX_BACKUPS most recent
    try:
        rotate_backups(dest_dir, src.name, MAX_BACKUPS)
    except Exception as e:
        logging.warning(f"[BACKUP] Failed to rotate old backups: {e}")

    return str(backup_path)


def rotate_backups(backup_dir: Path, base_name: str, max_keep: int) -> int:
    """
    Remove old backups, keeping only the most recent ones.

    Args:
        backup_dir: Directory containing backups
        base_name: Base filename to match (e.g., "settings.json")
        max_keep: Maximum number of backups to keep

    Returns:
        Number of backups deleted
    """
    pattern = f"{base_name}.*.bak"
    backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    deleted = 0
    for old_backup in backups[max_keep:]:
        try:
            old_backup.unlink()
            logging.debug(f"[BACKUP] Deleted old backup: {old_backup}")
            deleted += 1
        except Exception as e:
            logging.warning(f"[BACKUP] Failed to delete old backup {old_backup}: {e}")

    return deleted


def list_backups(config_path: str, backup_dir: Optional[str] = None) -> list:
    """
    List available backups for a config file.

    Args:
        config_path: Path to the original config file
        backup_dir: Optional custom backup directory

    Returns:
        List of backup file paths, newest first
    """
    src = Path(config_path)
    dest_dir = Path(backup_dir) if backup_dir else BACKUP_DIR

    if not dest_dir.exists():
        return []

    pattern = f"{src.name}.*.bak"
    backups = sorted(dest_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(b) for b in backups]


def restore_backup(backup_path: str, config_path: str) -> bool:
    """
    Restore a configuration file from a backup.

    Args:
        backup_path: Path to the backup file
        config_path: Path to restore to

    Returns:
        True if restore succeeded, False otherwise
    """
    backup = Path(backup_path)
    if not backup.exists():
        logging.error(f"[BACKUP] Backup file does not exist: {backup_path}")
        return False

    try:
        # Create a backup of current config before restoring
        current = Path(config_path)
        if current.exists():
            pre_restore = f"{config_path}.pre_restore"
            shutil.copy2(config_path, pre_restore)
            logging.info(f"[BACKUP] Saved current config to: {pre_restore}")

        # Restore from backup
        shutil.copy2(backup_path, config_path)
        logging.info(f"[BACKUP] Restored config from: {backup_path}")
        return True
    except Exception as e:
        logging.error(f"[BACKUP] Failed to restore backup: {e}")
        return False


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="PoolAIssistant config backup utility")
    parser.add_argument("action", choices=["backup", "list", "restore"],
                        help="Action to perform")
    parser.add_argument("config_path", help="Path to config file")
    parser.add_argument("--backup-dir", help="Custom backup directory")
    parser.add_argument("--backup-file", help="Backup file to restore (for restore action)")

    args = parser.parse_args()

    if args.action == "backup":
        result = backup_config(args.config_path, args.backup_dir)
        if result:
            print(f"Backup created: {result}")
            sys.exit(0)
        else:
            print("Backup failed")
            sys.exit(1)

    elif args.action == "list":
        backups = list_backups(args.config_path, args.backup_dir)
        if backups:
            print("Available backups (newest first):")
            for b in backups:
                print(f"  {b}")
        else:
            print("No backups found")
        sys.exit(0)

    elif args.action == "restore":
        if not args.backup_file:
            print("Error: --backup-file required for restore action")
            sys.exit(1)
        if restore_backup(args.backup_file, args.config_path):
            print("Restore successful")
            sys.exit(0)
        else:
            print("Restore failed")
            sys.exit(1)
