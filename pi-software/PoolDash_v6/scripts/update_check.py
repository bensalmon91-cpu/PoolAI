#!/usr/bin/env python3
"""
Check for updates on the backend and download/apply if available.

Usage:
    python update_check.py              # Check and download if available
    python update_check.py --check      # Fresh check without downloading
    python update_check.py --apply      # Check, download, and auto-apply
    python update_check.py --status     # Show current update status
    python update_check.py --force      # Force re-check ignoring cache
"""

import hashlib
import json
import logging
import os
import sys
import tarfile
import shutil
import socket
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path("/opt/PoolAIssistant/data")
APP_DIR = Path("/opt/PoolAIssistant/app")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
STATUS_FILE = DATA_DIR / "update_status.json"
DOWNLOAD_DIR = DATA_DIR / "updates"

# HARDCODED UPDATE SERVER - survives clone prep, always works
UPDATE_SERVER_URL = "https://poolaissistant.modprojects.co.uk"

# Trust: a server-compromise attacker can replace the tarball AND its
# checksum. Signature verification closes that gap - the private key lives
# off-server, the public key is baked into every installed copy.
TRUST_DIR = APP_DIR / "trust"
SIGNING_KEY_PUB = TRUST_DIR / "update_signing_key.pub"

# Rollout flag: until every published update carries a signature, we permit
# unsigned updates with a logged warning. Once operations has been signing
# for one full release cycle, flip this to True (or drop a file named
# `require_signature` into TRUST_DIR, which takes precedence).
REQUIRE_SIGNATURE_DEFAULT = False

# How long before a cached error is considered stale and auto-refreshed
ERROR_CACHE_EXPIRY_MINUTES = 5


def check_network_connectivity():
    """
    Check if we have basic network connectivity before attempting update check.
    Returns (is_connected, error_message).
    """
    # Test 1: Can we resolve a well-known domain?
    try:
        socket.setdefaulttimeout(5)
        socket.gethostbyname("google.com")
    except socket.gaierror:
        return False, "DNS resolution failed - no internet connection"
    except socket.timeout:
        return False, "DNS resolution timed out - network may be slow"
    except Exception as e:
        return False, f"DNS check failed: {e}"

    # Test 2: Can we connect to the internet?
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
    except (socket.timeout, socket.error):
        return False, "Cannot reach internet - check network connection"

    # Test 3: Can we resolve our update server specifically?
    try:
        socket.gethostbyname("poolaissistant.modprojects.co.uk")
    except socket.gaierror:
        return False, "Cannot resolve update server - DNS may be misconfigured"
    except Exception as e:
        return False, f"Server DNS check failed: {e}"

    return True, None


def create_retry_session(retries=3, backoff_factor=0.5):
    """Create a requests session with retry logic for transient failures."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def is_status_stale_error(status):
    """Check if cached status is an error that's older than the expiry threshold."""
    if not status:
        return False
    if status.get("status") != "error":
        return False

    updated_at = status.get("updated_at")
    if not updated_at:
        return True  # No timestamp, consider stale

    try:
        last_update = datetime.fromisoformat(updated_at)
        expiry_time = last_update + timedelta(minutes=ERROR_CACHE_EXPIRY_MINUTES)
        return datetime.now() > expiry_time
    except (ValueError, TypeError):
        return True  # Can't parse timestamp, consider stale


def safe_tar_extract(tar: tarfile.TarFile, dest_dir: Path) -> bool:
    """
    Safely extract tar archive, preventing directory traversal attacks.

    Validates that all extracted files stay within dest_dir.
    Returns True if extraction was safe and successful.
    """
    dest_dir = dest_dir.resolve()

    for member in tar.getmembers():
        # Resolve the full path where this member would be extracted
        member_path = (dest_dir / member.name).resolve()

        # Check if the resolved path is within dest_dir
        try:
            member_path.relative_to(dest_dir)
        except ValueError:
            # Path is outside dest_dir - this is a directory traversal attempt
            logger.error(f"Blocked directory traversal attempt: {member.name}")
            return False

        # Check for suspicious absolute paths
        if member.name.startswith('/') or member.name.startswith('\\'):
            logger.error(f"Blocked absolute path in archive: {member.name}")
            return False

        # Check for suspicious path components
        if '..' in member.name.split('/') or '..' in member.name.split('\\'):
            logger.error(f"Blocked suspicious path: {member.name}")
            return False

    # All members are safe, extract them
    # Use filter='data' on Python 3.12+ for additional safety
    try:
        # Python 3.12+ has the filter parameter
        tar.extractall(dest_dir, filter='data')
    except TypeError:
        # Older Python versions don't have filter parameter
        tar.extractall(dest_dir)

    return True


def load_settings():
    """Load settings from JSON file."""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def get_current_version():
    """Get current software version."""
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return os.environ.get("SOFTWARE_VERSION", "0.0.0")


def write_status(status_data):
    """Write update status to file."""
    status_data["updated_at"] = datetime.now().isoformat()
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATUS_FILE, "w") as f:
            json.dump(status_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write status file: {e}")


def read_status():
    """Read current update status."""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def sha256_file(path):
    """Calculate SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_for_updates(settings, current_version, skip_network_check=False):
    """Check server for available updates.

    Args:
        settings: Settings dictionary
        current_version: Current software version string
        skip_network_check: If True, skip network pre-check (for forced checks)

    Returns:
        Tuple of (update_info dict or None, error message or None)
    """
    # Pre-check network connectivity unless skipped
    if not skip_network_check:
        is_connected, net_error = check_network_connectivity()
        if not is_connected:
            logger.warning(f"Network pre-check failed: {net_error}")
            return None, f"No network: {net_error}"

    # Always use hardcoded server URL - this must survive clone prep
    backend_url = UPDATE_SERVER_URL

    # API key is optional for update checks (public updates)
    api_key = settings.get("api_key") or settings.get("remote_api_key", "")

    check_url = f"{backend_url}/api/updates/check.php"

    try:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        # Use session with retry logic for transient failures
        session = create_retry_session(retries=3, backoff_factor=1.0)

        response = session.get(
            check_url,
            headers=headers,
            params={"current_version": current_version},
            timeout=30
        )

        if response.status_code == 200:
            try:
                return response.json(), None
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from server: {e}")
                return None, f"Server returned invalid JSON: {e}"
        else:
            return None, f"Server returned {response.status_code}: {response.text}"

    except requests.exceptions.Timeout:
        logger.warning("Update check timed out")
        return None, "Connection timed out - server may be slow"
    except requests.exceptions.ConnectionError as e:
        error_str = str(e)
        # Provide more helpful error messages
        if "NameResolutionError" in error_str or "Failed to resolve" in error_str:
            logger.warning(f"DNS resolution failed: {e}")
            return None, "DNS resolution failed - check network connection"
        elif "Connection refused" in error_str:
            logger.warning(f"Connection refused: {e}")
            return None, "Server connection refused - server may be down"
        else:
            logger.warning(f"Connection error during update check: {e}")
            return None, f"Connection failed - check network"
    except requests.exceptions.RequestException as e:
        logger.exception(f"Request failed: {e}")
        return None, f"Request failed: {e}"


def _signature_required() -> bool:
    """Hard-fail unsigned updates iff ops has opted in (marker file or flag)."""
    if (TRUST_DIR / "require_signature").is_file():
        return True
    return REQUIRE_SIGNATURE_DEFAULT


def verify_ed25519_signature(tarball_path, signature_path, pubkey_path):
    """Verify a detached Ed25519 signature. Returns (ok: bool, error: str|None)."""
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key, load_ssh_public_key
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:
        return False, f"cryptography library not installed: {e}"

    try:
        pubkey_bytes = pubkey_path.read_bytes()
    except OSError as e:
        return False, f"cannot read public key: {e}"

    # Accept either PEM or OpenSSH format (both are common for Ed25519).
    pubkey = None
    for loader in (load_pem_public_key, load_ssh_public_key):
        try:
            candidate = loader(pubkey_bytes)
            if isinstance(candidate, Ed25519PublicKey):
                pubkey = candidate
                break
        except Exception:
            continue
    if pubkey is None:
        return False, "public key is not a recognised Ed25519 key"

    try:
        sig = signature_path.read_bytes()
    except OSError as e:
        return False, f"cannot read signature: {e}"
    try:
        data = tarball_path.read_bytes()
    except OSError as e:
        return False, f"cannot read tarball: {e}"

    try:
        pubkey.verify(sig, data)
    except InvalidSignature:
        return False, "signature does not match public key"
    except Exception as e:
        return False, f"verification error: {e}"
    return True, None


def download_signature(download_url, api_key):
    """Fetch <tarball_url>.sig; returns (bytes, None) or (None, error_str)."""
    sig_url = download_url + ".sig"
    try:
        headers = {"X-API-Key": api_key} if api_key else {}
        r = requests.get(sig_url, headers=headers, timeout=60)
    except requests.RequestException as e:
        return None, f"signature fetch failed: {e}"
    if r.status_code == 404:
        return None, "not_found"
    if r.status_code != 200:
        return None, f"signature fetch HTTP {r.status_code}"
    return r.content, None


def download_update(settings, version, download_url, expected_checksum):
    """Download update package."""
    # Always use hardcoded server URL
    backend_url = UPDATE_SERVER_URL

    # API key is optional
    api_key = settings.get("api_key") or settings.get("remote_api_key", "")

    # Make URL absolute if needed
    if download_url.startswith("/"):
        download_url = backend_url + download_url

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Determine filename from URL or version
    filename = f"update-v{version}.tar.gz"
    download_path = DOWNLOAD_DIR / filename

    print(f"Downloading update v{version}...")

    try:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = requests.get(
            download_url,
            headers=headers,
            stream=True,
            timeout=300
        )

        if response.status_code != 200:
            return None, f"Download failed: {response.status_code}"

        with open(download_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Verify checksum
        if expected_checksum:
            actual_checksum = sha256_file(download_path)
            if actual_checksum.lower() != expected_checksum.lower():
                download_path.unlink()
                return None, f"Checksum mismatch! Expected {expected_checksum[:16]}..., got {actual_checksum[:16]}..."

        # Verify signature (Ed25519). Trust lives in TRUST_DIR on this Pi,
        # not in what the server says - so a server compromise alone
        # cannot push code.
        signature_required = _signature_required()
        if SIGNING_KEY_PUB.is_file():
            sig_bytes, sig_err = download_signature(download_url, api_key)
            if sig_bytes is None:
                msg = f"Update signature unavailable: {sig_err}"
                if signature_required:
                    download_path.unlink(missing_ok=True)
                    logger.error(msg + " (refusing to install unsigned update)")
                    return None, msg
                logger.warning(msg + " (proceeding in permissive mode)")
            else:
                sig_path = download_path.with_suffix(download_path.suffix + ".sig")
                sig_path.write_bytes(sig_bytes)
                ok, verify_err = verify_ed25519_signature(
                    download_path, sig_path, SIGNING_KEY_PUB
                )
                if not ok:
                    download_path.unlink(missing_ok=True)
                    sig_path.unlink(missing_ok=True)
                    logger.error(f"Update signature INVALID: {verify_err}")
                    return None, f"Signature verification failed: {verify_err}"
                logger.info("Update signature verified (Ed25519)")
        else:
            msg = f"No signing public key installed at {SIGNING_KEY_PUB}"
            if signature_required:
                download_path.unlink(missing_ok=True)
                return None, msg + " (refusing to install unsigned update)"
            logger.warning(msg + " (update accepted on checksum only)")

        print(f"Downloaded and verified: {download_path}")
        return download_path, None

    except Exception as e:
        return None, f"Download error: {e}"


def rollback_update():
    """Rollback to previous version from backup."""
    backup_dir = APP_DIR.parent / "app_backup"

    if not backup_dir.exists():
        return False, "No backup available for rollback"

    print("Rolling back to previous version...")

    try:
        # Remove current app files (except data/instance)
        for item in APP_DIR.iterdir():
            if item.name in ("instance", "__pycache__"):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Restore from backup
        for item in backup_dir.iterdir():
            target = APP_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

        print("Rollback completed successfully!")
        return True, None

    except Exception as e:
        return False, f"Rollback failed: {e}"


def verify_update():
    """Verify the update was successful by checking critical files and imports."""
    critical_files = [
        APP_DIR / "pooldash_app" / "__init__.py",
        APP_DIR / "VERSION",
    ]

    for f in critical_files:
        if not f.exists():
            return False, f"Critical file missing: {f.name}"

    # Try to import the main module
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "pooldash_app",
            APP_DIR / "pooldash_app" / "__init__.py"
        )
        if spec is None:
            return False, "Cannot load app module spec"
    except Exception as e:
        return False, f"Import verification failed: {e}"

    return True, None


def apply_update(archive_path):
    """Apply update from downloaded archive with automatic rollback on failure."""
    staging_dir = APP_DIR.parent / "app_update_staging"
    backup_dir = APP_DIR.parent / "app_backup"

    # Clean staging area
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    print(f"Extracting update to staging area...")

    try:
        # Extract archive safely
        if not tarfile.is_tarfile(archive_path):
            return False, "Update archive is not a valid tar file"

        with tarfile.open(archive_path, "r:*") as tar:
            if not safe_tar_extract(tar, staging_dir):
                return False, "Archive contains unsafe paths (possible directory traversal attack)"

        # Backup current app (just the main files, not data)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        # Copy current app to backup
        shutil.copytree(APP_DIR, backup_dir, ignore=shutil.ignore_patterns(
            "instance", "__pycache__", "*.pyc", "*.sqlite3"
        ))
        print("Backup created successfully")

        # Move staged files into app dir
        for item in staging_dir.iterdir():
            target = APP_DIR / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))

        # Cleanup staging
        shutil.rmtree(staging_dir)

        # Verify the update
        print("Verifying update...")
        ok, error = verify_update()
        if not ok:
            print(f"Update verification failed: {error}")
            print("Initiating automatic rollback...")
            rollback_ok, rollback_error = rollback_update()
            if rollback_ok:
                return False, f"Update failed verification ({error}), rolled back successfully"
            else:
                return False, f"Update failed ({error}) AND rollback failed ({rollback_error})"

        print("Update applied and verified successfully!")

        import subprocess

        # Install any new Python dependencies
        print("Installing dependencies...")
        requirements_file = APP_DIR / "requirements.txt"
        if requirements_file.exists():
            try:
                result = subprocess.run(
                    ["/opt/PoolAIssistant/venv/bin/pip", "install", "-r", str(requirements_file), "-q"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print("  Dependencies installed successfully")
                else:
                    print(f"  Warning: pip install failed: {result.stderr}")
            except Exception as e:
                print(f"  Warning: Could not install dependencies: {e}")

        # Run post-update migrations. Currently seeds /etc/poolai/bootstrap.secret
        # from the per-device settings.json so the new env/file-based persist.py
        # has the secret to load. Idempotent; no-op if already migrated.
        print("Running post-update migrations...")
        migrate_script = APP_DIR / "scripts" / "migrate_bootstrap_secret.sh"
        if migrate_script.exists():
            try:
                result = subprocess.run(
                    ["sudo", "bash", str(migrate_script)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    print("  Post-update migrations applied")
                elif result.returncode == 3:
                    # No bootstrap_secret in settings - not fatal; secret may
                    # have been provisioned by the installer via another path.
                    print("  No pre-existing bootstrap secret to migrate (ok)")
                else:
                    print(f"  Migration warning: {result.stderr.strip()}")
            except Exception as e:
                print(f"  Migration skipped: {e}")
        else:
            print("  migrate_bootstrap_secret.sh not present - skipping")

        # Configure firewall for port 80 using robust ports script
        print("Configuring firewall...")
        ports_script = APP_DIR / "scripts" / "ensure_ports.sh"
        if ports_script.exists():
            try:
                result = subprocess.run(
                    ["sudo", str(ports_script)],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    print("  Firewall configured successfully")
                else:
                    print(f"  Firewall config warning: {result.stderr}")
            except Exception as e:
                print(f"  Firewall config skipped: {e}")
        else:
            # Fallback to direct UFW commands if script doesn't exist
            try:
                result = subprocess.run(["ufw", "status"], capture_output=True, text=True)
                if "Status: active" in result.stdout:
                    subprocess.run(["ufw", "allow", "80/tcp"], capture_output=True)
                    subprocess.run(["ufw", "delete", "allow", "8080/tcp"], capture_output=True)
                    print("  Firewall: port 80 opened, port 8080 closed")
            except Exception as e:
                print(f"  Firewall config skipped: {e}")

        # Remove nginx completely - Flask now runs directly on port 80
        print("Removing nginx (if installed)...")
        try:
            # Stop first
            subprocess.run(
                ["sudo", "systemctl", "stop", "nginx"],
                capture_output=True, text=True, timeout=30
            )
            # Uninstall
            result = subprocess.run(
                ["sudo", "apt-get", "remove", "-y", "--purge", "nginx", "nginx-common"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print("  nginx removed successfully")
            else:
                print("  nginx not installed")
            # Clean up
            subprocess.run(
                ["sudo", "apt-get", "autoremove", "-y"],
                capture_output=True, text=True, timeout=60
            )
        except Exception as e:
            print(f"  nginx removal skipped: {e}")

        # Run system dependency check (installs hostapd, dnsmasq, etc. if missing)
        print("Checking system dependencies...")
        deps_script = APP_DIR / "scripts" / "ensure_dependencies.sh"
        if deps_script.exists():
            try:
                result = subprocess.run(
                    ["sudo", str(deps_script)],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    print("  System dependencies verified")
                else:
                    print(f"  Warning: dependency check had issues: {result.stderr}")
            except Exception as e:
                print(f"  Warning: Could not run dependency check: {e}")

        # Check if device needs provisioning (no API key)
        print("Checking device provisioning...")
        try:
            settings_path = DATA_DIR / "pooldash_settings.json"
            needs_provision = True
            if settings_path.exists():
                with open(settings_path) as f:
                    settings = json.load(f)
                    if settings.get("remote_api_key"):
                        needs_provision = False
                        print("  Device already provisioned")

            if needs_provision:
                print("  API key missing - running auto-provision...")
                provision_script = APP_DIR / "scripts" / "auto_provision.py"
                if provision_script.exists():
                    result = subprocess.run(
                        ["sudo", "python3", str(provision_script)],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        print("  Device provisioned successfully")
                    else:
                        print(f"  Warning: provisioning had issues: {result.stderr}")
                else:
                    print(f"  Warning: provision script not found")
        except Exception as e:
            print(f"  Warning: Could not check/run provisioning: {e}")

        # Ensure update_check timer is installed (self-healing)
        print("Ensuring update timer is installed...")
        try:
            timer_installed = subprocess.run(
                ["systemctl", "is-enabled", "update_check.timer"],
                capture_output=True, text=True
            ).returncode == 0

            if not timer_installed:
                # Copy service and timer files to systemd
                service_src = APP_DIR / "scripts" / "update_check.service"
                timer_src = APP_DIR / "scripts" / "update_check.timer"

                if service_src.exists() and timer_src.exists():
                    subprocess.run(
                        ["sudo", "cp", str(service_src), "/etc/systemd/system/"],
                        capture_output=True, text=True, timeout=30
                    )
                    subprocess.run(
                        ["sudo", "cp", str(timer_src), "/etc/systemd/system/"],
                        capture_output=True, text=True, timeout=30
                    )
                    subprocess.run(
                        ["sudo", "systemctl", "daemon-reload"],
                        capture_output=True, text=True, timeout=30
                    )
                    subprocess.run(
                        ["sudo", "systemctl", "enable", "update_check.timer"],
                        capture_output=True, text=True, timeout=30
                    )
                    subprocess.run(
                        ["sudo", "systemctl", "start", "update_check.timer"],
                        capture_output=True, text=True, timeout=30
                    )
                    print("  Update timer installed and enabled")
                else:
                    print("  Warning: update timer files not found")
            else:
                print("  Update timer already installed")
        except Exception as e:
            print(f"  Warning: Could not install update timer: {e}")

        # Run maintenance logs migration (merge into pool_readings.sqlite3)
        print("Running database migrations...")
        migration_script = APP_DIR / "scripts" / "migrate_maintenance_logs.py"
        if migration_script.exists():
            try:
                result = subprocess.run(
                    ["python3", str(migration_script)],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print("  Maintenance logs migration completed")
                else:
                    # Migration may not be needed (fresh install), that's OK
                    print(f"  Migration note: {result.stdout.strip().split(chr(10))[-1] if result.stdout else 'completed'}")
            except Exception as e:
                print(f"  Warning: Could not run migration: {e}")
        else:
            print("  Migration script not found (may be older version)")

        print("Restart the service to use the new version:")
        print("  sudo systemctl restart poolaissistant_ui")

        return True, None

    except Exception as e:
        # Try to rollback on any error
        print(f"Update failed: {e}")
        if backup_dir.exists():
            print("Attempting automatic rollback...")
            rollback_ok, rollback_error = rollback_update()
            if rollback_ok:
                return False, f"Update failed ({e}), rolled back successfully"
            else:
                return False, f"Update failed ({e}) AND rollback failed ({rollback_error})"
        return False, f"Apply failed: {e}"


def main():
    parser = argparse.ArgumentParser(description="Check for and apply software updates")
    parser.add_argument("--check", action="store_true", help="Check for updates (fresh check, no download)")
    parser.add_argument("--apply", action="store_true", help="Auto-apply update if available")
    parser.add_argument("--status", action="store_true", help="Show current update status")
    parser.add_argument("--force", action="store_true", help="Force re-check even if recently checked")
    args = parser.parse_args()

    settings = load_settings()
    current_version = get_current_version()

    if args.status:
        status = read_status()
        print(f"Current version: {current_version}")

        # Auto-refresh if cached status is a stale error
        if is_status_stale_error(status):
            print(f"Last check failed {ERROR_CACHE_EXPIRY_MINUTES}+ minutes ago, retrying...")
            update_info, error = check_for_updates(settings, current_version)
            if error:
                print(f"Still failing: {error}")
                write_status({
                    "status": "error",
                    "message": error,
                    "update_available": False,
                    "current_version": current_version
                })
            elif update_info:
                available = update_info.get("update_available", False)
                print(f"Update available: {available}")
                if available:
                    print(f"Available version: {update_info.get('version')}")
                write_status({
                    "status": "ok",
                    "message": "Update check successful",
                    "update_available": available,
                    "current_version": current_version,
                    "version": update_info.get("version") if available else None,
                    "latest_version": update_info.get("latest_version", current_version)
                })
            return 0

        # Show cached status
        if status:
            print(f"Last check: {status.get('updated_at', 'never')}")
            print(f"Update available: {status.get('update_available', False)}")
            if status.get("version"):
                print(f"Available version: {status.get('version')}")
            if status.get("message"):
                print(f"Status: {status.get('message')}")
        else:
            print("No previous update check - run with --check or --force")
        return 0

    # --check: Just check for updates, don't download
    if args.check:
        print(f"Current version: {current_version}")
        print("Checking for updates...")

        update_info, error = check_for_updates(settings, current_version)

        if error:
            print(f"Error: {error}")
            write_status({
                "status": "error",
                "message": error,
                "update_available": False,
                "current_version": current_version
            })
            return 1

        if not update_info.get("update_available"):
            print("You are running the latest version.")
            write_status({
                "status": "ok",
                "message": "No updates available",
                "update_available": False,
                "current_version": current_version,
                "latest_version": update_info.get("latest_version", current_version)
            })
        else:
            new_version = update_info.get("version")
            description = update_info.get("description", "")
            print(f"\nUpdate available: v{new_version}")
            if description:
                print(f"Description: {description}")
            print(f"\nTo download and apply, run:")
            print(f"  python3 {__file__} --apply")
            write_status({
                "status": "ok",
                "message": "Update available",
                "update_available": True,
                "current_version": current_version,
                "version": new_version
            })
        return 0

    print(f"Current version: {current_version}")
    print("Checking for updates...")

    # When --force is used, skip network pre-check (user explicitly wants to retry)
    update_info, error = check_for_updates(
        settings, current_version,
        skip_network_check=args.force
    )

    if error:
        print(f"Error: {error}")
        write_status({
            "status": "error",
            "message": error,
            "update_available": False,
            "current_version": current_version
        })
        return 1

    if not update_info.get("update_available"):
        print("You are running the latest version.")
        write_status({
            "status": "ok",
            "message": "No updates available",
            "update_available": False,
            "current_version": current_version,
            "latest_version": update_info.get("latest_version", current_version),
            "download_path": None,  # Clear any old download path
            "applied": False
        })
        return 0

    # Update available
    new_version = update_info.get("version")
    download_url = update_info.get("download_url")
    checksum = update_info.get("checksum")
    description = update_info.get("description", "")

    print(f"\nUpdate available: v{new_version}")
    if description:
        print(f"Description: {description}")

    # Download
    download_path, error = download_update(settings, new_version, download_url, checksum)

    if error:
        print(f"Download error: {error}")
        write_status({
            "status": "error",
            "message": error,
            "update_available": True,
            "current_version": current_version,
            "version": new_version
        })
        return 1

    status_data = {
        "status": "ok",
        "message": "Update downloaded",
        "update_available": True,
        "current_version": current_version,
        "version": new_version,
        "download_path": str(download_path),
        "applied": False
    }

    if args.apply:
        print("\nApplying update...")
        success, error = apply_update(download_path)
        if success:
            status_data["message"] = "Update applied successfully"
            status_data["applied"] = True
            status_data["update_available"] = False  # No longer pending
            status_data["current_version"] = new_version  # Update to new version
            status_data["download_path"] = None  # Clear download path
        else:
            status_data["status"] = "error"
            status_data["message"] = f"Apply failed: {error}"
            print(f"Error: {error}")

    write_status(status_data)

    if not args.apply:
        print(f"\nTo apply the update, run:")
        print(f"  python3 {__file__} --apply")
        print(f"Or manually extract: {download_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
