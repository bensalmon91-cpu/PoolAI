#!/bin/bash
# ========================================
# PoolAIssistant USB Data Storage Script
# ========================================
# Detects USB storage and uses it for database storage
# Preserves SD card by offloading writes to USB
#
# Run on boot before PoolAIssistant services start

# Note: Removed 'set -e' to allow explicit error handling and prevent silent failures

DATA_DIR="/opt/PoolAIssistant/data"
USB_MOUNT="/mnt/poolaissistant_usb"
USB_DATA="$USB_MOUNT/poolaissistant_data"
MARKER_FILE="$USB_DATA/.poolaissistant_data"
LOG_FILE="/var/log/poolaissistant_usb.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

# Handle read-only filesystem (Pi may be configured with read-only root for SD card protection)
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

# Get the user/group to own data files (check if poolaissistant exists)
get_data_owner() {
    if id "poolaissistant" &>/dev/null; then
        echo "poolaissistant:poolaissistant"
    elif id "poolai" &>/dev/null; then
        echo "poolai:poolai"
    else
        echo "root:root"
    fi
}

# Find first USB storage device
find_usb_device() {
    log "Scanning for USB storage devices..."

    # Look for USB block devices (not partitions)
    local found_any=false
    for dev in /dev/sd[a-z]; do
        if [ -b "$dev" ]; then
            found_any=true
            log "  Checking device: $dev"

            # Check if it's USB
            local dev_info
            dev_info=$(udevadm info --query=property --name="$dev" 2>/dev/null)
            if [ $? -ne 0 ]; then
                log "    Could not query device info"
                continue
            fi

            if echo "$dev_info" | grep -q "ID_BUS=usb"; then
                local model=$(echo "$dev_info" | grep "ID_MODEL=" | cut -d= -f2)
                log "    Found USB device: ${model:-unknown}"

                # Return first partition, or device itself if no partitions
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

# Format USB if needed (creates ext4 filesystem)
format_usb() {
    local device="$1"
    log "Formatting $device as ext4..."

    # Unmount if mounted
    umount "$device" 2>/dev/null || true

    # Create ext4 filesystem with label
    mkfs.ext4 -L "PoolAIssistant" "$device"

    log "Format complete"
}

# Check if device has valid filesystem
has_filesystem() {
    local device="$1"
    blkid "$device" | grep -qE "TYPE=\"(ext4|ext3|vfat|ntfs)\"" 2>/dev/null
}

# Mount USB device
mount_usb() {
    local device="$1"

    # Create mount point
    mkdir -p "$USB_MOUNT"

    # Check filesystem type
    local fstype=$(blkid -s TYPE -o value "$device" 2>/dev/null)

    if [ -z "$fstype" ]; then
        log "No filesystem found on $device - formatting..."
        format_usb "$device"
        fstype="ext4"
    fi

    # Mount options based on filesystem
    local mount_opts="defaults,noatime"
    if [ "$fstype" = "vfat" ] || [ "$fstype" = "ntfs" ]; then
        mount_opts="$mount_opts,uid=1000,gid=1000"
    fi

    # Mount
    mount -t "$fstype" -o "$mount_opts" "$device" "$USB_MOUNT"
    log "Mounted $device ($fstype) at $USB_MOUNT"
}

# Initialize USB data directory
init_usb_data() {
    if ! mkdir -p "$USB_DATA"; then
        log_error "Failed to create USB data directory: $USB_DATA"
        return 1
    fi

    # Create marker file
    echo "PoolAIssistant Data Directory" > "$MARKER_FILE"
    echo "Created: $(date)" >> "$MARKER_FILE"

    # Set permissions using detected owner
    local owner=$(get_data_owner)
    log "Setting ownership to: $owner"
    chown -R "$owner" "$USB_DATA" 2>/dev/null || log "Warning: Could not set ownership to $owner"
    chmod 755 "$USB_DATA"

    log "Initialized USB data directory at $USB_DATA"
}

# Migrate existing data from SD to USB
migrate_data() {
    if [ -d "$DATA_DIR" ] && [ ! -L "$DATA_DIR" ]; then
        log "Migrating existing data from SD card to USB..."

        # Copy existing data
        if [ "$(ls -A $DATA_DIR 2>/dev/null)" ]; then
            cp -a "$DATA_DIR"/* "$USB_DATA"/ 2>/dev/null || true
            log "Data copied to USB"
        fi

        # Backup original directory
        mv "$DATA_DIR" "${DATA_DIR}.sd_backup"
        log "Original data backed up to ${DATA_DIR}.sd_backup"
    fi
}

# Create symlink from DATA_DIR to USB
create_symlink() {
    # Remove existing directory/link
    if [ -L "$DATA_DIR" ]; then
        rm "$DATA_DIR"
    elif [ -d "$DATA_DIR" ]; then
        migrate_data
    fi

    # Create symlink
    ln -s "$USB_DATA" "$DATA_DIR"
    log "Created symlink: $DATA_DIR -> $USB_DATA"
}

# Restore SD card data (fallback when no USB)
restore_sd_fallback() {
    if [ -L "$DATA_DIR" ]; then
        # Remove symlink
        rm "$DATA_DIR"
        log "Removed USB symlink"
    fi

    if [ -d "${DATA_DIR}.sd_backup" ]; then
        # Restore from backup
        mv "${DATA_DIR}.sd_backup" "$DATA_DIR"
        log "Restored data from SD backup"
    else
        # Create fresh directory
        mkdir -p "$DATA_DIR"
        local owner=$(get_data_owner)
        chown "$owner" "$DATA_DIR" 2>/dev/null || log "Warning: Could not set ownership to $owner"
        log "Created fresh data directory on SD card"
    fi
}

# Main function
main() {
    log "========================================"
    log "PoolAIssistant USB Storage Check"
    log "========================================"

    # Ensure we can write to root filesystem (for mount points, symlinks, etc.)
    remount_rw

    # Restore read-only state on exit
    trap remount_ro EXIT

    # Check if device was specified as argument
    if [ -n "$1" ]; then
        USB_DEVICE="$1"
        log "Using specified device: $USB_DEVICE"
    else
        # Find USB device automatically
        USB_DEVICE=$(find_usb_device) || true
    fi

    if [ -z "$USB_DEVICE" ]; then
        log "No USB storage detected"

        # Check if we were using USB before
        if [ -L "$DATA_DIR" ]; then
            log "WARNING: Was using USB storage but device not found!"
            log "Falling back to SD card storage"
            restore_sd_fallback
        else
            log "Using SD card storage (default)"
        fi

        exit 0
    fi

    log "Found USB device: $USB_DEVICE"

    # Mount USB
    if ! mountpoint -q "$USB_MOUNT"; then
        mount_usb "$USB_DEVICE"
    else
        log "USB already mounted at $USB_MOUNT"
    fi

    # Check for existing PoolAIssistant data on USB
    if [ -f "$MARKER_FILE" ]; then
        log "Found existing PoolAIssistant data on USB"
    else
        log "Initializing new USB data directory"
        init_usb_data
        migrate_data
    fi

    # Create/verify symlink
    create_symlink

    # Verify
    if [ -L "$DATA_DIR" ] && [ -d "$USB_DATA" ]; then
        log "SUCCESS: Using USB storage for data"
        log "  Device: $USB_DEVICE"
        log "  Mount: $USB_MOUNT"
        log "  Data: $USB_DATA"

        # Show disk usage
        df -h "$USB_MOUNT" | tail -1 | awk '{print "  Space: " $3 " used / " $2 " total (" $5 " used)"}'
    else
        log "ERROR: Failed to set up USB storage"
        restore_sd_fallback
        exit 1
    fi

    log "========================================"
}

# Run main
main "$@"
