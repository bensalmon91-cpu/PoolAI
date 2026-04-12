#!/bin/bash
#
# boot_check.sh - PoolAIssistant Boot Sequence Check
#
# This script runs at boot to:
# 1. Check if this is a cloned device that needs configuration
# 2. Verify connection to configured pool controllers
# 3. Log status and optionally trigger first-boot setup
#
# Exit codes:
#   0 = All checks passed
#   1 = Clone detected, needs configuration
#   2 = Controller connection failed
#   3 = Configuration error

set -e

# Paths
APP_DIR="/opt/PoolAIssistant"
DATA_DIR="${APP_DIR}/data"
SETTINGS_FILE="${DATA_DIR}/pooldash_settings.json"
# Check both locations for FIRST_BOOT marker (clone_prep creates in both for compatibility)
FIRST_BOOT_MARKER="${DATA_DIR}/FIRST_BOOT"
FIRST_BOOT_MARKER_ALT="${APP_DIR}/FIRST_BOOT"
PRE_CONFIGURED_MARKER="${DATA_DIR}/PRE_CONFIGURED"
LOG_FILE="${DATA_DIR}/boot_check.log"
STATUS_FILE="${DATA_DIR}/boot_status.json"

# Ensure data directory exists
mkdir -p "$DATA_DIR"

# Logging function
log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
}

# Write status to JSON file for UI to read
write_status() {
    local status="$1"
    local message="$2"
    local is_clone="$3"
    local controllers_ok="$4"
    cat > "$STATUS_FILE" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "status": "$status",
    "message": "$message",
    "is_clone": $is_clone,
    "controllers_ok": $controllers_ok,
    "checks": {
        "first_boot_marker": $([ -f "$FIRST_BOOT_MARKER" ] || [ -f "$FIRST_BOOT_MARKER_ALT" ] && echo "true" || echo "false"),
        "pre_configured": $([ -f "$PRE_CONFIGURED_MARKER" ] && echo "true" || echo "false"),
        "settings_exist": $([ -f "$SETTINGS_FILE" ] && echo "true" || echo "false"),
        "device_id_set": $(grep -q '"device_id":\s*"[^"]\+"' "$SETTINGS_FILE" 2>/dev/null && echo "true" || echo "false")
    }
}
EOF
}

# Check if this is a clone that needs configuration
check_clone_status() {
    log "INFO" "Checking clone status..."

    # Check 1: FIRST_BOOT marker exists (check both locations)
    if [ -f "$FIRST_BOOT_MARKER" ] || [ -f "$FIRST_BOOT_MARKER_ALT" ]; then
        log "WARN" "FIRST_BOOT marker found - this is a fresh clone"
        return 1
    fi

    # Check 2: Settings file doesn't exist
    if [ ! -f "$SETTINGS_FILE" ]; then
        log "WARN" "Settings file not found - this appears to be unconfigured"
        return 1
    fi

    # Check 3: No device_id set (empty or missing)
    if ! grep -q '"device_id":\s*"[a-f0-9-]\{36\}"' "$SETTINGS_FILE" 2>/dev/null; then
        log "WARN" "No valid device_id found - may need provisioning"
        # This is a soft warning, not necessarily a clone
    fi

    # Check 4: No controllers configured
    local controller_count=$(python3 -c "
import json
try:
    with open('$SETTINGS_FILE') as f:
        data = json.load(f)
    controllers = data.get('controllers', [])
    enabled = [c for c in controllers if c.get('enabled', True)]
    print(len(enabled))
except:
    print(0)
" 2>/dev/null)

    if [ "$controller_count" = "0" ]; then
        log "WARN" "No controllers configured"
        return 1
    fi

    # Check 5: PRE_CONFIGURED marker (skip interactive setup)
    if [ -f "$PRE_CONFIGURED_MARKER" ]; then
        log "INFO" "PRE_CONFIGURED marker found - using pre-shipped configuration"
    fi

    log "INFO" "Clone check passed - device appears configured"
    return 0
}

# Test connection to a single controller
test_controller() {
    local host="$1"
    local port="${2:-502}"
    local timeout=5

    # Test 1: Ping
    if ! ping -c 1 -W "$timeout" "$host" > /dev/null 2>&1; then
        log "WARN" "Controller $host - ping failed"
        return 1
    fi

    # Test 2: TCP port (Modbus)
    if ! timeout "$timeout" bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
        log "WARN" "Controller $host:$port - TCP connection failed"
        return 1
    fi

    log "INFO" "Controller $host:$port - OK"
    return 0
}

# Check all configured controllers
check_controllers() {
    log "INFO" "Checking controller connections..."

    if [ ! -f "$SETTINGS_FILE" ]; then
        log "ERROR" "Settings file not found, cannot check controllers"
        return 1
    fi

    # Extract controllers from settings
    local controllers=$(python3 -c "
import json
try:
    with open('$SETTINGS_FILE') as f:
        data = json.load(f)
    for c in data.get('controllers', []):
        if c.get('enabled', True):
            print(f\"{c.get('host', '')}:{c.get('port', 502)}:{c.get('name', 'Unknown')}\")
except Exception as e:
    pass
" 2>/dev/null)

    if [ -z "$controllers" ]; then
        log "WARN" "No enabled controllers found in settings"
        return 1
    fi

    local all_ok=true
    local ok_count=0
    local fail_count=0

    while IFS=: read -r host port name; do
        if [ -n "$host" ]; then
            if test_controller "$host" "$port"; then
                ((ok_count++)) || true
            else
                ((fail_count++)) || true
                all_ok=false
            fi
        fi
    done <<< "$controllers"

    log "INFO" "Controller check complete: $ok_count OK, $fail_count failed"

    if [ "$all_ok" = true ]; then
        return 0
    else
        return 1
    fi
}

# Main boot check sequence
main() {
    log "INFO" "=========================================="
    log "INFO" "PoolAIssistant Boot Check Starting"
    log "INFO" "=========================================="

    local is_clone=false
    local controllers_ok=false
    local exit_code=0

    # Step 1: Check if this is a clone
    if ! check_clone_status; then
        is_clone=true
        log "WARN" "Device appears to be a clone or unconfigured"

        # If FIRST_BOOT marker exists, suggest running first_boot_setup
        if [ -f "$FIRST_BOOT_MARKER" ] || [ -f "$FIRST_BOOT_MARKER_ALT" ]; then
            log "INFO" "Run first_boot_setup.sh to configure this device"
            write_status "needs_setup" "Fresh clone detected - run first_boot_setup.sh" true false
            exit 1
        fi
    fi

    # Step 2: Check controller connections (only if configured)
    if [ "$is_clone" = false ] || [ -f "$SETTINGS_FILE" ]; then
        if check_controllers; then
            controllers_ok=true
            log "INFO" "All controller connections successful"
        else
            log "WARN" "Some controller connections failed"
            exit_code=2
        fi
    fi

    # Step 3: Write final status
    if [ "$is_clone" = true ]; then
        write_status "clone_detected" "Device needs configuration" true false
        exit_code=1
    elif [ "$controllers_ok" = false ]; then
        write_status "controller_error" "Some controllers unreachable" false false
        exit_code=2
    else
        write_status "ok" "All systems operational" false true
        exit_code=0
    fi

    log "INFO" "Boot check complete (exit code: $exit_code)"
    log "INFO" "=========================================="

    return $exit_code
}

# Run main function
main "$@"
