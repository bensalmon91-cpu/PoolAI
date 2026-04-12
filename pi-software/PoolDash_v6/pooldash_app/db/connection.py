"""
Robust SQLite database connection utilities.

Provides:
- WAL mode for crash recovery
- Integrity checking on startup
- Context managers for safe connection handling
- Proper logging of errors
- Timeout handling
"""

import sqlite3
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

logger = logging.getLogger(__name__)

# Default connection settings
DEFAULT_TIMEOUT = 30.0
BUSY_TIMEOUT_MS = 5000


def init_database(db_path: str, check_integrity: bool = True) -> bool:
    """
    Initialize database with WAL mode and optionally check integrity.
    
    Args:
        db_path: Path to SQLite database
        check_integrity: Whether to run integrity check (slower but safer)
    
    Returns:
        True if database is healthy, False if there are issues
    """
    try:
        conn = sqlite3.connect(db_path, timeout=DEFAULT_TIMEOUT)
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        
        # Enable WAL mode for crash recovery
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if result and result[0].lower() == "wal":
            logger.debug(f"WAL mode enabled for {db_path}")
        else:
            logger.warning(f"Could not enable WAL mode for {db_path}: {result}")
        
        # Set synchronous to NORMAL for balance of safety and speed
        conn.execute("PRAGMA synchronous=NORMAL")
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")
        
        if check_integrity:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                logger.error(f"Database integrity check failed for {db_path}: {result}")
                conn.close()
                return False
            logger.debug(f"Integrity check passed for {db_path}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        logger.exception(f"Failed to initialize database {db_path}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error initializing database {db_path}: {e}")
        return False


@contextmanager
def get_connection(
    db_path: str, 
    timeout: float = DEFAULT_TIMEOUT,
    readonly: bool = False
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for safe database connections.
    
    Automatically:
    - Sets busy timeout
    - Enables WAL mode
    - Commits on success
    - Rolls back on exception
    - Closes connection in all cases
    
    Args:
        db_path: Path to SQLite database
        timeout: Connection timeout in seconds
        readonly: Open in read-only mode if True
    
    Yields:
        sqlite3.Connection
        
    Example:
        with get_connection("/path/to/db.sqlite3") as conn:
            conn.execute("INSERT INTO ...")
            # Automatically commits on exit
    """
    conn = None
    try:
        if readonly:
            # Read-only mode using URI
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, timeout=timeout, uri=True)
        else:
            conn = sqlite3.connect(db_path, timeout=timeout)
        
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        
        yield conn
        
        if not readonly:
            conn.commit()
            
    except sqlite3.Error as e:
        logger.exception(f"Database error on {db_path}: {e}")
        if conn and not readonly:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    except Exception as e:
        logger.exception(f"Unexpected error on {db_path}: {e}")
        if conn and not readonly:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Error closing connection to {db_path}: {e}")


def check_database_health(db_path: str) -> dict:
    """
    Check database health and return status report.
    
    Returns dict with:
        - healthy: bool
        - integrity: str ("ok" or error message)
        - wal_mode: bool
        - size_mb: float
        - error: str or None
    """
    result = {
        "healthy": False,
        "integrity": "unknown",
        "wal_mode": False,
        "size_mb": 0,
        "error": None
    }
    
    try:
        if not os.path.exists(db_path):
            result["error"] = "Database file does not exist"
            return result
        
        result["size_mb"] = round(os.path.getsize(db_path) / 1e6, 2)
        
        with get_connection(db_path, readonly=True) as conn:
            # Check journal mode
            journal = conn.execute("PRAGMA journal_mode").fetchone()
            result["wal_mode"] = journal and journal[0].lower() == "wal"
            
            # Quick integrity check
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            result["integrity"] = integrity[0] if integrity else "unknown"
            
            result["healthy"] = result["integrity"] == "ok"
            
    except sqlite3.DatabaseError as e:
        result["error"] = f"Database error: {e}"
        logger.exception(f"Database health check failed for {db_path}")
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        logger.exception(f"Unexpected error checking {db_path}")
    
    return result


def vacuum_database(db_path: str) -> bool:
    """
    Vacuum database to reclaim space and optimize.
    
    Note: This can take a while on large databases and
    temporarily doubles disk usage.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path, timeout=300)  # Long timeout for vacuum
        conn.execute("VACUUM")
        conn.close()
        logger.info(f"Vacuumed database {db_path}")
        return True
    except sqlite3.Error as e:
        logger.exception(f"Failed to vacuum {db_path}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error vacuuming {db_path}: {e}")
        return False
