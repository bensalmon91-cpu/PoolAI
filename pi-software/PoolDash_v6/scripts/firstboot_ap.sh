#!/usr/bin/env bash
#
# firstboot_ap.sh - starts the setup AP only on the very first boot of a
# freshly cloned Pi that has no network configuration.
#
# The service that invokes this (poolaissistant-firstboot-ap.service) is
# gated by ConditionPathExists=/opt/PoolAIssistant/data/FIRST_BOOT, so it
# fires at most once — on the first boot after clone_prep.sh. After that,
# the FIRST_BOOT marker is removed and the service never runs again.
#
# Manual AP use (after first boot) happens via ap_control.sh + the
# touchscreen toggle.

set -u

MARKER="/opt/PoolAIssistant/data/FIRST_BOOT"
LOG_TAG="poolai-firstboot-ap"

log() { logger -t "$LOG_TAG" -- "$*"; echo "[$(date '+%F %T')] $*"; }

# We must clear the marker no matter what happens below, or the next boot
# will run us again and potentially drop the user's configured WiFi.
cleanup() { rm -f "$MARKER" 2>/dev/null || true; }
trap cleanup EXIT

# Give NetworkManager a chance to auto-connect to any pre-seeded WiFi
# profile (unlikely on a fresh clone, but possible if the image was
# prepared with one). 30s is the same settle window NM itself uses.
log "first boot detected — waiting up to 30s for networking to settle"
for i in $(seq 1 30); do
    sleep 1
    if nmcli -t -f TYPE,STATE device 2>/dev/null | grep -q '^wifi:connected$'; then
        log "WiFi auto-connected — no AP needed"
        exit 0
    fi
    # If someone plugged in an ethernet cable at the point of first boot,
    # the pool technician can use that to reach the UI directly.
    if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" == "1" ]]; then
        log "ethernet cable present — no AP needed"
        exit 0
    fi
done

log "no network after 30s — starting setup AP for first-boot configuration"
if /usr/local/bin/ap_control.sh start; then
    log "setup AP is up; user should connect phone to 'PoolAI' SSID"
    exit 0
fi

log "ERROR: failed to start setup AP on first boot"
exit 1
