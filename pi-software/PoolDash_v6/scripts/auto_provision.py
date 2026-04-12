#!/usr/bin/env python3
"""
Auto-Provisioning Script for PoolAIssistant

Automatically registers the Pi with the MOD Projects server on first boot.
Uses a bootstrap secret to authenticate and receives an API key in return.

This script should run on boot before the main UI starts.
If already provisioned (API key exists), it exits immediately.

Usage:
    python auto_provision.py          # Normal provisioning
    python auto_provision.py --force  # Force re-provisioning
    python auto_provision.py --test   # Test connectivity and report status
    python auto_provision.py --status # Show current provisioning status
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INSTANCE_DIR = PROJECT_DIR / "instance"
DATA_DIR = Path(os.environ.get("POOLDASH_DATA_DIR", "/opt/PoolAIssistant/data"))

# Settings path
SETTINGS_PATH = Path(os.environ.get("POOLDASH_SETTINGS_PATH", DATA_DIR / "pooldash_settings.json"))

# Retry settings with exponential backoff
MAX_RETRIES = 5
BASE_RETRY_DELAY = 5  # seconds
MAX_RETRY_DELAY = 60  # seconds


def get_retry_delay(attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    # Exponential backoff: 5, 10, 20, 40, 60 (capped)
    delay = min(BASE_RETRY_DELAY * (2 ** (attempt - 1)), MAX_RETRY_DELAY)
    # Add jitter: +/- 25% randomness to prevent thundering herd
    jitter = delay * 0.25 * (random.random() * 2 - 1)
    return delay + jitter

# Add project dir to path to import persist
sys.path.insert(0, str(PROJECT_DIR / "pooldash_app"))
try:
    import persist as persist_module
    USE_PERSIST = True
except ImportError:
    USE_PERSIST = False


def load_settings():
    """Load settings using persist module (includes hardcoded defaults)."""
    if USE_PERSIST:
        # Use persist.load() which has hardcoded backend_url and bootstrap_secret
        return persist_module.load(str(DATA_DIR))
    # Fallback to direct file read
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {}


def save_settings(settings):
    """Save settings using persist module."""
    try:
        if USE_PERSIST:
            persist_module.save(str(DATA_DIR), settings)
            print(f"Settings saved to {SETTINGS_PATH}")
            return True
        # Fallback to direct file write
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
        print(f"Settings saved to {SETTINGS_PATH}")
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False


def get_or_create_device_id(settings):
    """Get existing device ID or create a new one."""
    device_id = settings.get("device_id", "")
    if not device_id:
        import uuid
        device_id = str(uuid.uuid4())
        settings["device_id"] = device_id
        save_settings(settings)
        print(f"Generated new device ID: {device_id}")
    return device_id


def provision(settings, force=False):
    """Attempt to provision the device with the server."""

    # Check if already provisioned
    api_key = settings.get("remote_api_key", "")
    if api_key and not force:
        print(f"Already provisioned (API key exists: {api_key[:8]}...)")
        return True

    # Check for required settings
    # Prefer backend_url, fall back to remote_sync_url
    backend_url = settings.get("backend_url", "").strip()
    if not backend_url:
        backend_url = settings.get("remote_sync_url", "").strip()
    bootstrap_secret = settings.get("bootstrap_secret", "").strip()

    if not backend_url:
        print("No backend_url or remote_sync_url configured - skipping provisioning")
        print("Set 'backend_url' in settings to enable auto-provisioning")
        return False

    if not bootstrap_secret:
        print("No bootstrap_secret configured - skipping provisioning")
        print("Set 'bootstrap_secret' in settings to enable auto-provisioning")
        return False

    # Get device info
    device_id = get_or_create_device_id(settings)
    device_alias = settings.get("device_alias", "")

    # Build provisioning URL
    provision_url = backend_url.rstrip("/") + "/api/provision.php"

    print(f"Attempting to provision with {provision_url}")
    print(f"Device ID: {device_id}")
    print(f"Device Alias: {device_alias or '(none)'}")

    # Prepare request
    headers = {
        "X-Bootstrap-Secret": bootstrap_secret,
        "Content-Type": "application/json",
    }

    payload = {
        "device_id": device_id,
        "device_alias": device_alias,
    }

    # Retry loop
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Provisioning attempt {attempt}/{MAX_RETRIES}...")

            response = requests.post(
                provision_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("ok"):
                    new_api_key = result.get("api_key", "")
                    device_name = result.get("device_name", "")
                    was_new = result.get("provisioned", False)

                    if new_api_key:
                        # Save the API key and enable sync
                        settings["remote_api_key"] = new_api_key
                        settings["remote_sync_enabled"] = True
                        settings["remote_sync_url"] = backend_url

                        if device_name and not device_alias:
                            settings["device_alias"] = device_name

                        save_settings(settings)

                        status = "registered" if was_new else "already registered"
                        print(f"SUCCESS: Device {status}!")
                        print(f"API Key: {new_api_key[:8]}...{new_api_key[-4:]}")
                        print(f"Device Name: {device_name}")
                        return True
                    else:
                        print(f"Server returned OK but no API key: {result}")
                        return False
                else:
                    error = result.get("error", "Unknown error")
                    print(f"Provisioning failed: {error}")
                    return False

            elif response.status_code == 401:
                print("Invalid bootstrap secret - check your configuration")
                return False

            elif response.status_code == 403:
                print("Provisioning not enabled on server - configure bootstrap secret in admin")
                return False

            else:
                print(f"Server returned {response.status_code}: {response.text[:200]}")

        except requests.exceptions.ConnectionError as e:
            print(f"Connection error: {e}")
        except requests.exceptions.Timeout:
            print("Request timed out")
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
        except json.JSONDecodeError:
            print(f"Invalid JSON response: {response.text[:200]}")

        if attempt < MAX_RETRIES:
            delay = get_retry_delay(attempt)
            logger.info(f"Retrying in {delay:.1f} seconds...")
            print(f"Retrying in {delay:.1f} seconds...")
            time.sleep(delay)

    logger.error(f"Failed to provision after {MAX_RETRIES} attempts")
    print(f"Failed to provision after {MAX_RETRIES} attempts")
    return False


def show_status(settings):
    """Show current provisioning status."""
    print("\n--- Provisioning Status ---")

    device_id = settings.get("device_id", "")
    device_alias = settings.get("device_alias", "")
    api_key = settings.get("remote_api_key", "")
    sync_enabled = settings.get("remote_sync_enabled", False)
    backend_url = settings.get("backend_url", settings.get("remote_sync_url", ""))

    print(f"Device ID:      {device_id or '(not set)'}")
    print(f"Device Alias:   {device_alias or '(not set)'}")
    print(f"Backend URL:    {backend_url or '(not set)'}")
    print(f"API Key:        {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else ''}" if api_key else "API Key:        (not provisioned)")
    print(f"Sync Enabled:   {'Yes' if sync_enabled else 'No'}")

    if api_key:
        print("\nStatus: PROVISIONED ✓")
        return True
    else:
        print("\nStatus: NOT PROVISIONED")
        return False


def run_tests(settings):
    """Run connectivity and provisioning tests, report to server."""
    print("\n" + "=" * 60)
    print("PoolAIssistant Provisioning Tests")
    print("=" * 60)

    results = {
        "device_id": settings.get("device_id", ""),
        "device_alias": settings.get("device_alias", ""),
        "tests": {},
        "overall": "PASS",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    backend_url = settings.get("backend_url", settings.get("remote_sync_url", ""))
    api_key = settings.get("remote_api_key", "")

    # Test 1: Network connectivity
    print("\n[1/5] Testing network connectivity...")
    try:
        response = requests.get("https://www.google.com", timeout=10)
        if response.status_code == 200:
            print("      ✓ Internet connection OK")
            results["tests"]["internet"] = {"status": "PASS", "message": "Connected"}
        else:
            print(f"      ✗ HTTP {response.status_code}")
            results["tests"]["internet"] = {"status": "FAIL", "message": f"HTTP {response.status_code}"}
            results["overall"] = "FAIL"
    except Exception as e:
        print(f"      ✗ Failed: {e}")
        results["tests"]["internet"] = {"status": "FAIL", "message": str(e)}
        results["overall"] = "FAIL"

    # Test 2: Backend reachability
    print("\n[2/5] Testing backend server...")
    if backend_url:
        try:
            response = requests.get(f"{backend_url}/api/health.php", timeout=10)
            if response.status_code == 200:
                print(f"      ✓ Backend reachable: {backend_url}")
                results["tests"]["backend"] = {"status": "PASS", "url": backend_url}
            else:
                print(f"      ✗ HTTP {response.status_code}")
                results["tests"]["backend"] = {"status": "FAIL", "message": f"HTTP {response.status_code}"}
                results["overall"] = "FAIL"
        except Exception as e:
            print(f"      ✗ Failed: {e}")
            results["tests"]["backend"] = {"status": "FAIL", "message": str(e)}
            results["overall"] = "FAIL"
    else:
        print("      ✗ No backend URL configured")
        results["tests"]["backend"] = {"status": "SKIP", "message": "No URL configured"}

    # Test 3: Provisioning status
    print("\n[3/5] Checking provisioning status...")
    if api_key:
        print(f"      ✓ Provisioned with API key: {api_key[:8]}...")
        results["tests"]["provisioned"] = {"status": "PASS", "has_key": True}
    else:
        print("      ○ Not yet provisioned")
        results["tests"]["provisioned"] = {"status": "WARN", "has_key": False}

    # Test 4: API key validation
    print("\n[4/5] Validating API key with server...")
    if api_key and backend_url:
        try:
            response = requests.get(
                f"{backend_url}/api/chunks_status.php",
                headers={"X-API-Key": api_key},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    print(f"      ✓ API key valid - Device: {data.get('device_name', 'Unknown')}")
                    results["tests"]["api_key"] = {"status": "PASS", "device_name": data.get("device_name")}
                else:
                    print(f"      ✗ API key rejected: {data.get('error', 'Unknown')}")
                    results["tests"]["api_key"] = {"status": "FAIL", "message": data.get("error")}
                    results["overall"] = "FAIL"
            elif response.status_code == 401:
                print("      ✗ API key invalid or expired")
                results["tests"]["api_key"] = {"status": "FAIL", "message": "Invalid key"}
                results["overall"] = "FAIL"
            else:
                print(f"      ✗ HTTP {response.status_code}")
                results["tests"]["api_key"] = {"status": "FAIL", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            print(f"      ✗ Failed: {e}")
            results["tests"]["api_key"] = {"status": "FAIL", "message": str(e)}
            results["overall"] = "FAIL"
    else:
        print("      ○ Skipped (no API key)")
        results["tests"]["api_key"] = {"status": "SKIP", "message": "No API key"}

    # Test 5: Report results to server
    print("\n[5/5] Reporting test results to server...")
    if api_key and backend_url:
        try:
            response = requests.post(
                f"{backend_url}/api/device_status.php",
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                json=results,
                timeout=10
            )
            if response.status_code == 200:
                print("      ✓ Results reported to server")
                results["tests"]["report"] = {"status": "PASS"}
            else:
                print(f"      ○ Report failed (HTTP {response.status_code}) - non-critical")
                results["tests"]["report"] = {"status": "WARN", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            print(f"      ○ Report failed: {e} - non-critical")
            results["tests"]["report"] = {"status": "WARN", "message": str(e)}
    else:
        print("      ○ Skipped (no credentials)")
        results["tests"]["report"] = {"status": "SKIP"}

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for t in results["tests"].values() if t.get("status") == "PASS")
    total = len(results["tests"])

    if results["overall"] == "PASS":
        print(f"RESULT: ALL TESTS PASSED ({passed}/{total})")
    else:
        print(f"RESULT: SOME TESTS FAILED ({passed}/{total} passed)")
    print("=" * 60)

    return results["overall"] == "PASS"


def main():
    parser = argparse.ArgumentParser(description="Auto-provision Pi with MOD Projects server")
    parser.add_argument("--force", action="store_true", help="Force re-provisioning even if already done")
    parser.add_argument("--test", action="store_true", help="Run connectivity and provisioning tests")
    parser.add_argument("--status", action="store_true", help="Show current provisioning status")
    args = parser.parse_args()

    settings = load_settings()

    # Handle --status
    if args.status:
        print("=" * 60)
        print("PoolAIssistant Provisioning Status")
        print("=" * 60)
        show_status(settings)
        return 0

    # Handle --test
    if args.test:
        success = run_tests(settings)
        return 0 if success else 1

    # Normal provisioning
    print("=" * 60)
    print("PoolAIssistant Auto-Provisioning")
    print("=" * 60)

    if provision(settings, force=args.force):
        print("Provisioning complete!")
        return 0
    else:
        print("Provisioning skipped or failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
