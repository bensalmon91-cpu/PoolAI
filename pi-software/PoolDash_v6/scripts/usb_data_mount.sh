#!/bin/bash
# ========================================
# PoolAIssistant USB Data Storage Script
# ========================================
# Detects USB storage and uses it for database storage
# Preserves SD card by offloading writes to USB
#
# v6.11.22: hardened after a real production incident on Swanwood - the
# Flask route used to run this synchronously with subprocess.run(timeout=180)
# and copy a live, actively-growing multi-GB SQLite database with a plain
# `cp -a`, no service stop. Copying 6+ GB over USB2/NTFS took far longer
# than 180s; when the timeout fired, only the immediate child process was
# killed, not the `cp` it had spawned, so the copy kept running orphaned in
# the background for ~30 more minutes and left a dangling symlink instead of
# completing the directory swap. No data was lost only because the swap
# step never ran. This version:
#   - stops poolaissistant_logger/poolaissistant_ui before copying (the old
#     version copied a hot, actively-written WAL-mode database file)
#   - is meant to be launched detached (see main_ui.py's enable_external_storage,
#     which now uses subprocess.Popen instead of a blocking subprocess.run)
#   - writes machine-readable progress to $STATUS_FILE throughout, so the UI
#     can show real progress instead of a single "check back shortly" flash
#   - uses rsync instead of cp -a when available (resumable, and doesn't
#     silently continue past a mid-copy failure the way cp can)
#   - verifies the copy (byte-size match + sqlite3 integrity_check on the
#     pool readings DB) before doing the swap that discards the SD original
#
# Run manually via Settings -> System -> External Storage, or directly with
# a device path argument.

DATA_DIR="/opt/PoolAIssistant/data"
USB_MOUNT="/mnt/poolaissistant_usb"
USB_DATA="$USB_MOUNT/poolaissistant_data"
MARKER_FILE="$USB_DATA/.poolaissistant_data"
LOG_FILE="/var/log/poolaissistant_usb.log"
STATUS_FILE="$DATA_DIR/external_storage_status.json"
POOL_DB_NAME="pool_readings.sqlite3"
SERVICES=("poolaissistant_logger" "poolaissistant_ui")

mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

# Write machine-readable progress for the Settings UI to poll. Never lets a
# status-write failure abort the migration itself.
write_status() {
    local phase="$1"
    local message="$2"
    local error="${3:-}"
    local tmp_file="${STATUS_FILE}.tmp.$$"
    {
        printf '{\n'
        printf '  "phase": "%s",\n' "$phase"
        printf '  "message": "%s",\n' "$(printf '%s' "$message" | sed 's/"/\\"/g')"
        printf '  "error": %s,\n' "$([ -n "$error" ] && printf '"%s"' "$(printf '%s' "$error" | sed 's/"/\\"/g')" || printf 'null')"
        printf '  "updated_at": "%s"\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf '}\n'
    } > "$tmp_file" 2>/dev/null && mv "$tmp_file" "$STATUS_FILE" 2>/dev/null
}

remount_rw() {
    if mount | grep -q "on / type.*ro,"; then
        log "Remounting root filesystem as read-write..."
        mount -o remount,rw / || log "Warning: Could not remount as read-write"
    fi
}

remount_ro() {
    if mount | grep -q "on / type.*rw"; then
        log "Remounting root filesystem as read-only..."
        mount -o remount,ro / || true
    fi
}

get_data_owner() {
    if id "poolaissistant" &>/dev/null; then
        echo "poolaissistant:poolaissistant"
    elif id "poolai" &>/dev/null; then
        echo "poolai:poolai"
    else
        echo "root:root"
    fi
}

stop_services() {
    log "Stopping PoolAIssistant services before copying data..."
    for svc in "${SERVICES[@]}"; do
        systemctl stop "$svc" 2>/dev/null || log "Warning: could not stop $svc (continuing)"
    done
    # Give the logger a moment to release its WAL/SHM files cleanly.
    sleep 2
}

start_services() {
    log "Restarting PoolAIssistant services..."
    for svc in "${SERVICES[@]}"; do
        systemctl start "$svc" 2>/dev/null || log "Warning: could not start $svc"
    done
}

find_usb_device() {
    log "Scanning for USB storage devices..."
    local found_any=false
    for dev in /dev/sd[a-z]; do
        if [ -b "$dev" ]; then
            found_any=true
            log "  Checking device: $dev"
            local dev_info
            dev_info=$(udevadm info --query=property --name="$dev" 2>/dev/null)
            if [ $? -ne 0 ]; then
                log "    Could not query device info"
                continue
            fi
            if echo "$dev_info" | grep -q "ID_BUS=usb"; then
                local model=$(echo "$dev_info" | grep "ID_MODEL=" | cut -d= -f2)
                log "    Found USB device: ${model:-unknown}"
                if [ -b "${dev}1" ]; then
                    log "    Using partition: ${dev}1"
                    echo "${dev}1"
                else
                    log "    Using whole device: $dev"
                    echo "$dev"
                fi
                return 0
            else
                log "    Not a USB device (ID_BUS=$(echo "$dev_info" | grep "ID_BUS=" | cut -d= -f2))"
            fi
        fi
    done
    if [ "$found_any" = false ]; then
        log "  No /dev/sd* block devices found"
    fi
    return 1
}

format_usb() {
    local device="$1"
    log "Formatting $device as ext4..."
    umount "$device" 2>/dev/null || true
    mkfs.ext4 -L "PoolAIssistant" "$device"
    log "Format complete"
}

has_filesystem() {
    local device="$1"
    blkid "$device" | grep -qE "TYPE=\"(ext4|ext3|vfat|ntfs)\"" 2>/dev/null
}

mount_usb() {
    local device="$1"
    mkdir -p "$USB_MOUNT"
    local fstype=$(blkid -s TYPE -o value "$device" 2>/dev/null)
    if [ -z "$fstype" ]; then
        log "No filesystem found on $device - formatting..."
        format_usb "$device"
        fstype="ext4"
    fi
    local mount_opts="defaults,noatime"
    if [ "$fstype" = "vfat" ] || [ "$fstype" = "ntfs" ]; then
        mount_opts="$mount_opts,uid=1000,gid=1000"
    fi
    mount -t "$fstype" -o "$mount_opts" "$device" "$USB_MOUNT"
    log "Mounted $device ($fstype) at $USB_MOUNT"
}

init_usb_data() {
    if ! mkdir -p "$USB_DATA"; then
        log_error "Failed to create USB data directory: $USB_DATA"
        return 1
    fi
    echo "PoolAIssistant Data Directory" > "$MARKER_FILE"
    echo "Created: $(date)" >> "$MARKER_FILE"
    local owner=$(get_data_owner)
    log "Setting ownership to: $owner"
    chown -R "$owner" "$USB_DATA" 2>/dev/null || log "Warning: Could not set ownership to $owner"
    chmod 755 "$USB_DATA"
    log "Initialized USB data directory at $USB_DATA"
}

# Copy the SD-card data onto the USB destination. Services must already be
# stopped by the caller so pool_readings.sqlite3 (and its -wal/-shm files)
# are quiescent during the copy - rsync/cp on a live WAL-mode DB can copy a
# torn, inconsistent snapshot.
copy_data() {
    log "Copying data from $DATA_DIR to $USB_DATA..."
    write_status "migrating" "Copying data to external storage - this can take a while for a large database"

    if [ ! "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
        log "Source data directory is empty, nothing to copy"
        return 0
    fi

    if command -v rsync >/dev/null 2>&1; then
        rsync -a --stats "$DATA_DIR"/ "$USB_DATA"/ >> "$LOG_FILE" 2>&1
        return $?
    else
        log "Warning: rsync not available, falling back to cp -a"
        cp -a "$DATA_DIR"/* "$USB_DATA"/ 2>>"$LOG_FILE"
        return $?
    fi
}

# Verify the copy before we let create_symlink() discard the SD-card
# original. Checks: (1) the copied pool DB passes SQLite's own integrity
# check, (2) total copied byte size is not suspiciously smaller than the
# source (a full byte-for-byte compare would be safer still, but on a
# multi-GB DB that can itself take minutes - this catches a truncated/
# aborted copy without doubling the migration time).
verify_copy() {
    write_status "verifying" "Verifying copied data before switching over"

    local src_db="$DATA_DIR/$POOL_DB_NAME"
    local dst_db="$USB_DATA/$POOL_DB_NAME"
    if [ -f "$src_db" ]; then
        if [ ! -f "$dst_db" ]; then
            log_error "Copied database not found at $dst_db"
            return 1
        fi
        local integrity
        integrity=$(sqlite3 "$dst_db" "PRAGMA integrity_check;" 2>&1)
        if [ "$integrity" != "ok" ]; then
            log_error "Copied database failed integrity check: $integrity"
            return 1
        fi
        log "Copied database passed integrity check"
    fi

    local src_size dst_size
    src_size=$(du -sb "$DATA_DIR" 2>/dev/null | cut -f1)
    dst_size=$(du -sb "$USB_DATA" 2>/dev/null | cut -f1)
    if [ -n "$src_size" ] && [ -n "$dst_size" ]; then
        # Allow the destination to be up to 5% smaller than the source
        # (filesystem block-size rounding differences between ext4/NTFS),
        # but not meaningfully smaller - that indicates a truncated copy.
        local min_ok=$(( src_size * 95 / 100 ))
        if [ "$dst_size" -lt "$min_ok" ]; then
            log_error "Copied data size ($dst_size bytes) is suspiciously smaller than source ($src_size bytes)"
            return 1
        fi
        log "Size check OK: source=${src_size}B destination=${dst_size}B"
    fi
    return 0
}

# Back up the SD-card original and swap DATA_DIR over to a symlink pointing
# at the (already-copied-and-verified) USB destination.
migrate_data() {
    if [ -d "$DATA_DIR" ] && [ ! -L "$DATA_DIR" ]; then
        log "Backing up original SD-card data directory..."
        mv "$DATA_DIR" "${DATA_DIR}.sd_backup"
        log "Original data backed up to ${DATA_DIR}.sd_backup"
    fi
}

create_symlink() {
    if [ -L "$DATA_DIR" ]; then
        rm "$DATA_DIR"
    fi
    ln -s "$USB_DATA" "$DATA_DIR"
    log "Created symlink: $DATA_DIR -> $USB_DATA"
}

restore_sd_fallback() {
    if [ -L "$DATA_DIR" ]; then
        rm "$DATA_DIR"
        log "Removed USB symlink"
    fi
    if [ -d "${DATA_DIR}.sd_backup" ]; then
        mv "${DATA_DIR}.sd_backup" "$DATA_DIR"
        log "Restored data from SD backup"
    elif [ ! -d "$DATA_DIR" ]; then
        mkdir -p "$DATA_DIR"
        local owner=$(get_data_owner)
        chown "$owner" "$DATA_DIR" 2>/dev/null || log "Warning: Could not set ownership to $owner"
        log "Created fresh data directory on SD card"
    fi
}

main() {
    log "========================================"
    log "PoolAIssistant USB Storage Check"
    log "========================================"
    write_status "starting" "Starting external storage migration"

    remount_rw
    trap remount_ro EXIT

    if [ -n "$1" ]; then
        USB_DEVICE="$1"
        log "Using specified device: $USB_DEVICE"
    else
        USB_DEVICE=$(find_usb_device) || true
    fi

    if [ -z "$USB_DEVICE" ]; then
        log "No USB storage detected"
        if [ -L "$DATA_DIR" ]; then
            log "WARNING: Was using USB storage but device not found!"
            log "Falling back to SD card storage"
            stop_services
            restore_sd_fallback
            start_services
            write_status "error" "USB device not found - reverted to SD card storage" "device not found"
        else
            log "Using SD card storage (default)"
            write_status "idle" "No external storage device present"
        fi
        exit 0
    fi

    log "Found USB device: $USB_DEVICE"
    write_status "mounting" "Mounting external storage device"

    if ! mountpoint -q "$USB_MOUNT"; then
        if ! mount_usb "$USB_DEVICE"; then
            write_status "error" "Failed to mount external storage device" "mount failed"
            exit 1
        fi
    else
        log "USB already mounted at $USB_MOUNT"
    fi

    if [ -f "$MARKER_FILE" ]; then
        log "Found existing PoolAIssistant data on USB"
    else
        log "Initializing new USB data directory"
        init_usb_data
    fi

    # Stop services for the entire copy+verify window - a live, actively
    # written WAL-mode SQLite DB cannot be safely copied with rsync/cp.
    stop_services

    if ! copy_data; then
        log_error "Data copy failed"
        write_status "error" "Data copy failed - services restarted, still using SD card storage" "copy failed"
        start_services
        exit 1
    fi

    if ! verify_copy; then
        log_error "Copy verification failed - aborting migration, SD card data is untouched"
        write_status "error" "Copy verification failed - still using SD card storage (no data was changed)" "verification failed"
        start_services
        exit 1
    fi

    migrate_data
    create_symlink
    start_services

    if [ -L "$DATA_DIR" ] && [ -d "$USB_DATA" ]; then
        log "SUCCESS: Using USB storage for data"
        log "  Device: $USB_DEVICE"
        log "  Mount: $USB_MOUNT"
        log "  Data: $USB_DATA"
        write_status "done" "Now using external storage for data"
        df -h "$USB_MOUNT" | tail -1 | awk '{print "  Space: " $3 " used / " $2 " total (" $5 " used)"}'
    else
        log "ERROR: Failed to set up USB storage"
        write_status "error" "Failed to switch over to external storage" "symlink setup failed"
        stop_services
        restore_sd_fallback
        start_services
        exit 1
    fi

    log "========================================"
}

main "$@"
