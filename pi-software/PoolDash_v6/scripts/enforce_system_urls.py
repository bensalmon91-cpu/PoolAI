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

# System URLs - MUST match persist.py SYSTEM_URLS
SYSTEM_URLS = {
    "backend_url": "https://poolaissistant.modprojects.co.uk",
    "bootstrap_secret": "e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9",
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
