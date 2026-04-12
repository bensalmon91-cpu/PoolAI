import os
from dataclasses import dataclass


def _default_pool_db_path() -> str:
    preferred = "/opt/PoolAIssistant/data/pool_readings.sqlite3"
    if os.path.isdir("/opt/PoolAIssistant"):
        return preferred
    return os.path.join(os.getcwd(), "pool_readings.sqlite3")

def _get_pool_db_path() -> str:
    """Get pool database path from env or default."""
    return os.getenv("POOL_DB_PATH") or os.getenv("POOLDB") or _default_pool_db_path()


def _get_maint_db_path() -> str:
    """Get maintenance database path - defaults to pool DB path (merged database).

    NOTE: Maintenance logs are now stored in pool_readings.sqlite3 (merged database)
    This enables automatic sync/backup and allows AI to correlate maintenance with readings.
    """
    return os.getenv("MAINT_DB_PATH") or _get_pool_db_path()


@dataclass
class Settings:
    # --- DATABASE FILES (change if you prefer absolute paths) ---
    # NOTE: Maintenance logs are now stored in pool_readings.sqlite3 (merged database)
    # This enables automatic sync/backup and allows AI to correlate maintenance with readings.
    # MAINT_DB_PATH defaults to POOL_DB_PATH for backward compatibility.
    POOL_DB_PATH: str = None
    MAINT_DB_PATH: str = None

    def __post_init__(self):
        if self.POOL_DB_PATH is None:
            self.POOL_DB_PATH = _get_pool_db_path()
        if self.MAINT_DB_PATH is None:
            self.MAINT_DB_PATH = _get_maint_db_path()

    # --- DEVICE MAPPING (pool name -> controller IP) ---
    # Use IP_POOL_1..IP_POOL_4 or configure controllers in the UI.
    POOL_IPS: dict = None
    POOLS: list = None

    # --- CONTROLLER STATUS CHECK (Home page TCP test) ---
    TARGET_HOST: str = os.getenv("TARGET_HOST", "")
    TARGET_PORT: int = int(os.getenv("TARGET_PORT", 502))
    TCP_TEST_TIMEOUT: float = 1.0

    # --- FLASK SECRET (sessions/flash) ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")  # change in production!

    # --- THEME COLOURS (7" touch) ---
    LIGHT_BG: str = "#e6f2ff"
    MID_BG:   str = "#d4e8ff"
    DARK_TXT: str = "#0b2a4a"
    ACCENT:   str = "#4a90e2"
    CARD:     str = "#ffffff"

    @staticmethod
    def from_env():
        s = Settings()
        pool_ips: dict[str, str] = {}
        for name, env_key in (
            ("Pool 1", "IP_POOL_1"),
            ("Pool 2", "IP_POOL_2"),
            ("Pool 3", "IP_POOL_3"),
            ("Pool 4", "IP_POOL_4"),
        ):
            val = os.getenv(env_key, "").strip()
            if val:
                pool_ips[name] = val
        s.POOL_IPS = pool_ips
        s.POOLS = list(pool_ips.keys())
        return s

    def to_dict(self):
        return {
            "MAINT_DB_PATH": self.MAINT_DB_PATH,
            "POOL_DB_PATH": self.POOL_DB_PATH,
            "POOL_IPS": self.POOL_IPS,
            "POOLS": self.POOLS,
            "TARGET_HOST": self.TARGET_HOST,
            "TARGET_PORT": self.TARGET_PORT,
            "TCP_TEST_TIMEOUT": self.TCP_TEST_TIMEOUT,
            "SECRET_KEY": self.SECRET_KEY,
            "LIGHT_BG": self.LIGHT_BG,
            "MID_BG": self.MID_BG,
            "DARK_TXT": self.DARK_TXT,
            "ACCENT": self.ACCENT,
            "CARD": self.CARD,
        }
