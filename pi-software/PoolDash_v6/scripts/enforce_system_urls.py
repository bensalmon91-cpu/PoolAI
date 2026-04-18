#!/usr/bin/env python3
"""
Enforce System URLs - Runs at midnight to ensure backend URLs are correct.

This script ensures that the backend_url and bootstrap_secret always match
the hardcoded SYSTEM_URLS values. This prevents tampering and ensures
the device can always communicate with the server.

The values can only be changed via a software update (by modifying persist.py).
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime


def _load_bootstrap_secret() -> str:
    """Source the bootstrap secret from env or /etc/poolai/bootstrap.secret.

    Mirrors pooldash_app/persist.py so this midnight-enforcer works in
    whatever execution context it's launched from (systemd timer,
    manual SSH run, etc.) without pulling persist.py as a dependency.
    """
    env_val = os.environ.get("POOLAI_BOOTSTRAP_SECRET", "").strip()
    if env_val:
        return env_val
    try:
        secret_path = Path("/etc/poolai/bootstrap.secret")
        if secret_path.is_file():
            return secret_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


# System URLs - MUST match persist.py SYSTEM_URLS
SYSTEM_URLS = {
    "backend_url": "https://poolaissistant.modprojects.co.uk",
    "bootstrap_secret": _load_bootstrap_secret(),
}

SETTINGS_PATH = Path("/opt/PoolAIssistant/data/pooldash_settings.json")
LOG_PATH = Path("/opt/PoolAIssistant/data/enforce_urls.log")


def log(msg: str):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    log("Starting URL enforcement check")

    if not SETTINGS_PATH.exists():
        log("Settings file does not exist - nothing to enforce")
        return 0

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        log(f"Failed to read settings: {e}")
        return 1

    changed = False

    # Check and enforce each system URL
    for key, expected_value in SYSTEM_URLS.items():
        if not expected_value:
            # Source unavailable (e.g. bootstrap.secret missing on this run).
            # Do NOT overwrite an existing value with empty - leave it alone.
            log(f"SKIP: {key} has no expected value available; leaving settings as-is")
            continue
        current_value = settings.get(key, "")
        if current_value != expected_value:
            log(f"MISMATCH: {key} was '{current_value}', reverting to '{expected_value}'")
            settings[key] = expected_value
            changed = True

    if changed:
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, sort_keys=True)
            log("Settings file updated with correct system URLs")
        except Exception as e:
            log(f"Failed to write settings: {e}")
            return 1
    else:
        log("All system URLs are correct - no changes needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
