#!/usr/bin/env bash
#
# health_watchdog.sh - reboot if the Pi has been genuinely unreachable for 10 min
#
# Replaces poolaissistant_ap_manager.sh's auto-failover AP loop. Design goals:
#   1. Never disconnect wlan0 or fight NetworkManager — we only observe.
#   2. Honour the user: if setup-mode AP is on, the Pi IS reachable via
#      192.168.4.1, so strikes reset.
#   3. Respect ethernet-only deployments — a pool-subnet Pi with no WAN
#      but a live eth0 cable is healthy, not stuck.
#   4. Don't reboot during boot (first 15 min) so a long first-boot
#      configuration doesn't end in a reboot loop.
#   5. If we trigger 3+ reboots within an hour, pause ourselves — clearly
#      the reboot didn't fix whatever's wrong, and repeatedly rebooting
#      just damages the SD card.
#
# This file is the Stage-5 replacement for poolaissistant_ap_manager.sh.

set -u

INTERVAL=60                              # seconds between checks
STRIKE_THRESHOLD=10                      # 10 consecutive fails = ~10 min of actual unreachability
MIN_UPTIME=900                           # skip reboot during first 15 min after boot
REBOOT_COOKIE=/var/lib/poolaissistant/watchdog-reboots
AP_STATE=/tmp/poolaissistant_ap_state
LOG_TAG="poolai-watchdog"

mkdir -p "$(dirname "$REBOOT_COOKIE")" 2>/dev/null || true

log() { logger -t "$LOG_TAG" -- "$*"; echo "[$(date '+%F %T')] $*"; }

# --- Health check ------------------------------------------------------------
is_healthy() {
    # Setup AP on → the user is mid-configuration, treat as healthy
    if [[ -f "$AP_STATE" ]]; then
        return 0
    fi

    # Primary check: default route exists AND the gateway responds to ping.
    # We ping the gateway (not 8.8.8.8) because pool-controller deployments
    # often sit on isolated LANs with no internet route.
    local gw
    gw=$(ip -4 route show default 2>/dev/null | awk '/default/ {print $3; exit}')
    if [[ -n "$gw" ]] && ping -c 1 -W 2 "$gw" >/dev/null 2>&1; then
        return 0
    fi

    # Fallback: ethernet-only setups may have no default route, but eth0
    # with a live carrier + an IP is "healthy enough". This is the common
    # pool-subnet deployment.
    if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" == "1" ]]; then
        if ip -4 addr show eth0 2>/dev/null | grep -q "inet "; then
            return 0
        fi
    fi

    return 1
}

# --- Reboot-loop protection --------------------------------------------------
# Count reboots we've triggered in the last hour by reading the cookie.
# If ≥3, refuse to trigger another — something is broken that rebooting
# won't fix, and we'd rather stay up and let the user see the problem.
recent_reboot_count() {
    local hour_ago=$(( $(date +%s) - 3600 ))
    if [[ -f "$REBOOT_COOKIE" ]]; then
        awk -v t="$hour_ago" '$1 > t' "$REBOOT_COOKIE" 2>/dev/null | wc -l
    else
        echo 0
    fi
}

trigger_reboot() {
    local recent
    recent=$(recent_reboot_count)
    if (( recent >= 3 )); then
        log "watchdog paused: ${recent} reboots in last hour, not rebooting again"
        return 1
    fi
    date +%s >> "$REBOOT_COOKIE"
    log "10 minutes unreachable — rebooting (cookie #$((recent + 1)))"
    sync
    sleep 2
    systemctl reboot
    return 0
}

# --- Main loop ---------------------------------------------------------------
log "starting (interval=${INTERVAL}s, threshold=${STRIKE_THRESHOLD})"

strikes=0
while true; do
    sleep "$INTERVAL"

    uptime=$(awk '{print int($1)}' /proc/uptime)
    if (( uptime < MIN_UPTIME )); then
        # Boot grace period — don't count strikes yet. Networking might
        # still be stabilising.
        strikes=0
        continue
    fi

    if is_healthy; then
        if (( strikes > 0 )); then
            log "recovered after $strikes strikes"
        fi
        strikes=0
    else
        strikes=$((strikes + 1))
        log "unhealthy ($strikes/$STRIKE_THRESHOLD)"
        if (( strikes >= STRIKE_THRESHOLD )); then
            if trigger_reboot; then
                # The reboot call returned — should never happen unless
                # systemctl failed. Reset and keep trying.
                strikes=0
            else
                # Reboot suppressed by loop-protection. Reset strikes so
                # we don't spam logs every minute.
                strikes=0
            fi
        fi
    fi
done
