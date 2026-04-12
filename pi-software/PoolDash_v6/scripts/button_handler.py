#!/usr/bin/env python3
"""
PoolAIssistant Physical Button Handler

Monitors a GPIO button for reset/recovery actions.
Default: GPIO3 (Pin 5) - also wakes Pi from halt state

Button Actions:
- Short press (< 2s): Show network status (blink activity LED)
- Long press (5-10s): Forget WiFi networks and enable AP mode
- Very long press (10s+): System reboot (NO data wipe)

Wiring:
  Connect a momentary push button between:
  - GPIO3 (Pin 5) - one terminal
  - GND (Pin 6) - other terminal

  GPIO3 is special - it can also wake the Pi from halt/shutdown state.

  No resistor needed - internal pull-up is enabled in software.
"""

import os
import sys
import time
import subprocess
import json
import logging
from pathlib import Path

# Configuration
BUTTON_GPIO = 3  # GPIO3 (Pin 5) - also used for wake from halt
LED_GPIO = None  # Set to GPIO number if you have a status LED
DEBOUNCE_TIME = 0.05  # 50ms debounce

SHORT_PRESS_MAX = 2.0  # Seconds
LONG_PRESS_MIN = 5.0   # Seconds for network reset
REBOOT_MIN = 10.0  # Seconds for system reboot

DATA_DIR = Path("/opt/PoolAIssistant/data")
APP_DIR = Path("/opt/PoolAIssistant/app")
SETTINGS_FILE = DATA_DIR / "pooldash_settings.json"
LOG_FILE = DATA_DIR / "button_handler.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO not available - button handler disabled")
    GPIO_AVAILABLE = False


def blink_led(times=3, interval=0.2):
    """Blink status LED if configured."""
    if LED_GPIO is None or not GPIO_AVAILABLE:
        return

    try:
        GPIO.setup(LED_GPIO, GPIO.OUT)
        for _ in range(times):
            GPIO.output(LED_GPIO, GPIO.HIGH)
            time.sleep(interval)
            GPIO.output(LED_GPIO, GPIO.LOW)
            time.sleep(interval)
    except Exception as e:
        logger.error(f"LED blink error: {e}")


def run_command(cmd, timeout=30):
    """Run a shell command and return success status."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {cmd}")
        return False
    except Exception as e:
        logger.error(f"Command failed: {cmd} - {e}")
        return False


def show_network_status():
    """Short press action: Show network status."""
    logger.info("Short press detected - showing network status")
    blink_led(times=2, interval=0.1)

    # Log current network status
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"],
            capture_output=True, text=True, timeout=5
        )
        logger.info(f"Network status:\n{result.stdout}")
    except Exception as e:
        logger.error(f"Could not get network status: {e}")


def reset_network():
    """Long press action: Reset network settings and force AP mode."""
    logger.info("Long press detected - resetting network settings")
    blink_led(times=5, interval=0.1)

    # Stop WiFi connections
    logger.info("Disconnecting WiFi...")
    run_command("nmcli device disconnect wlan0")

    # Delete all saved WiFi connections
    logger.info("Deleting saved WiFi networks...")
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if ':wifi' in line or ':802-11-wireless' in line:
                name = line.split(':')[0]
                run_command(f'nmcli con delete "{name}"')
                logger.info(f"Deleted WiFi connection: {name}")
    except Exception as e:
        logger.error(f"Error deleting WiFi connections: {e}")

    # Reset ethernet to DHCP
    logger.info("Resetting ethernet to DHCP...")
    run_command("nmcli con mod 'Wired connection 1' ipv4.method auto ipv4.addresses '' ipv4.gateway '' 2>/dev/null || true")

    # Force restart AP manager
    logger.info("Restarting AP manager...")
    run_command("systemctl restart poolaissistant_ap_manager.service")

    logger.info("Network reset complete - AP should be available shortly")
    blink_led(times=3, interval=0.3)


def system_reboot():
    """Very long press action: System reboot (NO data wipe)."""
    logger.info("Very long press detected - performing system reboot")
    blink_led(times=10, interval=0.05)

    logger.info("Rebooting system...")
    # Give time for LED feedback to complete
    time.sleep(0.5)
    run_command("sudo reboot")


def handle_button_press(duration):
    """Handle button press based on duration."""
    if duration < SHORT_PRESS_MAX:
        show_network_status()
    elif duration < REBOOT_MIN:
        reset_network()
    else:
        system_reboot()


def button_callback(channel):
    """Callback when button is pressed (falling edge)."""
    # Debounce
    time.sleep(DEBOUNCE_TIME)
    if GPIO.input(channel) == GPIO.HIGH:
        return  # False trigger

    # Wait for button release and measure duration
    press_start = time.time()

    while GPIO.input(channel) == GPIO.LOW:
        duration = time.time() - press_start

        # Provide feedback for long press thresholds
        if duration >= REBOOT_MIN and int(duration * 10) % 5 == 0:
            blink_led(times=1, interval=0.05)
        elif duration >= LONG_PRESS_MIN and int(duration * 10) % 10 == 0:
            blink_led(times=1, interval=0.1)

        time.sleep(0.1)

        # Safety limit
        if duration > 30:
            logger.warning("Button held too long - ignoring")
            return

    duration = time.time() - press_start
    logger.info(f"Button pressed for {duration:.1f} seconds")

    handle_button_press(duration)


def main():
    """Main entry point."""
    if not GPIO_AVAILABLE:
        logger.error("GPIO not available - exiting")
        sys.exit(1)

    logger.info(f"Starting button handler on GPIO{BUTTON_GPIO}")

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Add event detection
        GPIO.add_event_detect(
            BUTTON_GPIO,
            GPIO.FALLING,
            callback=button_callback,
            bouncetime=200
        )

        logger.info("Button handler ready")
        logger.info(f"  Short press (<{SHORT_PRESS_MAX}s): Show status")
        logger.info(f"  Long press ({LONG_PRESS_MIN}-{REBOOT_MIN}s): Forget WiFi + enable AP")
        logger.info(f"  Very long press (>{REBOOT_MIN}s): System reboot")

        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
